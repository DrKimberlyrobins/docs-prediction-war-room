# DOC'S PREDICTION WAR ROOM

Independent basketball slate, pregame projections, market comparisons, and immutable forecast receipts.

## Run locally

Use Python 3.12 or later. Install Poppler's `pdftotext` to include official NBA injury reports.

```sh
python -m unittest -v
python publish.py
python -m http.server 8765 --directory site
```

Open http://localhost:8765 for the dashboard and /results.html for the grading page.

## GitHub Pages

In a new public repository on branch `main`, select **GitHub Actions** under **Settings → Pages**. Give the workflow write access to the new repo's default branch so it can commit forecast receipts. Run **Refresh and publish War Room** manually the first time. The workflow targets 13 and 43 minutes past each hour, also runs on code pushes, archives forecast versions, and deploys its generated static files to Pages. Scheduled runners can start late.

## Data and methodology

- ESPN daily scoreboards provide fixtures, home/away, neutral sites, final scores, period scores, and attributed lines. Men's and women's college scoreboards use ESPN's Division I group. The dashboard covers the current and next Central dates.
- The official NBA injury report is parsed independently, matched by date and team abbreviations, and shown with its source timestamp. Players listed out or limited are disclosed. The score model applies no player-residual adjustment, so it can significantly miss a changed rotation.
- Ratings use recency weights with a 14-day half-life, six iterations of opponent adjustment, and five prior games of shrinkage. Home court adds 1.5 points to the home team and subtracts 1.5 from the away team. Neutral games receive zero adjustment. The first-half model uses actual first-half scores and a half-sized venue adjustment. Each team requires four observed games.
- Forecasts are computed before market comparison. Spread disagreement is the team's projected margin plus its offered spread. Totals disagreement is the projected total minus the offered line for Over, with sign reversed for Under. Ranking uses positive disagreement divided by historical RMSE with a sample-size discount. Rankings compare normalized point disagreement. Odds are displayed, and the model does not estimate expected value.
- Rolling-origin evaluation trains only on games dated at least two Central calendar days before each evaluation game. This is a retrospective score test on the current history window. It does not measure profitability or validate calibrated probabilities. Measures and samples are saved in `site/data/board.json`.
- The first accepted market forecast per game drives the record. Revisions also receive individual grades without producing duplicate wins or losses. Results are scored against the saved quote and final scoreboard. Revisions are retained when the pick, injury entries, model version, or projected score (by at least a quarter point) changes.
- Only timestamped pregame snapshots are accepted. Score-only forecasts are retained when no eligible market exists. The capture time is the local observation timestamp for ESPN prices.

## Current coverage limits

ESPN-attributed quotes are the only active market feed. DraftKings availability, including on women's games, varies by slate. Kambi, Kalshi, KenPom, NBA prop distributions, separate NBA team-total and first-half market candidates, verified starting lineups and substitutions, player matchup assignments, pace and possession inputs, rest and travel inputs, and quantified injury adjustments are outside this version. Ranking can overstate opportunities when schedules are sparse or team quality shifts quickly. Provider availability and permission to republish at production scale require independent verification. The source bundle includes no provider credentials.
