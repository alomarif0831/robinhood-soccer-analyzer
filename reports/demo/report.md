# Robinhood soccer prediction-market backtest

> **SYNTHETIC DEMO DATA.** Every price and score in this report was simulated by `rsa demo` with planted biases so you can see what the analysis looks like. Nothing here is a real finding.

Generated 2026-09-07 01:07 UTC. Window **2026-07-20 → 2026-09-06** (post-World-Cup). Fee model: **robinhood**; fills at **ask**.

- Fixtures in window: 228 (228 completed); warm-up results for models: 1992
- Venue price snapshots: 684; priced events matched to a fixture: 228; unmatched events: 0

## Verdict

- Venue prices and the closing line are statistically indistinguishable in accuracy (mean Brier gap -0.004, t=-0.6, n=228).
- Versus the closing line the venue prices the draw below fair on average (-2.3 pts, t=-7.6, n=228).
- Versus the closing line the venue prices the away above fair on average (+2.2 pts, t=7.1, n=228).
- Professional rules would have placed 10 bets: flat ROI -3.1% (95% CI -30.1% to +17.9%), Kelly ROI -9.8%, max drawdown 3.6%, mean CLV vs venue close +0.3 pts.
- The **book**-based strategy's ROI of -8.8% (n=120) is not distinguishable from zero (95% CI -23.6% to +6.3%).
- Betting on the **elo** reference lost money after fees: ROI -14.6% (95% CI -29.0% to -1.2%, n=263).
- The **poisson**-based strategy's ROI of +0.2% (n=261) is not distinguishable from zero (95% CI -10.2% to +10.4%).
- The **blend**-based strategy's ROI of -2.0% (n=108) is not distinguishable from zero (95% CI -17.9% to +14.0%).
- The **pro**-based strategy's ROI of -4.9% (n=68) is not distinguishable from zero (95% CI -23.3% to +13.8%).

## Accuracy: venue vs reference probabilities

Multiclass Brier score and log loss over the three outcomes (lower is better). `mktn` = venue prices normalized to sum to 1; `book` = de-vigged closing odds (Pinnacle when available); `elo`/`poisson` = walk-forward models; `blend` = 30% Poisson / 70% book.

| source | n | brier | logloss |
|---|---|---|---|
| mktn | 228 | 0.568 | 0.955 |
| book | 228 | 0.571 | 0.959 |
| elo | 228 | 0.605 | 1.012 |
| poisson | 228 | 0.579 | 0.975 |
| blend | 228 | 0.568 | 0.957 |
| pro | 228 | 0.570 | 0.959 |


## Calibration of venue prices

Each outcome contract bucketed by its pre-kickoff YES price. `diff` = hit rate − mean price; a positive diff means contracts in that bucket paid out more often than their price implied (cheap).

| bin | n | mean_price | hit_rate | diff | se |
|---|---|---|---|---|---|
| [0.0, 0.1) | 9 | 0.062 | 0.000 | -0.062 | 0.081 |
| [0.1, 0.2) | 123 | 0.162 | 0.146 | -0.016 | 0.033 |
| [0.2, 0.3) | 241 | 0.242 | 0.220 | -0.022 | 0.028 |
| [0.3, 0.4) | 110 | 0.344 | 0.373 | 0.028 | 0.045 |
| [0.4, 0.5) | 65 | 0.451 | 0.477 | 0.026 | 0.062 |
| [0.5, 0.6) | 64 | 0.549 | 0.562 | 0.013 | 0.062 |
| [0.6, 0.7) | 50 | 0.634 | 0.660 | 0.026 | 0.068 |
| [0.7, 0.8) | 17 | 0.726 | 0.647 | -0.079 | 0.108 |
| [0.8, 0.9) | 3 | 0.830 | 1.000 | 0.170 | 0.217 |
| [0.9, 1.0) | 2 | 0.920 | 1.000 | 0.080 | 0.192 |


## Systematic bias by outcome

| outcome | n | mean_price | hit_rate | diff | se | z |
|---|---|---|---|---|---|---|
| away | 228 | 0.331 | 0.316 | -0.015 | 0.031 | -0.484 |
| draw | 228 | 0.226 | 0.241 | 0.016 | 0.028 | 0.561 |
| home | 228 | 0.450 | 0.443 | -0.007 | 0.033 | -0.213 |


## By league

