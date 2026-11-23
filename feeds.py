"""Retrieve ESPN daily scoreboards, preserving per-league fetch failures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
LEAGUES = {"nba": "NBA", "mens-college-basketball": "Men's College Basketball",
           "womens-college-basketball": "Women's College Basketball"}
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball"
CACHE = Path(".cache")

def scoreboard(league, day, today):
    key = CACHE / f"{league}-{day}.json"
    if day < today - timedelta(days=2) and key.exists():
        return json.loads(key.read_text())
    query = f"dates={day:%Y%m%d}&limit=300"
    if league != "nba":
        query += "&groups=50"
    with urlopen(Request(f"{ESPN}/{league}/scoreboard?{query}",
                         headers={"Accept-Encoding": "gzip", "User-Agent": "PredictionWarRoom/1.0"}), timeout=18) as response:
        payload = response.read()
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    events = json.loads(payload)["events"]
    if len(events) >= 300:
        raise ValueError("Schedule may be truncated")
    key.write_text(json.dumps(events, separators=(",", ":")))
    return events

def load(today, lookback=35):
    CACHE.mkdir(exist_ok=True)
    jobs = [(league, today - timedelta(days=i)) for i in range(-1, lookback + 1)
            for league in LEAGUES if league == "nba" or i <= 22]
    results = {}
    failures = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        pending = {job: pool.submit(scoreboard, *job, today) for job in jobs}
        for job, future in pending.items():
            try:
                results[job] = future.result()
            except (ValueError, OSError, KeyError) as error:
                failures.append({"league": job[0], "day": str(job[1]), "error": str(error)})
    return results, failures

if __name__ == "__main__":
    data, failures = load(datetime.now(CENTRAL).date())
    print(f"{len(data)} successful feeds", failures)
