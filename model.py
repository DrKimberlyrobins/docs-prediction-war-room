"""Opponent-adjusted team scoring model and rolling-origin diagnostics."""
from collections import defaultdict
from datetime import datetime, timedelta
from math import exp, sqrt
from statistics import mean
import re

VERSION = "1.0.0"
MIN_GAMES = 4
FORMULA = ("Each team scores league mean + its offense residual + opponent defense residual, "
           "then receives ±1.5 points for home court (zero at neutral sites). "
           "Residuals adjust for opponents over six passes and shrink toward zero using five prior games. "
           "Weights halve every 14 days. The first half is fitted separately from actual first-half scores with ±0.75 points for home court.")

def number(value):
    try:
        return float(str(value).lower().lstrip("ou").replace("−", "-"))
    except (ValueError, TypeError):
        return None

def normalize(league, event):
    comp = event["competitions"][0]
    sides = {c["homeAway"]: c for c in comp["competitors"] if c.get("homeAway") in ("home", "away")}
    if set(sides) != {"home", "away"}:
        return None
    game = {"id": f"{league}-{event['id']}", "league": league, "tip": comp["date"],
            "status": comp["status"]["type"]["name"], "neutral": comp.get("neutralSite", False),
            "time_valid": comp.get("timeValid", False),
            "source": next((x["href"] for x in event.get("links", []) if x.get("href", "").startswith("https://www.espn.com/")),
                           f"https://www.espn.com/{'nba' if league == 'nba' else 'mens-college-basketball' if league.startswith('mens') else 'womens-college-basketball'}/game/_/gameId/{event['id']}")}
    for side, item in sides.items():
        team = item["team"]
        game[side] = {"id": str(team["id"]), "name": team.get("displayName", team.get("name", team["id"])),
                      "abbr": team.get("abbreviation", "")}
        periods = sorted(item.get("linescores", []), key=lambda x: x.get("period", 0))
        count = 1 if league.startswith("mens") else 2
        half = [number(p.get("value", p.get("displayValue"))) for p in periods[:count]]
        if game["status"] == "STATUS_FINAL":
            game[side]["score"] = number(item.get("score"))
            game[side]["half"] = sum(half) if len(half) == count and None not in half else None
    market = []
    for provider in comp.get("odds", []):
        source = provider.get("provider", {}).get("displayName") or provider.get("provider", {}).get("name")
        if not source:
            continue
        for market_type, field, keys in [("spread", "pointSpread", ("home", "away")),
                                         ("total", "total", ("over", "under"))]:
            for side in keys:
                quote = (provider.get(field) or {}).get(side, {}).get("close", {})
                line, odds = number(quote.get("line")), number(quote.get("odds"))
                if market_type == "spread" and line is None:
                    details = provider.get("details", "")
                    match = re.fullmatch(r"([\w .&'-]+)\s+([+-]\d+(?:\.\d+)?)", details)
                    team_keys = {game[s]["abbr"].upper(): s for s in ("home", "away")}
                    if match and match[1].upper() in team_keys:
                        line = float(match[2]) * (1 if team_keys[match[1].upper()] == side else -1)
                if market_type == "total" and line is None:
                    line = number(provider.get("overUnder"))
                if line is not None:
                    market.append({"type": market_type, "side": side, "line": line,
                                   "odds": odds, "provider": source})
    game["market"] = market
    return game

