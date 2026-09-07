# Robinhood Soccer HQ

A desktop app that backtests the soccer prediction markets you can trade on Robinhood against
real match results, and ranks upcoming bets by confidence the way professionals do: fee-aware
edges against a pooled fair value, uncertainty, closing line value, liquidity filters, fractional
Kelly stakes. It covers every match played **after the 2026 World Cup** (final: 19 July 2026).

Robinhood's soccer event contracts (match winner: home / draw / away) clear on two exchanges:

* **Kalshi** – most league game markets (`KXEPLGAME`, `KXLALIGAGAME`, `KXBUNDESLIGAGAME`,
  `KXSERIEAGAME`, `KXLIGUE1GAME`, `KXMLSGAME`, `KXUCLGAME`, …). Kalshi's REST API is public, so the
  full pre-kickoff price history and the live order book are available.
* **Rothera** – Robinhood's own exchange, which took over some soccer listings in 2026. It has no
  public market-data API; prices you record from the app can be imported as CSV and analyzed the
  same way.

## Get the app

The repository's GitHub Actions workflow builds everything on GitHub's own machines, like Stock
Tracker HQ, so nobody needs Python installed:

1. GitHub → **Actions** → **Build executables** → **Run workflow**. Type a version such as
   `v0.2.1` to publish a Release, or leave it blank for artifacts only. Pushing a `v*` tag does the
   same.
2. Download from the run's **Artifacts** or the **Releases** page:

| platform | file | what it is |
|---|---|---|
| Windows | `RobinhoodSoccerHQ-<version>-windows-x64.exe` | the app: double-click, the HQ window opens |
| Windows | `rsa-<version>-windows-x64.exe` | the command-line version (PowerShell) |
| macOS (Apple Silicon) | `RobinhoodSoccerHQ-<version>-macos-arm64.dmg` | `Robinhood Soccer HQ.app` + `rsa` |
| macOS (Intel) | `RobinhoodSoccerHQ-<version>-macos-x64.dmg` | same, for Intel Macs |
| Linux | `RobinhoodSoccerHQ-<version>-linux-x64.tar.gz`, `rsa-<version>-linux-x64.tar.gz` | built on Ubuntu 22.04 (glibc 2.35+) |

The builds are unsigned. Windows SmartScreen asks once (*More info → Run anyway*). On a Mac, open
the DMG, drag **Robinhood Soccer HQ** onto the **Applications** alias next to it, then clear the
quarantine flag once in Terminal (or use *System Settings → Privacy & Security → Open Anyway*):

```bash
xattr -dr com.apple.quarantine "/Applications/Robinhood Soccer HQ.app"
```

The app starts a local server on 127.0.0.1 and opens the HQ as an app-style window in Chrome or
Edge (falling back to your default browser). Nothing is sent anywhere except the data sources
below and, when you ask, GitHub for update checks. It quits when you close the window (or press
Quit). Data, settings and reports live in `~/.robinhood-soccer-hq` (`RSA_HOME` to relocate).

## The HQ

* **Dashboard** – data freshness, the headline verdicts, venue-vs-closing-line accuracy, the
  professional strategy's ROI and closing line value, picks ready, per-league data status, the
  pooling weights (what the fair value trusts).
* **Picks** – upcoming contracts that pass every rule, with fill price, fee, fair probability,
  edge, a 0–100 confidence score and tier (A/B/C), the Kelly stake and contract count, and *why*
  (source agreement, spread, freshness, z-score). Positive-edge contracts that were blocked are
  listed with the rule that blocked them.
* **Backtest** – calibration of venue prices, ROI by minimum edge, realized ROI by confidence tier
  and by predicted-edge decile (the proof that the score ranks bets), accuracy of every
  probability source vs results and vs the closing line, systematic bias by outcome and league,
  naive rules, and every bet the professional rules would have placed with its closing line value.
* **Matches** – every priced match: venue last/ask/bid/close, pooled fair value with uncertainty,
  decision-time and closing bookmaker lines, Poisson and Elo, volume, rest days.
* **Settings** – leagues, dates, fee model, fills, bankroll, Kelly fraction, caps, minimum
  confidence, theme, optional Kalshi API key, update check.

Buttons in the top bar run the jobs: **Fetch** (results + odds + prices for the settings window,
then a backtest), **Backtest** (re-analyze offline with new settings), **Picks** (rank upcoming
contracts). **Demo** runs everything on synthetic data with planted biases so you can see what a
finding looks like without internet; the demo source is clearly labelled and never a real
recommendation.

## How the numbers are made

1. **Data.** Results and kickoff times from ESPN's scoreboard feed; opening and closing bookmaker
   odds from football-data.co.uk (Pinnacle closing `PSC*` is the sharpest public benchmark;
   `fixtures.csv` gives current odds for upcoming games); venue prices from Kalshi's trade tape,
   hourly bid/ask candles and the live order book. Entry snapshots are taken at kickoff or
   `minutes_before` earlier; the closing quote at kickoff is kept separately for CLV.
2. **No look-ahead.** When the entry is before kickoff, only the pre-match bookmaker line is used
   as a source; the closing line is admissible only at kickoff and otherwise appears only in the
   CLV columns. Models and pooling weights are fitted walk-forward on matches that finished before
   the one being priced.
