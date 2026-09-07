# Robinhood soccer prediction-market backtest

> **SYNTHETIC DEMO DATA.** Every price and score in this report was simulated by `rsa demo` with planted biases so you can see what the analysis looks like. Nothing here is a real finding.

Generated 2026-09-07 00:15 UTC. Window **2026-07-20 → 2026-09-06** (post-World-Cup). Fee model: **robinhood**; fills at **ask**.

- Fixtures in window: 228 (228 completed); warm-up results for models: 1992
- Venue price snapshots: 684; priced events matched to a fixture: 228; unmatched events: 0

## Verdict

- Venue prices and the closing line are statistically indistinguishable in accuracy (mean Brier gap -0.012, t=-1.6, n=228).
- Versus the closing line the venue prices the draw below fair on average (-0.8 pts, t=-2.6, n=228).
- Versus the closing line the venue prices the away above fair on average (+1.5 pts, t=4.7, n=228).
- The **book**-based strategy's ROI of -5.4% (n=77) is not distinguishable from zero (95% CI -24.2% to +13.0%).
- The **elo**-based strategy's ROI of +2.7% (n=258) is not distinguishable from zero (95% CI -10.7% to +16.6%).
- The **poisson**-based strategy's ROI of +6.8% (n=219) is not distinguishable from zero (95% CI -6.3% to +19.1%).
- The **blend**-based strategy's ROI of -11.9% (n=85) is not distinguishable from zero (95% CI -30.7% to +7.8%).

## Accuracy: venue vs reference probabilities

Multiclass Brier score and log loss over the three outcomes (lower is better). `mktn` = venue prices normalized to sum to 1; `book` = de-vigged closing odds (Pinnacle when available); `elo`/`poisson` = walk-forward models; `blend` = 30% Poisson / 70% book.

| source | n | brier | logloss |
|---|---|---|---|
| mktn | 228 | 0.616 | 1.033 |
| book | 228 | 0.628 | 1.051 |
| elo | 228 | 0.626 | 1.041 |
| poisson | 228 | 0.631 | 1.046 |
| blend | 228 | 0.624 | 1.042 |


## Calibration of venue prices

Each outcome contract bucketed by its pre-kickoff YES price. `diff` = hit rate − mean price; a positive diff means contracts in that bucket paid out more often than their price implied (cheap).

| bin | n | mean_price | hit_rate | diff | se |
|---|---|---|---|---|---|
| [0.0, 0.1) | 10 | 0.073 | 0.000 | -0.073 | 0.082 |
| [0.1, 0.2) | 106 | 0.160 | 0.264 | 0.105 | 0.036 |
| [0.2, 0.3) | 227 | 0.242 | 0.216 | -0.027 | 0.028 |
| [0.3, 0.4) | 134 | 0.344 | 0.343 | -0.000 | 0.041 |
| [0.4, 0.5) | 78 | 0.446 | 0.449 | 0.003 | 0.056 |
| [0.5, 0.6) | 58 | 0.541 | 0.500 | -0.041 | 0.065 |
| [0.6, 0.7) | 47 | 0.636 | 0.532 | -0.104 | 0.070 |
| [0.7, 0.8) | 18 | 0.736 | 0.611 | -0.125 | 0.104 |
| [0.8, 0.9) | 4 | 0.823 | 0.750 | -0.073 | 0.191 |
| [0.9, 1.0) | 2 | 0.925 | 1.000 | 0.075 | 0.186 |


## Systematic bias by outcome

| outcome | n | mean_price | hit_rate | diff | se | z |
|---|---|---|---|---|---|---|
| away | 228 | 0.330 | 0.276 | -0.054 | 0.031 | -1.721 |
| draw | 228 | 0.245 | 0.294 | 0.049 | 0.028 | 1.727 |
| home | 228 | 0.448 | 0.430 | -0.018 | 0.033 | -0.550 |


## By league

