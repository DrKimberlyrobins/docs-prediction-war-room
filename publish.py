"""Build the static slate, immutable forecasts, and retrospective grades."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os

from feeds import CENTRAL, LEAGUES, load
from injuries import load_injuries, matchup
from model import FORMULA, VERSION, backtest, grade, normalize, score, select, train, utc

ROOT = Path("site/data")
ARCHIVE = ROOT / "receipts"

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)

def archive(g, forecast, observed):
    if datetime.now(timezone.utc) >= utc(g["tip"]):
        return
    content = json.dumps(forecast, sort_keys=True).encode()
    digest = hashlib.sha256(content).hexdigest()
    folder = ARCHIVE / g["id"]
    previous = sorted(folder.glob("*.json"))
    if previous:
        last = json.loads(previous[-1].read_text())
        p, old = forecast["projection"], last["projection"]
        quote_keys = ("type", "side", "line", "odds", "provider")
        def comparable(receipt):
            pick = receipt["pick"] or {}
            return [pick.get(key) for key in quote_keys]
        same_picks = comparable(last) == comparable(forecast)
        same_market = last.get("cover_market") == forecast.get("cover_market")
        new_injuries = (forecast.get("injuries") or {}).get("entries")
        old_injuries = (last.get("injuries") or {}).get("entries")
        halves = forecast["first_half"], last["first_half"]
        same_half = (halves[0] is None and halves[1] is None) or (
            all(halves) and all(abs(halves[0][side] - halves[1][side]) < .25 for side in ("home", "away")))
        same_score = all(abs(p[side] - old[side]) < .25 for side in ("home", "away"))
        if same_market and same_picks and same_score and same_half and new_injuries == old_injuries and last["version"] == forecast["version"]:
            return
    receipt = {"game_id": g["id"], "league": g["league"], "tip": g["tip"],
               "home": g["home"]["name"], "away": g["away"]["name"],
               "source": g["source"], "captured": observed.isoformat(),
               "digest": digest, **forecast}
    write(folder / f"{observed:%Y%m%dT%H%M%S%fZ}.json", receipt)

def metrics(rows):
    wins = sum(r["grade"] == "Win" for r in rows)
    losses = sum(r["grade"] == "Loss" for r in rows)
    errors = [r["margin_error"] for r in rows if r.get("margin_error") is not None]
    return {"wins": wins, "losses": losses, "pushes": sum(r["grade"] == "Push" for r in rows),
            "win_pct": round(100 * wins / (wins + losses), 1) if wins + losses else None,
            "margin_mae": round(sum(errors) / len(errors), 2) if errors else None}

def grade_archive(all_games):
    store = ROOT / "finals.json"
    finals = json.loads(store.read_text()) if store.exists() else {}
    rows = []
    groups = defaultdict(list)
    for folder in sorted(ARCHIVE.glob("*")):
        current = all_games.get(folder.name)
        if current and current["status"] == "STATUS_FINAL":
            if all(current[s].get("score") is not None for s in ("home", "away")):
                finals[folder.name] = current
        final = finals.get(folder.name)
        market_started = False
        for index, ref in enumerate(sorted(folder.glob("*.json"))):
            r = json.loads(ref.read_text())
            if utc(r["captured"]) >= utc(r["tip"]):
                continue
            r["first"] = index == 0
            r["first_market"] = bool(r["pick"]) and not market_started
            market_started |= bool(r["pick"])
            r["grade"] = grade(final, r["pick"]) if final else None
            if final:
                r["final"] = {s: final[s]["score"] for s in ("home", "away")}
                r["halftime"] = {s: final[s].get("half") for s in ("home", "away")}
                p = r["projection"]
                r["margin_error"] = abs((p["home"]-p["away"])-(r["final"]["home"]-r["final"]["away"]))
            r["receipt"] = str(ref.relative_to("site"))
            if r["first_market"] and r["grade"]:
                groups["Overall"].append(r)
                groups[r["league"]].append(r)
                groups[f"{r['league']} / {r['pick']['type']}"].append(r)
            rows.append(r)
    write(store, finals)
    return {"receipts": sorted(rows, key=lambda r: r["captured"], reverse=True),
            "records": {key: metrics(value) for key, value in groups.items()}}

def main():
    today = datetime.now(CENTRAL).date()
    raw, failures = load(today)
    observed = datetime.now(timezone.utc)
    injury_report = load_injuries(observed)
    observed = datetime.now(timezone.utc)
    all_games = {}
    counts = defaultdict(int)
    for (league, _), events in sorted(raw.items()):
        for event in events:
            game = normalize(league, event)
            if game:
                all_games[game["id"]] = game
    upcoming = []
    reports = {}
    for league in LEAGUES:
        games = [g for g in all_games.values() if g["league"] == league]
        history = [g for g in games if g["status"] == "STATUS_FINAL" and utc(g["tip"]) < observed]
        validation = backtest(history, CENTRAL)
        reports[league] = validation
        full_fit = train(history, observed, "score")
        half_fit = train(history, observed, "half")
        for game in games:
            day = utc(game["tip"]).astimezone(CENTRAL).date()
            if not today <= day <= today + timedelta(days=1):
                continue
            if (league, day) not in raw:
                continue
            counts[f"{league}/{day}"] += 1
            forecast = None
            if game["status"] == "STATUS_SCHEDULED" and game["time_valid"] and observed < utc(game["tip"]):
                projection = score(game, full_fit, 1.5)
                if projection:
                    forecast = {"version": VERSION, "projection": projection,
                                "first_half": score(game, half_fit, .75),
                                "cover_market": [q for q in game["market"] if q["type"] in ("spread", "half_spread")],
                                "cover_validation": {key: validation.get(key) for key in ("score_margin", "half_margin")},
                                "pick": select(game, projection, validation),
                                "coverage": ["Individual injury impact, starters, minutes, and defender assignments unavailable in the model.",
                                             "Possession-based efficiency and pace are unavailable. The model uses opponent-adjusted scoring per game."]}
                    if league == "nba" and injury_report:
                        captured, url, entries = injury_report
                        key = matchup(game["away"]["abbr"], game["home"]["abbr"])
                        if (str(day), key) in entries:
                            forecast["injuries"] = {"as_of": captured, "url": url,
                                                    "entries": entries[str(day), key]}
                    archive(game, forecast, observed)
            previous = sorted((ARCHIVE / game["id"]).glob("*.json"))
            if previous:
                game["forecast"] = json.loads(previous[-1].read_text())
            game["day"] = str(day)
            upcoming.append(game)
    # Preserve each daily slate before the rolling board drops it.
    for day in sorted({g["day"] for g in upcoming}):
        write(ROOT / "history" / f"{day}.json", {"games": [g for g in upcoming if g["day"] == day]})
    write(ROOT / "results.json", grade_archive(all_games))
    write(ROOT / "board.json", {"generated": observed.isoformat(), "today": str(today),
                                "formula": FORMULA, "version": VERSION, "counts": dict(counts),
                                "leagues": LEAGUES, "validation": reports, "failures": failures,
                                "games": sorted(upcoming, key=lambda g: g["tip"])})
    print(f"{len(upcoming)} games, {sum('forecast' in g for g in upcoming)} projected, "
          f"{sum(bool(g.get('forecast', {}).get('pick')) for g in upcoming)} with market selections, {len(failures)} failed feeds")
    if not any((league, today) in raw for league in LEAGUES) and os.getenv("GITHUB_ACTIONS"):
        raise SystemExit("Today's schedule is unavailable from all three feeds")

if __name__ == "__main__":
    main()
