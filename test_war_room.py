import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from injuries import parse
from model import grade, normalize, score, select, utc

class WarRoomTest(unittest.TestCase):
    def test_home_away_and_college_market(self):
        game = normalize("mens-college-basketball", {"id": "100", "competitions": [{
            "date": "2026-11-24T01:00Z", "status": {"type": {"name":"STATUS_SCHEDULED"}},
            "competitors": [{"homeAway": side, "team": {"id": ident, "displayName": side}}
                            for side,ident in [("away","2"),("home","1")]],
            "odds":[{"provider":{"name":"Test bookmaker"}, "overUnder":90,
                     "pointSpread":{"home":{"close":{"line":"-3.5","odds":"-110"}}}}]
        }]})
        self.assertEqual(game["home"]["id"],"1")
        self.assertEqual(game["away"]["id"],"2")
        ratings = {"1":{"games":8,"offense":5,"defense":0}, "2":{"games":8,"offense":0,"defense":0}}
        projected = score(game, (70,ratings), 1.5)
        self.assertEqual((projected["home"],projected["away"]),(76.5,68.5))
        pick = select(game,projected,{"score_margin":{"n":30,"rmse":12}})
        self.assertEqual((pick["type"],pick["edge"]),("spread",4.5))
        self.assertIsNone(pick["probability"])

    def test_final_grades(self):
        final = {"status":"STATUS_FINAL","home":{"score":101},"away":{"score":96}}
        self.assertEqual(grade(final, {"type":"spread","side":"away","line":6}), "Win")
        self.assertEqual(grade(final, {"type":"spread","side":"home","line":-5}), "Push")
        self.assertEqual(grade(final, {"type":"total","side":"under","line":196.5}), "Loss")
        self.assertIsNone(grade({**final,"status":"STATUS_IN_PROGRESS"}, {"type":"total"}))

    def test_injury_report_switches_game_on_new_time(self):
        text = """11/23/2026   07:00 (ET)   MEM@CHA   Memphis Grizzlies   Last, First   Out   Injury
07:30 (ET)   NO@MIN   New Orleans Pelicans   NOT YET SUBMITTED
                      Minnesota Timberwolves   Last, Player   Probable   Injury"""
        games = parse(text)
        self.assertEqual(games["2026-11-23","MEM@CHA"][0]["status"],"Out")
        self.assertEqual([r["status"] for r in games["2026-11-23","NOP@MIN"]],
                         ["NOT YET SUBMITTED", "Probable"])

    def test_published_receipts_are_reproducible(self):
        path = Path("site/data/board.json")
        if not path.exists():
            self.skipTest("No published snapshot yet")
        games = json.loads(path.read_text())["games"]
        ids = set()
        for game in games:
            self.assertNotIn(game["id"], ids)
            ids.add(game["id"])
            f = game.get("forecast")
            if not f:
                continue
            self.assertLess(utc(f["captured"]),utc(f["tip"]))
            if game["league"] != "nba" and f["pick"]:
                self.assertEqual(f["pick"]["type"], "spread")
            for p in (f["projection"],f["first_half"]):
                if not p:
                    continue
                i = p["inputs"]
                for side, opp, direction in [("home","away",1),("away","home",-1)]:
                    expected = i["league_mean"]+i[side]["offense"]+i[opp]["defense"]+direction*i["home_court_per_team"]
                    self.assertAlmostEqual(p[side],expected,delta=.00501)

if __name__ == "__main__":
    unittest.main()
