# Robinhood Soccer Analyzer

Backtests the soccer prediction markets you can trade on Robinhood against real match
results, for every match played **after the 2026 World Cup** (final: 19 July 2026), to see
whether the market is systematically mispriced and whether any of it survives fees.

Robinhood's soccer event contracts (match winner: home / draw / away) clear on two exchanges:

* **Kalshi** – the majority of league game markets (`KXEPLGAME`, `KXLALIGAGAME`,
  `KXBUNDESLIGAGAME`, `KXSERIEAGAME`, `KXLIGUE1GAME`, `KXMLSGAME`, `KXUCLGAME`, …).
  Kalshi's REST API is public, so the full pre-kickoff price history is available.
* **Rothera** – Robinhood's own exchange, which took over some soccer listings in 2026.
  Rothera has no public market-data API. Prices you record from the app (or your order
  history) can be imported with `--prices-csv` and are analyzed identically.

## What it does

1. **Collects** results and kickoff times (ESPN's free scoreboard feed), bookmaker
   opening/closing odds (football-data.co.uk CSVs, incl. Pinnacle closing), and venue prices
   (Kalshi trades + hourly bid/ask candles, or a CSV you supply).
2. **Snapshots** each contract at kickoff (or `--minutes-before` kickoff): last trade, best bid,
   best ask, volume. In-play trades are ignored.
3. **Joins** every priced event to its fixture by league, team-name alias/fuzzy match, and date.
   Home/away orientation comes from the results source, so it doesn't matter which team the
   venue lists first.
4. **Scores** the venue's prices against three references: the de-vigged closing line
   (`book`), a walk-forward Elo (`elo`) and a time-decayed Poisson/Dixon-Coles model
   (`poisson`), using Brier score and log loss with a paired t-test.
5. **Diagnoses** systematic bias: calibration by price bucket (favourite–longshot), by outcome
   (is the draw underpriced?), by league, and venue-minus-closing-line per outcome.
6. **Backtests** strategies **net of fees**: naive rules (always home/draw/away/favourite/
   underdog/NO-draw) and reference-driven bets (buy YES or NO whenever `fair − price − fee ≥ min-edge`),
   filling at the ask (NO at 1 − bid). Reports ROI with bootstrap 95% intervals, an
   edge-threshold sweep, and breakdowns by outcome, side and league.

Fees default to Robinhood's June-2026 schedule: commission `0.10 × p × (1−p)` per contract
(`0.05` with Gold), rounded up to the cent per order, plus a $0.01 exchange fee. `--fees kalshi`
models trading on Kalshi directly (`0.07 × p × (1−p)`), `--fees none` shows gross numbers.

## Quick start

```bash
pip install -e .[dev]           # pandas, numpy, requests (+ pytest)
rsa demo                        # synthetic end-to-end run, no network -> reports/demo/report.md
rsa series                      # list Kalshi soccer series tickers (live)
rsa run --leagues epl,laliga,bundesliga,seriea,ligue1,mls --data-dir data/live
```

`rsa run` = `rsa fetch` (network, cached under `data/live/cache`) + `rsa backtest` (offline).
Re-run `rsa backtest` with different `--fees`, `--min-edge`, `--fill last`, `--slippage` without
re-downloading. Output goes to `reports/<data-dir name>/`:

| file | contents |
|---|---|
| `report.md` | the findings, with a plain-language verdict section |
| `summary.json` | the same numbers, machine-readable |
| `joined.csv` | one row per match: prices, quotes, odds, model probabilities, result |
| `bets_<reference>.csv` | every bet a strategy would have placed, with fill, fee, edge, P&L |
| `unmatched_events.csv` | priced events that could not be joined to a fixture (fix aliases in `rsa/teams.py`) |

Useful flags for `fetch`/`run`: `--start/--end` (default: 2026-07-20 → today), `--no-candles`
(skip bid/ask, faster), `--minutes-before 60`, `--prices-csv my_rothera_prices.csv`,
`--no-kalshi` (results/odds only), `--kalshi-key-id/--kalshi-private-key` (optional API auth
for higher rate limits; needs `pip install cryptography`).

### Importing prices from Robinhood / Rothera

A CSV with columns `league,team_a,team_b,outcome_label,price` (plus optional `venue,event_id,
market_ticker,yes_bid,yes_ask,snapshot_time,kickoff,volume,result`). `outcome_label` is a team
name or `TIE`; prices may be cents or dollars. See `rsa/prices.py`.

## Reading the report

* A tradeable edge needs **all** of: a bias that is stable across leagues and weeks, ROI whose
  95% interval excludes zero **after fees**, and fills at the ask. The verdict section only
  claims what the numbers support at the sample size.
* The closing line (`book`) is the sharpest public benchmark. A strategy that only beats Elo or
  Poisson is not evidence of an edge; those models are there to show what happens when you
  bet on a weak reference.
* Six weeks of post-World-Cup club football is ~250 matches across six leagues. Intervals will
  be wide; keep re-running as the season goes on (`rsa run` appends nothing—it re-fetches the
  window from cache plus new days).

## Status and caveats

* **No live data has been pulled yet.** This project was built in a sandbox whose network
  policy blocks Kalshi, ESPN and football-data.co.uk, so the only report in the repo
  (`reports/demo/report.md`) is from **synthetic** data with planted biases. Run `rsa run` on
  your own machine to get real findings.
* Kalshi archives settled markets past a rolling cutoff to `/historical/*` endpoints; the client
  reads both tiers. Endpoint shapes were taken from Kalshi's public documentation and both the
  cents and `_dollars` price encodings are handled, but if a field name changes, `rsa/kalshi.py`
  is the place to look.
* Series tickers for the Europa/Conference League, Leagues Cup and Liga MX follow Kalshi's naming
  convention but are marked unverified in `rsa/config.py`; confirm with `rsa series`.
* ESPN's scoreboard endpoint is unofficial and unauthenticated; football-data.co.uk covers the
  big-five European leagues only (MLS uses ESPN's moneyline as the odds reference, which is
  weaker than Pinnacle closing).
* "Last trade" fills overstate what you can actually get; the default `--fill ask` is realistic
  for Kalshi-routed contracts when candles are available.

## Project layout

```
rsa/config.py     leagues, series tickers, ESPN/football-data codes, analysis window
rsa/fees.py       Robinhood / Kalshi fee models, break-even maths
rsa/kalshi.py     public API client (live + historical tiers), pre-kickoff snapshots
rsa/prices.py     venue-agnostic PriceSnapshot + CSV import/export
rsa/results.py    ESPN + football-data.co.uk loaders, de-vigging (Shin), odds merge
rsa/teams.py      team-name aliases, normalization, fuzzy matching, title parsing
rsa/matching.py   join priced events to fixtures, one row per match
rsa/models.py     Elo (Davidson draw), Poisson/Dixon-Coles, walk-forward predictions
rsa/backtest.py   scoring rules, calibration, bias tables, fee-aware strategies, bootstrap
rsa/report.py     markdown report + verdicts
rsa/pipeline.py   collect -> save -> analyze -> write
rsa/synth.py      synthetic raw-shaped fixtures + offline Kalshi client (used by `rsa demo`)
rsa/cli.py        command line
tests/            pytest suite (fees, parsing, matching, models, backtest, demo pipeline)
```

Run the tests with `pytest`.