`overround` = sum of the three YES prices − 1 (the venue's built-in margin); `brier_*` lower is better.

| league | n | overround | draw_price | draw_rate | home_price | home_rate | brier_mktn | brier_book |
|---|---|---|---|---|---|---|---|---|
| bundesliga | 18 | 0.027 | 0.229 | 0.222 | 0.482 | 0.333 | 0.669 | 0.696 |
| epl | 30 | 0.031 | 0.231 | 0.267 | 0.488 | 0.433 | 0.633 | 0.637 |
| laliga | 30 | 0.004 | 0.258 | 0.233 | 0.381 | 0.333 | 0.514 | 0.553 |
| ligue1 | 27 | 0.018 | 0.251 | 0.333 | 0.456 | 0.407 | 0.607 | 0.612 |
| mls | 103 | 0.028 | 0.249 | 0.282 | 0.445 | 0.505 | 0.624 | 0.627 |
| seriea | 20 | 0.013 | 0.227 | 0.500 | 0.465 | 0.300 | 0.667 | 0.693 |


## Venue price minus closing line

Mean of (normalized venue probability − de-vigged closing probability) per outcome. Negative = venue cheaper than the sharp line.

| outcome | n | mean_diff | sd | t |
|---|---|---|---|---|
| home | 228 | -0.0069 | 0.0590 | -1.7678 |
| draw | 228 | -0.0077 | 0.0450 | -2.5845 |
| away | 228 | 0.0146 | 0.0472 | 4.6747 |


## Naive rules (no model), after fees

Buy one YES contract on every match under a fixed rule (`no_draw` buys NO on the draw). ROI = profit / dollars risked, with a bootstrap 95% interval.

| rule | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price |
|---|---|---|---|---|---|---|---|---|
| home | 228 | 114.340 | -16.340 | -14.3% | -27.2% | -2.3% | 43.0% | 0.464 |
| draw | 228 | 67.500 | -0.500 | -0.7% | -20.8% | +20.3% | 29.4% | 0.262 |
| away | 228 | 87.150 | -24.150 | -27.7% | -42.7% | -12.5% | 27.6% | 0.347 |
| favorite | 228 | 134.150 | -17.150 | -12.8% | -23.8% | -1.9% | 51.3% | 0.549 |
| underdog | 228 | 58.710 | 1.290 | +2.2% | -19.8% | +25.2% | 26.3% | 0.226 |
| no_draw | 228 | 183.230 | -22.230 | -12.1% | -19.8% | -4.8% | 70.6% | 0.772 |


## Reference-driven strategies, after fees

Buy any YES or NO contract whose reference probability exceeds fill price + fee by at least 0.03.

| reference | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge | p_value_profit_le_0 |
|---|---|---|---|---|---|---|---|---|---|---|
| book | 77 | 43.360 | -2.360 | -5.4% | -24.2% | +13.0% | 53.2% | 0.527 | 0.059 | 0.711 |
| elo | 258 | 105.120 | 2.880 | +2.7% | -10.7% | +16.6% | 41.9% | 0.372 | 0.091 | 0.372 |
| poisson | 219 | 107.640 | 7.360 | +6.8% | -6.3% | +19.1% | 52.5% | 0.455 | 0.089 | 0.154 |
| blend | 85 | 44.270 | -5.270 | -11.9% | -30.7% | +7.8% | 45.9% | 0.484 | 0.060 | 0.874 |


### Edge threshold sweep — book

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 243 | 148.420 | -11.420 | -7.7% | -17.9% | +2.3% | 56.4% | 0.577 | 0.027 |
| 0.020 | 111 | 67.190 | -7.190 | -10.7% | -24.4% | +4.8% | 54.1% | 0.570 | 0.049 |
| 0.040 | 50 | 29.110 | -2.110 | -7.2% | -27.5% | +14.3% | 54.0% | 0.546 | 0.073 |
| 0.060 | 21 | 11.040 | -2.040 | -18.5% | -55.9% | +20.4% | 42.9% | 0.489 | 0.104 |
| 0.080 | 10 | 5.410 | -1.410 | -26.1% | -81.5% | +38.1% | 40.0% | 0.504 | 0.140 |
| 0.100 | 3 | 1.360 | -0.360 | -26.5% | -100.0% | +56.3% | 33.3% | 0.417 | 0.271 |


### Edge threshold sweep — elo

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 375 | 155.640 | 3.360 | +2.2% | -9.3% | +13.8% | 42.4% | 0.380 | 0.067 |
| 0.020 | 291 | 118.710 | 4.290 | +3.6% | -9.3% | +16.3% | 42.3% | 0.372 | 0.083 |
| 0.040 | 214 | 84.580 | 8.420 | +10.0% | -5.6% | +26.4% | 43.5% | 0.359 | 0.102 |
| 0.060 | 149 | 56.230 | 1.770 | +3.1% | -16.0% | +23.7% | 38.9% | 0.342 | 0.125 |
| 0.080 | 119 | 44.540 | 1.460 | +3.3% | -19.1% | +26.0% | 38.7% | 0.339 | 0.139 |
| 0.100 | 94 | 34.750 | 1.250 | +3.6% | -21.6% | +29.5% | 38.3% | 0.334 | 0.151 |


### Edge threshold sweep — poisson

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 352 | 177.780 | 6.220 | +3.5% | -5.7% | +13.1% | 52.3% | 0.469 | 0.060 |
| 0.020 | 254 | 126.690 | 7.310 | +5.8% | -6.0% | +17.9% | 52.8% | 0.462 | 0.080 |
| 0.040 | 184 | 90.030 | 3.970 | +4.4% | -10.0% | +18.5% | 51.1% | 0.452 | 0.099 |
| 0.060 | 125 | 58.370 | 0.630 | +1.1% | -17.1% | +18.6% | 47.2% | 0.429 | 0.122 |
| 0.080 | 89 | 39.820 | -3.820 | -9.6% | -30.4% | +12.8% | 40.4% | 0.410 | 0.143 |
| 0.100 | 71 | 30.590 | -3.590 | -11.7% | -35.8% | +12.4% | 38.0% | 0.393 | 0.156 |


### Edge threshold sweep — blend

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 233 | 131.270 | -2.270 | -1.7% | -12.7% | +9.7% | 55.4% | 0.528 | 0.030 |
| 0.020 | 119 | 64.530 | -4.530 | -7.0% | -23.8% | +9.2% | 50.4% | 0.505 | 0.050 |
| 0.040 | 54 | 27.020 | -4.020 | -14.9% | -39.3% | +11.1% | 42.6% | 0.463 | 0.075 |
| 0.060 | 30 | 14.700 | -2.700 | -18.4% | -51.3% | +15.4% | 40.0% | 0.452 | 0.096 |
| 0.080 | 11 | 4.850 | -0.850 | -17.5% | -77.1% | +35.1% | 36.4% | 0.404 | 0.141 |
| 0.100 | 4 | 1.020 | -1.020 | -100.0% | -100.0% | -100.0% | 0.0% | 0.222 | 0.234 |


### Breakdown — book_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 30 | 18.540 | -0.540 | -2.9% | -28.9% | +23.2% | 60.0% |
| draw | 19 | 9.260 | -1.260 | -13.6% | -55.6% | +37.0% | 42.1% |
| home | 28 | 15.560 | -0.560 | -3.6% | -36.8% | +19.4% | 53.6% |


### Breakdown — book_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 50 | 33.050 | -2.050 | -6.2% | -25.4% | +11.6% | 62.0% |
| yes | 27 | 10.310 | -0.310 | -3.0% | -47.3% | +43.8% | 37.0% |


### Breakdown — book_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 5 | 3.630 | -0.630 | -17.4% | -74.1% | +47.1% | 60.0% |
| epl | 8 | 4.340 | -1.340 | -30.9% | -91.1% | +37.5% | 37.5% |
| laliga | 9 | 4.280 | -1.280 | -29.9% | -79.6% | +17.3% | 33.3% |
| ligue1 | 7 | 3.880 | -0.880 | -22.7% | -100.0% | +40.3% | 42.9% |
| mls | 41 | 23.830 | 3.170 | +13.3% | -7.7% | +33.4% | 65.9% |
| seriea | 7 | 3.400 | -1.400 | -41.2% | -100.0% | +39.5% | 28.6% |


### Breakdown — elo_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 92 | 38.120 | 5.880 | +15.4% | -8.2% | +39.5% | 47.8% |
| draw | 55 | 24.780 | -4.780 | -19.3% | -42.2% | +5.3% | 36.4% |
| home | 111 | 42.220 | 1.780 | +4.2% | -18.9% | +28.2% | 39.6% |


### Breakdown — elo_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 147 | 76.260 | -0.260 | -0.3% | -14.2% | +15.4% | 51.7% |
| yes | 111 | 28.860 | 3.140 | +10.9% | -19.2% | +44.7% | 28.8% |


### Breakdown — elo_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 18 | 6.950 | 1.050 | +15.1% | -39.5% | +66.7% | 44.4% |
| epl | 32 | 14.710 | -0.710 | -4.8% | -42.4% | +33.4% | 43.8% |
| laliga | 23 | 11.840 | -2.840 | -24.0% | -55.9% | +5.7% | 39.1% |
| ligue1 | 23 | 10.740 | 0.260 | +2.4% | -35.3% | +42.6% | 47.8% |
| mls | 143 | 52.470 | 9.530 | +18.2% | -1.6% | +39.9% | 43.4% |
| seriea | 19 | 8.410 | -4.410 | -52.4% | -87.5% | -11.5% | 21.1% |


### Breakdown — poisson_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 97 | 51.240 | 6.760 | +13.2% | -4.5% | +28.3% | 59.8% |
| draw | 28 | 14.480 | -0.480 | -3.3% | -40.6% | +39.0% | 50.0% |
| home | 94 | 41.920 | 1.080 | +2.6% | -19.2% | +23.2% | 45.7% |


### Breakdown — poisson_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 125 | 73.420 | 5.580 | +7.6% | -6.1% | +23.3% | 63.2% |
| yes | 94 | 34.220 | 1.780 | +5.2% | -21.8% | +31.0% | 38.3% |


### Breakdown — poisson_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 11 | 5.710 | 0.290 | +5.1% | -46.0% | +56.0% | 54.5% |
| epl | 31 | 15.380 | 0.620 | +4.0% | -29.9% | +45.2% | 51.6% |
| laliga | 27 | 14.670 | -0.670 | -4.6% | -35.7% | +25.4% | 51.9% |
| ligue1 | 17 | 8.660 | 1.340 | +15.5% | -25.0% | +49.3% | 58.8% |
| mls | 112 | 51.550 | 7.450 | +14.5% | -5.1% | +35.0% | 52.7% |
| seriea | 21 | 11.670 | -1.670 | -14.3% | -54.7% | +27.4% | 47.6% |


### Breakdown — blend_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 38 | 21.630 | -0.630 | -2.9% | -29.0% | +18.4% | 55.3% |
| draw | 16 | 8.570 | 0.430 | +5.0% | -50.4% | +71.3% | 56.2% |
| home | 31 | 14.070 | -5.070 | -36.0% | -66.5% | -7.2% | 29.0% |


### Breakdown — blend_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 55 | 32.980 | -5.980 | -18.1% | -38.9% | +0.7% | 49.1% |
| yes | 30 | 11.290 | 0.710 | +6.3% | -40.4% | +52.6% | 40.0% |


### Breakdown — blend_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 6 | 2.990 | 0.010 | +0.3% | -71.4% | +69.9% | 50.0% |
| epl | 9 | 4.600 | -1.600 | -34.8% | -81.1% | +31.2% | 33.3% |
| laliga | 11 | 5.820 | -1.820 | -31.3% | -81.1% | +11.3% | 36.4% |
| ligue1 | 7 | 3.200 | -0.200 | -6.2% | -68.3% | +51.6% | 42.9% |
| mls | 42 | 22.830 | 0.170 | +0.7% | -24.0% | +27.5% | 54.8% |
| seriea | 10 | 4.830 | -1.830 | -37.9% | -82.4% | +40.3% | 30.0% |


## Largest-edge bets — poisson reference

| kickoff | league | home | away | outcome | side | price | fee | fair | edge | won | profit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-14 16:00 | laliga | Real Madrid | Real Betis | home | yes | 0.130 | 0.030 | 0.684 | 0.524 | False | -0.160 |
| 2026-08-15 23:00 | mls | Houston Dynamo FC | Sporting Kansas City | home | yes | 0.300 | 0.040 | 0.633 | 0.293 | False | -0.340 |
| 2026-08-22 23:00 | mls | Portland Timbers | New England Revolution | home | yes | 0.240 | 0.030 | 0.533 | 0.263 | False | -0.270 |
| 2026-08-30 02:00 | mls | Atlanta United FC | Inter Miami CF | home | no | 0.400 | 0.040 | 0.678 | 0.238 | False | -0.440 |
| 2026-07-26 00:00 | mls | Orlando City SC | Inter Miami CF | home | no | 0.400 | 0.040 | 0.666 | 0.226 | True | 0.560 |
| 2026-08-28 13:00 | bundesliga | Eintracht Frankfurt | Werder Bremen | home | no | 0.290 | 0.040 | 0.553 | 0.223 | False | -0.330 |
| 2026-08-15 23:00 | mls | Chicago Fire FC | Vancouver Whitecaps | home | no | 0.330 | 0.040 | 0.592 | 0.222 | False | -0.370 |
| 2026-08-09 02:00 | mls | Atlanta United FC | FC Cincinnati | away | yes | 0.220 | 0.030 | 0.470 | 0.220 | False | -0.250 |
| 2026-08-01 23:00 | mls | Minnesota United FC | New York Red Bulls | home | yes | 0.190 | 0.030 | 0.440 | 0.220 | False | -0.220 |
| 2026-08-23 18:00 | seriea | Internazionale | Napoli | home | yes | 0.450 | 0.040 | 0.709 | 0.219 | False | -0.490 |
| 2026-08-30 00:00 | mls | Portland Timbers | New York Red Bulls | away | no | 0.440 | 0.040 | 0.697 | 0.217 | True | 0.520 |
| 2026-08-09 00:00 | mls | Nashville SC | New York Red Bulls | away | no | 0.300 | 0.040 | 0.548 | 0.208 | False | -0.340 |
| 2026-08-22 23:00 | mls | Portland Timbers | New England Revolution | away | no | 0.520 | 0.040 | 0.756 | 0.196 | True | 0.440 |
| 2026-08-16 14:00 | epl | Crystal Palace | Manchester City | home | yes | 0.270 | 0.030 | 0.494 | 0.194 | False | -0.300 |
| 2026-08-15 23:00 | mls | Houston Dynamo FC | Sporting Kansas City | away | no | 0.650 | 0.040 | 0.880 | 0.190 | False | -0.690 |


## How to read this

- A real, exploitable edge needs three things at once: a bias that is stable across leagues/weeks, ROI whose confidence interval excludes zero **after fees**, and fills at the ask (not the last trade).
- Brier/log-loss differences of < 0.005 are noise at this sample size.
- Model-based strategies (Elo, Poisson) are weak references; `book` (the closing line) is the strongest public benchmark. If a strategy only wins against Elo, that is not evidence of an edge.
- Rothera-routed Robinhood contracts have no public API; import them with `--prices-csv` to include them.
