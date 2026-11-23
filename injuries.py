"""Read the NBA's official date-stamped injury reports."""
from datetime import datetime
import re
import subprocess
from urllib.request import urlopen
from zoneinfo import ZoneInfo

INDEX = "https://www.nba.com/players/injury-report"
PDF = r"https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2}_\d{2}[AP]M)\.pdf"
EASTERN = ZoneInfo("America/New_York")
ALIASES = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA",
           "WSH": "WAS", "PHO": "PHX", "BRK": "BKN"}

def matchup(away, home):
    return "@".join(ALIASES.get(t, t) for t in (away, home))

def parse(report):
    found = {}
    day = game = team = None
    for raw in report.splitlines():
        parts = re.split(r"\s{2,}", raw.strip())
        if parts and re.fullmatch(r"\d\d/\d\d/\d{4}", parts[0]):
            day = datetime.strptime(parts.pop(0), "%m/%d/%Y").date().isoformat()
        if parts and "(ET)" in parts[0]:
            parts.pop(0)
        if parts and re.fullmatch(r"[A-Z]{2,4}@[A-Z]{2,4}", parts[0]):
            game = matchup(*parts.pop(0).split("@"))
            team = None
        if not (day and game) or not parts:
            continue
        status = next((i for i, txt in enumerate(parts) if txt in
                       ("Out", "Doubtful", "Questionable", "Probable", "Available")), None)
        if status is not None and status >= 1 and "," in parts[status-1]:
            if status >= 2:
                team = parts[status-2]
            if team:
                found.setdefault((day, game), []).append({"team": team, "player": parts[status-1],
                    "status": parts[status], "reason": parts[status+1] if len(parts)>status+1 else ""})
        elif parts[-1] == "NOT YET SUBMITTED" and len(parts) >= 2:
            found.setdefault((day, game), []).append({"team": parts[-2], "status": parts[-1]})
    return found

def load_injuries(now):
    try:
        with urlopen(INDEX, timeout=10) as response:
            html = response.read().decode()
        links = []
        for m in re.finditer(PDF, html):
            when = datetime.strptime(" ".join(m.groups()), "%Y-%m-%d %I_%M%p").replace(tzinfo=EASTERN)
            if when <= now:
                links.append((when, m[0]))
        when, url = max(links)
        with urlopen(url, timeout=10) as response:
            pdf = response.read(4_000_000)
        raw = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True,
                             check=True, timeout=10).stdout.decode()
        if not re.search(r"Injury Report: \d\d/\d\d/\d\d", raw):
            return None
        return when.isoformat(), url, parse(raw)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None