def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def train(games, asof, field):
    obs = defaultdict(list)
    weighted = weight = 0.0
    venue = 0.75 if field == "half" else 1.5
    for g in games:
        h, a = g["home"], g["away"]
        if h.get(field) is None or a.get(field) is None:
            continue
        age = (asof - utc(g["tip"])).total_seconds() / 86400
        if not 0 <= age <= 36:
            continue
        w = exp(-age * 0.69314718056 / 14)
        shift = 0 if g["neutral"] else venue
        obs[h["id"]].append((a["id"], h[field] - shift, a[field] + shift, w))
        obs[a["id"]].append((h["id"], a[field] + shift, h[field] - shift, w))
        weighted += w * (h[field] + a[field])
        weight += 2 * w
    if not weight:
        return None
    center = weighted / weight
    off, defense = defaultdict(float), defaultdict(float)
    for _ in range(6):
        off = {team: sum(w * (s-center-defense.get(opp, 0)) for opp,s,_,w in rows) /
               (5 + sum(r[3] for r in rows)) for team,rows in obs.items()}
        defense = {team: sum(w * (s-center-off.get(opp, 0)) for opp,_,s,w in rows) /
                   (5 + sum(r[3] for r in rows)) for team,rows in obs.items()}
    return center, {team: {"games": len(rows), "offense": off[team], "defense": defense[team]}
                    for team,rows in obs.items()}

def score(game, fit, venue):
    if not fit:
        return None
    center, stats = fit
    h, a = [stats.get(game[s]["id"]) for s in ("home", "away")]
    if not h or not a or min(h["games"], a["games"]) < MIN_GAMES:
        return None
    shift = 0 if game["neutral"] else venue
    return {"home": round(center + h["offense"] + a["defense"] + shift, 2),
            "away": round(center + a["offense"] + h["defense"] - shift, 2),
            "inputs": {"league_mean": center, "home_court_per_team": shift, "home": h, "away": a}}

def backtest(history, central):
    errors = defaultdict(list)
    days = sorted({utc(g["tip"]).astimezone(central).date() for g in history})
    for day in days:
        cutoff = datetime.combine(day, datetime.min.time(), tzinfo=central)
        training = [g for g in history if utc(g["tip"]).astimezone(central).date() < day - timedelta(days=1)]
        fit = train(training, cutoff, "score")
        half_fit = train(training, cutoff, "half")
        for g in history:
            if utc(g["tip"]).astimezone(central).date() != day:
                continue
            for field, f, advantage in [("score", fit, 1.5), ("half", half_fit, .75)]:
                p = score(g, f, advantage)
                if not p or any(g[s].get(field) is None for s in ("home", "away")):
                    continue
                h, a = (p[s] - g[s][field] for s in ("home", "away"))
                errors[field + "_margin"].append(h - a)
                errors[field + "_total"].append(h + a)
    return {key: {"n": len(values), "mae": round(mean(map(abs, values)), 2),
                  "rmse": round(sqrt(mean(x*x for x in values)), 2)}
            for key, values in errors.items()}

def select(game, projection, validation):
    margin = projection["home"] - projection["away"]
    candidates = []
    for q in game["market"]:
        if q["type"] == "spread":
            edge = q["line"] + (margin if q["side"] == "home" else -margin)
            name = f"{game[q['side']]['name']} {q['line']:+g}"
            measure = "score_margin"
        elif game["league"] == "nba":
            sign = 1 if q["side"] == "over" else -1
            edge = sign * (projection["home"] + projection["away"] - q["line"])
            name = f"{q['side'].title()} {q['line']:g}"
            measure = "score_total"
        else:
            continue
        if edge <= 0:
            continue
        evidence = min(projection["inputs"][s]["games"] for s in ("home", "away"))
        stats = validation.get(measure, {})
        rank = None
        if stats.get("n", 0) >= 25 and stats.get("rmse") and q["odds"] is not None:
            rank = round(edge / stats["rmse"] * sqrt(evidence / (evidence + 5)), 4)
        candidates.append({**q, "name": name, "edge": round(edge, 2), "rank": rank,
                           "probability": None, "validation": stats})
    return max(candidates, key=lambda c: (c["rank"] is not None, c["rank"] or c["edge"]), default=None)

def grade(game, pick):
    h, a = [game[s].get("score") for s in ("home", "away")]
    if game["status"] != "STATUS_FINAL" or None in (h, a) or not pick:
        return None
    if pick["type"] == "spread":
        result = (h-a if pick["side"] == "home" else a-h) + pick["line"]
    else:
        result = (h+a-pick["line"]) * (1 if pick["side"] == "over" else -1)
    return "Win" if result > 0 else "Loss" if result < 0 else "Push"