3. **Fair value.** A log-linear pool of the bookmaker line, the venue's normalized price, a
   per-league Poisson/Dixon-Coles model and Elo (per-league home advantage, season-boundary
   regression, promoted teams seeded at relegated-team level). Weights and per-outcome intercepts
   are fitted by log loss with recency weighting and shrinkage to a prior that trusts the
   bookmaker most, bootstrapped by matchday for uncertainty, with floors that widen when the pool
   is on thin data or the decision is long before kickoff.
4. **Edge and confidence.** For each YES/NO contract: fee-aware edge at the fill (ask for YES,
   1 − bid for NO), its z-score and 20th percentile, edge vs the quote mid, the bookmaker line's
   own edge, agreement between independent sources, spread, volume, staleness, price band.
   Confidence = edge significance (35; full marks at z = 1.5) + edge size (15; full at 6 pts) + agreement (20) +
   liquidity (15) + price band (10) + freshness (5), scaled down on thin data or fatigue mismatches. Tiers: A ≥ 75,
   B ≥ 60, C ≥ 45.
5. **Discipline.** Gates: consistent three-way quotes, spread ≤ 6c, price 0.10–0.90, last trade
   ≤ 48 h old, conservative edge ≥ 0, edge vs mid ≥ 1c, the bookmaker line alone must not disagree.
   One bet per match, fractional Kelly (default ¼) with per-bet and per-day caps, fees computed at
   the lot size, minimum lot 10 contracts.
6. **Proof.** Brier and log loss with a paired test, calibration, cluster-bootstrap ROI intervals
   (by match and matchday), realized ROI by tier and by predicted-edge decile with Spearman rho,
   closing line value vs the venue's own close and vs Pinnacle, and distance of each source to the
   closing line.

Fees default to Robinhood's June 2026 schedule: commission `0.10 × p × (1 − p)` per contract
(`0.05` with Gold), rounded up to the cent per order, plus a $0.01 exchange fee.

## Command line

```bash
pip install -e ".[dev]"
rsa hq                          # the app window
rsa demo                        # synthetic end-to-end run -> reports/demo/{report,picks}.md
rsa run --leagues epl,laliga,bundesliga,seriea,ligue1,mls --data-dir data/live
rsa picks --data-dir data/live --bankroll 1000 --min-confidence 60
rsa backtest --data-dir data/live --fees robinhood_gold --minutes-before 360
rsa series                      # list Kalshi soccer series tickers
rsa menu                        # the text menu
```

Reports go to `reports/<data-dir name>/`: `report.md`, `picks.md`, `summary.json`, `joined.csv`,
`pro_portfolio.csv`, `pro_candidates.csv`, `picks.csv`, `picks_candidates.csv`, `bets_*.csv`.

### Importing prices from Robinhood / Rothera

A CSV with columns `league,team_a,team_b,outcome_label,price` (plus optional `venue,event_id,
market_ticker,yes_bid,yes_ask,snapshot_time,kickoff,volume,result,close_price`). See `rsa/prices.py`.

## Building locally

```bat
build.bat            :: Windows: venv + install + tests + release\RobinhoodSoccerHQ.exe and release\rsa.exe
./build.sh           #  macOS/Linux: the same, plus "Robinhood Soccer HQ.app" on macOS
```

PyInstaller does not cross-compile; build each platform on itself or use the GitHub workflow.
`python scripts/set_version.py v0.2.1` stamps a version. Tests: `pytest`.

## Status and caveats

* No live data has been analyzed in this repository yet: it was built in a sandbox whose network
  blocks Kalshi, ESPN and football-data.co.uk. All committed reports are from synthetic data.
* Six weeks of post-World-Cup football is a few hundred matches; every interval will be wide.
  Positive closing line value over 50+ bets is the first thing to look for, not ROI.
* Kalshi archives old settled markets to `/historical/*`; the client reads both tiers. Series
  tickers for Europa/Conference League, Leagues Cup and Liga MX are inferred, not verified.
* ESPN's scoreboard endpoint is unofficial. MLS has no football-data odds, so its fair value leans
  on the venue price and the models; its picks deserve extra skepticism.
* The packaged app excludes the optional Kalshi API-key signing (`cryptography`); public market
  data needs no key.

## Project layout

```
rsa/hq/           the HQ: server.py (local API + window), state.py (settings, jobs), jobs.py, ui/ (html/css/js)
rsa/pro.py        pooled fair value, uncertainty, Kelly, confidence, gates, portfolio, CLV, deciles
rsa/backtest.py   scoring rules, calibration, bias tables, strategies, bootstrap; runs the pro strategy
rsa/models.py     Elo (per-league home advantage, season boundary) + per-league Poisson/Dixon-Coles
rsa/kalshi.py     Kalshi client (live + historical tiers), entry/closing snapshots, open markets
rsa/results.py    ESPN + football-data.co.uk loaders (incl. fixtures.csv), de-vigging
rsa/matching.py   join priced events to fixtures; decision-time vs closing book references
rsa/pipeline.py   collect -> save -> analyze -> write; upcoming fixtures -> picks
rsa/report.py     markdown reports and the JSON summary the HQ reads
rsa/synth.py      synthetic raw-shaped data + offline Kalshi client (demo)
rsa/cli.py        commands; scripts/, rsa.spec, build.bat/.sh, .github/workflows/build.yml: packaging
tests/            pytest suite
```