`overround` = sum of the three YES prices − 1 (the venue's built-in margin); `brier_*` lower is better.

| league | n | overround | draw_price | draw_rate | home_price | home_rate | brier_mktn | brier_book |
|---|---|---|---|---|---|---|---|---|
| bundesliga | 18 | 0.035 | 0.211 | 0.167 | 0.490 | 0.611 | 0.525 | 0.538 |
| epl | 30 | 0.015 | 0.214 | 0.267 | 0.486 | 0.433 | 0.640 | 0.642 |
| laliga | 30 | -0.028 | 0.216 | 0.367 | 0.400 | 0.400 | 0.682 | 0.681 |
| ligue1 | 27 | 0.023 | 0.243 | 0.296 | 0.477 | 0.444 | 0.573 | 0.577 |
| mls | 103 | 0.002 | 0.233 | 0.204 | 0.436 | 0.447 | 0.524 | 0.527 |
| seriea | 20 | 0.021 | 0.213 | 0.200 | 0.469 | 0.350 | 0.548 | 0.554 |


## Venue price minus closing line

Mean of (normalized venue probability − de-vigged closing probability) per outcome. Negative = venue cheaper than the sharp line.

| outcome | n | mean_diff | sd | t |
|---|---|---|---|---|
| home | 228 | 0.0011 | 0.0541 | 0.3095 |
| draw | 228 | -0.0229 | 0.0455 | -7.5881 |
| away | 228 | 0.0218 | 0.0465 | 7.0672 |


## Naive rules (no model), after fees

Buy one YES contract on every match under a fixed rule (`no_draw` buys NO on the draw). ROI = profit / dollars risked, with a bootstrap 95% interval.

| rule | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price |
|---|---|---|---|---|---|---|---|---|
| home | 228 | 114.740 | -13.740 | -12.0% | -23.5% | +0.4% | 44.3% | 0.466 |
| draw | 228 | 62.760 | -7.760 | -12.4% | -31.8% | +6.4% | 24.1% | 0.243 |
| away | 228 | 87.190 | -15.190 | -17.4% | -32.0% | -2.9% | 31.6% | 0.347 |
| favorite | 228 | 134.570 | -5.570 | -4.1% | -14.8% | +7.0% | 56.6% | 0.551 |
| underdog | 228 | 56.830 | -12.830 | -22.6% | -42.6% | -2.9% | 19.3% | 0.218 |
| no_draw | 228 | 187.350 | -14.350 | -7.7% | -14.0% | -1.2% | 75.9% | 0.791 |


## Reference-driven strategies, after fees

Buy any YES or NO contract whose reference probability exceeds fill price + fee by at least 0.03.

| reference | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge | p_value_profit_le_0 |
|---|---|---|---|---|---|---|---|---|---|---|
| book | 120 | 64.720 | -5.720 | -8.8% | -23.6% | +6.3% | 49.2% | 0.505 | 0.054 | 0.876 |
| elo | 263 | 98.390 | -14.390 | -14.6% | -29.0% | -1.2% | 31.9% | 0.339 | 0.093 | 0.984 |
| poisson | 261 | 134.730 | 0.270 | +0.2% | -10.2% | +10.4% | 51.7% | 0.481 | 0.088 | 0.478 |
| blend | 108 | 57.160 | -1.160 | -2.0% | -17.9% | +14.0% | 51.9% | 0.494 | 0.060 | 0.599 |
| pro | 68 | 39.970 | -1.970 | -4.9% | -23.3% | +13.8% | 55.9% | 0.553 | 0.055 | 0.707 |


### Edge threshold sweep — book

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 290 | 161.790 | -1.790 | -1.1% | -9.7% | +7.7% | 55.2% | 0.524 | 0.030 |
| 0.020 | 157 | 87.450 | -4.450 | -5.1% | -17.4% | +7.5% | 52.9% | 0.522 | 0.047 |
| 0.040 | 81 | 40.990 | -1.990 | -4.9% | -23.9% | +15.0% | 48.1% | 0.471 | 0.064 |
| 0.060 | 38 | 17.410 | -1.410 | -8.1% | -39.4% | +24.1% | 42.1% | 0.423 | 0.082 |
| 0.080 | 16 | 6.440 | 0.560 | +8.7% | -38.3% | +45.6% | 43.8% | 0.369 | 0.103 |
| 0.100 | 6 | 2.170 | -0.170 | -7.8% | -100.0% | +53.8% | 33.3% | 0.330 | 0.125 |


### Edge threshold sweep — elo

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 403 | 153.240 | -31.240 | -20.4% | -31.0% | -9.0% | 30.3% | 0.345 | 0.066 |
| 0.020 | 305 | 114.090 | -16.090 | -14.1% | -26.9% | -1.5% | 32.1% | 0.339 | 0.084 |
| 0.040 | 233 | 86.700 | -15.700 | -18.1% | -32.7% | -3.8% | 30.5% | 0.336 | 0.101 |
| 0.060 | 169 | 61.260 | -3.260 | -5.3% | -22.2% | +13.8% | 34.3% | 0.327 | 0.120 |
| 0.080 | 129 | 46.320 | -3.320 | -7.2% | -28.5% | +13.9% | 33.3% | 0.324 | 0.136 |
| 0.100 | 93 | 33.020 | -1.020 | -3.1% | -27.4% | +20.6% | 34.4% | 0.320 | 0.154 |


### Edge threshold sweep — poisson

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 384 | 194.330 | -7.330 | -3.8% | -12.9% | +5.2% | 48.7% | 0.471 | 0.065 |
| 0.020 | 302 | 156.030 | -1.030 | -0.7% | -10.2% | +8.9% | 51.3% | 0.481 | 0.080 |
| 0.040 | 214 | 110.190 | 3.810 | +3.5% | -8.4% | +14.7% | 53.3% | 0.479 | 0.100 |
| 0.060 | 157 | 79.570 | 3.430 | +4.3% | -8.2% | +17.7% | 52.9% | 0.470 | 0.119 |
| 0.080 | 110 | 53.350 | 5.650 | +10.6% | -6.8% | +29.5% | 53.6% | 0.448 | 0.139 |
| 0.100 | 89 | 43.280 | 3.720 | +8.6% | -11.6% | +28.2% | 52.8% | 0.449 | 0.151 |


### Edge threshold sweep — blend

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 281 | 146.300 | 1.700 | +1.2% | -8.7% | +11.5% | 52.7% | 0.486 | 0.032 |
| 0.020 | 150 | 80.180 | -1.180 | -1.5% | -14.3% | +12.1% | 52.7% | 0.499 | 0.050 |
| 0.040 | 77 | 40.170 | 0.830 | +2.1% | -16.8% | +20.7% | 53.2% | 0.486 | 0.070 |
| 0.060 | 38 | 17.730 | 1.270 | +7.2% | -23.8% | +37.9% | 50.0% | 0.431 | 0.091 |
| 0.080 | 21 | 9.090 | 0.910 | +10.0% | -32.7% | +48.8% | 47.6% | 0.398 | 0.110 |
| 0.100 | 10 | 4.150 | 1.850 | +44.6% | -23.7% | +100.4% | 60.0% | 0.378 | 0.133 |


### Edge threshold sweep — pro

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 216 | 124.020 | -0.020 | -0.0% | -10.3% | +10.2% | 57.4% | 0.540 | 0.025 |
| 0.020 | 92 | 53.400 | -1.400 | -2.6% | -18.5% | +12.8% | 56.5% | 0.546 | 0.047 |
| 0.040 | 45 | 26.040 | -3.040 | -11.7% | -36.0% | +11.6% | 51.1% | 0.544 | 0.066 |
| 0.060 | 21 | 11.490 | 1.510 | +13.1% | -22.6% | +48.3% | 61.9% | 0.511 | 0.085 |
| 0.080 | 11 | 5.920 | 1.080 | +18.2% | -30.9% | +62.2% | 63.6% | 0.501 | 0.099 |
| 0.100 | 3 | 1.660 | 1.340 | +80.7% | +42.9% | +117.4% | 100.0% | 0.513 | 0.140 |


### Breakdown — book_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 36 | 23.320 | -0.320 | -1.4% | -22.9% | +19.4% | 63.9% |
| draw | 32 | 10.480 | -4.480 | -42.7% | -80.5% | +1.3% | 18.8% |
| home | 52 | 30.920 | -0.920 | -3.0% | -25.2% | +18.3% | 57.7% |


### Breakdown — book_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 65 | 43.370 | -3.370 | -7.8% | -24.8% | +7.8% | 61.5% |
| yes | 55 | 21.350 | -2.350 | -11.0% | -38.2% | +18.0% | 34.5% |


### Breakdown — book_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 12 | 6.870 | -1.870 | -27.2% | -71.7% | +18.1% | 41.7% |
| epl | 11 | 5.770 | 0.230 | +4.0% | -53.3% | +73.1% | 54.5% |
| laliga | 19 | 7.570 | -0.570 | -7.5% | -51.9% | +30.8% | 36.8% |
| ligue1 | 12 | 6.520 | -1.520 | -23.3% | -71.0% | +30.7% | 41.7% |
| mls | 58 | 32.820 | -1.820 | -5.5% | -26.1% | +13.2% | 53.4% |
| seriea | 8 | 5.170 | -0.170 | -3.3% | -57.2% | +57.7% | 62.5% |


### Breakdown — elo_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 94 | 40.300 | -4.300 | -10.7% | -31.5% | +12.3% | 38.3% |
| draw | 49 | 14.450 | -1.450 | -10.0% | -44.8% | +27.0% | 26.5% |
| home | 120 | 43.640 | -8.640 | -19.8% | -43.3% | +3.3% | 29.2% |


### Breakdown — elo_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 136 | 66.570 | -7.570 | -11.4% | -27.8% | +6.8% | 43.4% |
| yes | 127 | 31.820 | -6.820 | -21.4% | -46.9% | +6.6% | 19.7% |


### Breakdown — elo_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 23 | 8.270 | -1.270 | -15.4% | -62.2% | +33.8% | 30.4% |
| epl | 32 | 13.780 | 0.220 | +1.6% | -36.0% | +45.9% | 43.8% |
| laliga | 38 | 15.660 | 2.340 | +14.9% | -19.4% | +50.1% | 47.4% |
| ligue1 | 23 | 10.310 | -3.310 | -32.1% | -68.7% | +4.3% | 30.4% |
| mls | 126 | 43.440 | -10.440 | -24.0% | -43.3% | -3.1% | 26.2% |
| seriea | 21 | 6.930 | -1.930 | -27.8% | -73.9% | +37.4% | 23.8% |


### Breakdown — poisson_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 101 | 54.940 | 2.060 | +3.7% | -12.3% | +19.9% | 56.4% |
| draw | 49 | 23.280 | -2.280 | -9.8% | -30.9% | +16.1% | 42.9% |
| home | 111 | 56.510 | 0.490 | +0.9% | -16.8% | +18.6% | 51.4% |


### Breakdown — poisson_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 142 | 89.770 | -0.770 | -0.9% | -11.5% | +10.4% | 62.7% |
| yes | 119 | 44.960 | 1.040 | +2.3% | -19.3% | +22.2% | 38.7% |


### Breakdown — poisson_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 16 | 7.720 | -1.720 | -22.3% | -63.9% | +30.6% | 37.5% |
| epl | 31 | 15.560 | -0.560 | -3.6% | -35.2% | +31.9% | 48.4% |
| laliga | 32 | 14.230 | 1.770 | +12.4% | -26.4% | +55.0% | 50.0% |
| ligue1 | 23 | 10.940 | -1.940 | -17.7% | -53.6% | +19.1% | 39.1% |
| mls | 139 | 77.800 | 6.200 | +8.0% | -4.0% | +19.1% | 60.4% |
| seriea | 20 | 8.480 | -3.480 | -41.0% | -83.0% | -1.5% | 25.0% |


### Breakdown — blend_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 35 | 21.360 | 3.640 | +17.0% | -7.3% | +39.1% | 71.4% |
| draw | 28 | 9.790 | -4.790 | -48.9% | -89.4% | -4.9% | 17.9% |
| home | 45 | 26.010 | -0.010 | -0.0% | -22.4% | +20.8% | 57.8% |


### Breakdown — blend_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 59 | 37.970 | 0.030 | +0.1% | -18.8% | +16.8% | 64.4% |
| yes | 49 | 19.190 | -1.190 | -6.2% | -34.6% | +22.4% | 36.7% |


### Breakdown — blend_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 9 | 4.240 | -1.240 | -29.2% | -78.4% | +30.2% | 33.3% |
| epl | 11 | 5.410 | -1.410 | -26.1% | -82.2% | +47.2% | 36.4% |
| laliga | 14 | 4.990 | -0.990 | -19.8% | -75.2% | +26.3% | 28.6% |
| ligue1 | 10 | 4.840 | -0.840 | -17.4% | -79.6% | +40.5% | 40.0% |
| mls | 53 | 32.040 | 3.960 | +12.4% | -7.3% | +26.9% | 67.9% |
| seriea | 11 | 5.640 | -0.640 | -11.3% | -63.8% | +51.7% | 45.5% |


### Breakdown — pro_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 20 | 13.080 | 0.920 | +7.0% | -25.8% | +41.0% | 70.0% |
| draw | 12 | 3.900 | -1.900 | -48.7% | -100.0% | +37.6% | 16.7% |
| home | 36 | 22.990 | -0.990 | -4.3% | -25.4% | +16.7% | 61.1% |


### Breakdown — pro_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 41 | 28.620 | -2.620 | -9.2% | -30.8% | +9.2% | 63.4% |
| yes | 27 | 11.350 | 0.650 | +5.7% | -38.1% | +44.5% | 44.4% |


### Breakdown — pro_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 6 | 3.790 | -1.790 | -47.2% | -100.0% | +25.0% | 33.3% |
| epl | 6 | 3.460 | 0.540 | +15.6% | -42.6% | +70.0% | 66.7% |
| laliga | 6 | 1.750 | 0.250 | +14.3% | -100.0% | +150.0% | 33.3% |
| ligue1 | 5 | 2.830 | -0.830 | -29.3% | -100.0% | +44.9% | 40.0% |
| mls | 37 | 22.680 | 1.320 | +5.8% | -19.7% | +30.5% | 64.9% |
| seriea | 8 | 5.460 | -1.460 | -26.7% | -71.6% | +9.6% | 50.0% |


## Professional strategy: pooled fair value, confidence tiers, fractional Kelly

Fair probabilities pool the bookmaker line, the venue's own price and the two models with weights fitted walk-forward (only on earlier matches) and bootstrapped for uncertainty. A bet needs a confident, fee-adjusted edge, agreement between independent sources, a tight and fresh market, and a sane price band. One bet per match, fractional Kelly stakes, daily caps.

Rules: bankroll $1,000, 0.25× Kelly, max 2% per bet, 10% per day, 8 bets/day, confidence ≥ 60, edge ≥ 0.03. Gates: quote consistency, spread ≤ 0.06, price 0.10–0.90, last trade ≤ 48h old, conservative edge (20th pct) ≥ 0.00, edge vs mid ≥ 0.01, bookmaker line alone ≥ 0.00 after fees, lot ≥ 10 contracts.

Pooling weights fitted on the whole sample (the walk-forward fits use only earlier matches):

| source_set | w_book | w_mktn | w_poisson | w_elo | intercepts(h,d,a) | n_train |
|---|---|---|---|---|---|---|
| full | 0.47 | 0.49 | 0.22 | 0.00 | -0.06, +0.07, -0.02 | 228 |
| nobook | – | 0.88 | 0.32 | 0.06 | -0.08, +0.12, -0.05 | 228 |


| n | flat_roi | flat_roi_ci_low | flat_roi_ci_high | win_rate | kelly_staked | kelly_profit | kelly_roi | max_drawdown | avg_confidence | avg_edge |
|---|---|---|---|---|---|---|---|---|---|---|
| 10 | -3.1% | -30.1% | 17.9% | 70.0% | 187.270 | -18.270 | -9.8% | 3.6% | 74.330 | 0.069 |


Closing line value (CLV): entry price vs the venue's price at kickoff and vs the de-vigged closing line. Consistently positive CLV is the earliest reliable evidence of an edge; it needs the entry snapshot to be taken before kickoff (`--minutes-before`).

| clv_vs_venue_close_mean | clv_vs_venue_close_positive | clv_vs_book_mean | clv_vs_book_positive |
|---|---|---|---|
| 0.0030 | 30.0% | 0.0866 | 40.0% |


Realized results of **all** candidate contracts by confidence tier (does the score rank bets correctly?):

| tier | n | roi | roi_ci_low | roi_ci_high | win_rate | avg_edge | clv_close_mean |
|---|---|---|---|---|---|---|---|
| A | 5 | +10.8% | -34.6% | +34.8% | 80.0% | 0.0796 | 0.0060 |
| B | 13 | -24.1% | -64.2% | +20.5% | 46.2% | 0.0570 | 0.0008 |
| C | 39 | +13.7% | -9.7% | +33.2% | 64.1% | 0.0263 | 0.0041 |
| pass | 1,306 | -9.9% | -10.8% | -9.1% | 49.3% | -0.0548 | -0.0001 |


Edge-decile monotonicity over all candidates (Spearman rho of decile vs realized ROI = +0.81; a real edge shows profits rising with predicted edge):

| decile | n | pred_edge | roi | roi_ci_low | roi_ci_high | hit_minus_price | clv_close_mean |
|---|---|---|---|---|---|---|---|
| 1.0000 | 137 | -0.1405 | -13.6% | -29.0% | +1.6% | -0.0339 | -0.0039 |
| 2.0000 | 136 | -0.1032 | -19.4% | -33.9% | -6.2% | -0.0709 | -0.0022 |
| 3.0000 | 136 | -0.0854 | -13.0% | -24.4% | +0.5% | -0.0400 | -0.0019 |
| 4.0000 | 136 | -0.0707 | -8.0% | -21.2% | +5.5% | -0.0076 | -0.0008 |
| 5.0000 | 137 | -0.0576 | -14.4% | -26.8% | -3.2% | -0.0412 | 0.0009 |
| 6.0000 | 136 | -0.0440 | -6.4% | -19.2% | +6.2% | -0.0024 | -0.0005 |
| 7.0000 | 136 | -0.0297 | -5.2% | -18.3% | +6.8% | 0.0054 | 0.0012 |
| 8.0000 | 136 | -0.0163 | -8.6% | -21.5% | +4.5% | -0.0129 | 0.0024 |
| 9.0000 | 136 | 0.0014 | -0.1% | -11.6% | +13.3% | 0.0332 | 0.0018 |
| 10.0000 | 137 | 0.0365 | -4.9% | -18.8% | +8.1% | 0.0071 | 0.0036 |


Distance of each probability source to the de-vigged **closing** line (lower = closer to the sharpest price; this converges much faster than ROI):

| source | n | mse_vs_closing_line | mean_abs_diff_pts |
|---|---|---|---|
| mktn | 125 | 0.0068 | 3.8277 |
| book | 125 | 0.0011 | 1.4887 |
| pro | 125 | 0.0028 | 2.3363 |
| poisson | 125 | 0.0194 | 6.0643 |
| elo | 125 | 0.0257 | 7.2472 |


Bets the rules would have placed (first 20):

| kickoff | league | home | away | outcome | side | price | fee | fair | fair_sd | edge | edge_z | agreement | confidence | tier | contracts | clv_close | won | profit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-28 13:00 | bundesliga | Bayern Munich | VfL Wolfsburg | home | no | 0.820 | 0.025 | 0.911 | 0.043 | 0.066 | 1.414 | 0.667 | 72.100 | B | 23 | 0.000 | True | 0.155 |
| 2026-08-28 14:00 | laliga | Real Madrid | Getafe | draw | yes | 0.200 | 0.026 | 0.270 | 0.047 | 0.044 | 0.849 | 1.000 | 74.900 | B | 56 | 0.010 | False | -0.226 |
| 2026-08-28 16:00 | laliga | Sevilla | Elche | home | no | 0.750 | 0.029 | 0.840 | 0.045 | 0.061 | 1.322 | 0.333 | 77.500 | A | 25 | 0.000 | True | 0.221 |
| 2026-08-29 18:00 | seriea | AC Milan | Lecce | home | no | 0.710 | 0.031 | 0.822 | 0.048 | 0.081 | 1.478 | 1.000 | 89.500 | A | 26 | 0.000 | True | 0.259 |
| 2026-08-29 23:00 | mls | Seattle Sounders FC | CF Montréal | home | no | 0.860 | 0.022 | 0.927 | 0.029 | 0.045 | 1.279 | 0.667 | 77.500 | A | 22 | 0.010 | True | 0.118 |
| 2026-08-30 00:00 | mls | Houston Dynamo FC | Austin FC | away | no | 0.820 | 0.025 | 0.897 | 0.043 | 0.052 | 1.097 | 0.667 | 65.600 | B | 23 | 0.000 | True | 0.155 |
| 2026-09-05 23:00 | mls | San Diego FC | New York Red Bulls | away | yes | 0.660 | 0.033 | 0.854 | 0.114 | 0.162 | 1.351 | 0.667 | 79.900 | A | 28 | 0.000 | True | 0.307 |
| 2026-09-05 23:00 | mls | Nashville SC | Sporting Kansas City | home | no | 0.810 | 0.026 | 0.896 | 0.060 | 0.061 | 0.938 | 0.667 | 64.300 | B | 23 | 0.000 | False | -0.836 |
| 2026-09-05 23:00 | mls | Atlanta United FC | Los Angeles FC | away | no | 0.870 | 0.021 | 0.935 | 0.033 | 0.043 | 1.035 | 0.667 | 61.100 | B | 22 | -0.010 | True | 0.109 |
| 2026-09-06 00:00 | mls | Orlando City SC | Real Salt Lake | home | yes | 0.450 | 0.035 | 0.565 | 0.064 | 0.080 | 1.183 | 0.667 | 80.900 | A | 40 | 0.020 | False | -0.485 |


## Largest-edge bets — poisson reference

| kickoff | league | home | away | outcome | side | price | fee | fair | edge | won | profit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-07-27 02:00 | mls | LA Galaxy | New York Red Bulls | away | yes | 0.360 | 0.040 | 0.741 | 0.341 | True | 0.600 |
| 2026-09-06 23:00 | mls | Houston Dynamo FC | Chicago Fire FC | away | no | 0.460 | 0.040 | 0.827 | 0.327 | True | 0.500 |
| 2026-08-17 00:00 | mls | Seattle Sounders FC | Inter Miami CF | away | yes | 0.340 | 0.040 | 0.696 | 0.316 | True | 0.620 |
| 2026-08-22 16:00 | bundesliga | TSG Hoffenheim | Mainz | away | no | 0.420 | 0.040 | 0.750 | 0.290 | True | 0.540 |
| 2026-08-02 00:00 | mls | Colorado Rapids | Sporting Kansas City | away | yes | 0.480 | 0.040 | 0.801 | 0.281 | False | -0.520 |
| 2026-08-24 00:00 | mls | LA Galaxy | Sporting Kansas City | home | no | 0.380 | 0.040 | 0.662 | 0.242 | True | 0.580 |
| 2026-07-26 02:00 | mls | Colorado Rapids | San Jose Earthquakes | home | no | 0.400 | 0.040 | 0.676 | 0.236 | True | 0.560 |
| 2026-08-28 19:00 | laliga | Espanyol | Real Sociedad | away | no | 0.410 | 0.040 | 0.683 | 0.233 | False | -0.450 |
| 2026-08-30 18:00 | seriea | Parma | Juventus | home | no | 0.390 | 0.040 | 0.662 | 0.232 | False | -0.430 |
| 2026-08-23 02:00 | mls | Orlando City SC | New York Red Bulls | away | yes | 0.560 | 0.040 | 0.832 | 0.232 | True | 0.400 |
| 2026-07-27 02:00 | mls | LA Galaxy | New York Red Bulls | home | no | 0.600 | 0.040 | 0.869 | 0.229 | True | 0.360 |
| 2026-09-05 23:00 | mls | San Diego FC | New York Red Bulls | away | yes | 0.660 | 0.040 | 0.917 | 0.217 | True | 0.300 |
| 2026-08-16 14:00 | epl | Crystal Palace | Manchester City | home | yes | 0.270 | 0.030 | 0.510 | 0.210 | False | -0.300 |
| 2026-08-30 02:00 | mls | Atlanta United FC | Inter Miami CF | home | no | 0.390 | 0.040 | 0.633 | 0.203 | True | 0.570 |
| 2026-09-06 00:00 | mls | Charlotte FC | Inter Miami CF | away | yes | 0.230 | 0.030 | 0.459 | 0.199 | False | -0.260 |


## How to read this

- A real, exploitable edge needs three things at once: a bias that is stable across leagues/weeks, ROI whose confidence interval excludes zero **after fees**, and fills at the ask (not the last trade).
- Brier/log-loss differences of < 0.005 are noise at this sample size.
- Model-based strategies (Elo, Poisson) are weak references; `book` (the closing line) is the strongest public benchmark. If a strategy only wins against Elo, that is not evidence of an edge.
- Rothera-routed Robinhood contracts have no public API; import them with `--prices-csv` to include them.
