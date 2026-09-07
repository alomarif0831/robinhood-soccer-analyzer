# Robinhood soccer prediction-market backtest

> **SYNTHETIC DEMO DATA.** Every price and score in this report was simulated by `rsa demo` with planted biases so you can see what the analysis looks like. Nothing here is a real finding.

Generated 2026-09-07 01:55 UTC. Window **2026-07-20 → 2026-09-06** (post-World-Cup). Fee model: **robinhood**; fills at **ask**.

- Fixtures in window: 228 (228 completed); warm-up results for models: 1992
- Venue price snapshots: 684; priced events matched to a fixture: 228; unmatched events: 0

## Verdict

- Venue prices and the closing line are statistically indistinguishable in accuracy (mean Brier gap -0.004, t=-0.6, n=228).
- Versus the closing line the venue prices the draw below fair on average (-2.3 pts, t=-7.6, n=228).
- Versus the closing line the venue prices the away above fair on average (+2.2 pts, t=7.1, n=228).
- Professional rules would have placed 10 bets: flat ROI -3.1% (95% CI -30.1% to +17.9%), Kelly ROI -9.8%, max drawdown 3.6%, mean CLV vs venue close +0.3 pts.
- The **book**-based strategy's ROI of -8.8% (n=120) is not distinguishable from zero (95% CI -24.0% to +5.7%).
- The **elo**-based strategy's ROI of -15.6% (n=255) is not distinguishable from zero (95% CI -31.1% to +1.3%).
- The **poisson**-based strategy's ROI of +1.3% (n=260) is not distinguishable from zero (95% CI -11.0% to +13.2%).
- The **blend**-based strategy's ROI of -2.7% (n=107) is not distinguishable from zero (95% CI -20.2% to +13.7%).
- The **pro**-based strategy's ROI of -4.8% (n=63) is not distinguishable from zero (95% CI -26.3% to +14.7%).

## Accuracy: venue vs reference probabilities

Multiclass Brier score and log loss over the three outcomes (lower is better). `mktn` = venue prices normalized to sum to 1; `book` = de-vigged closing odds (Pinnacle when available); `elo`/`poisson` = walk-forward models; `blend` = 30% Poisson / 70% book.

| source | n | brier | logloss |
|---|---|---|---|
| mktn | 228 | 0.568 | 0.955 |
| book | 228 | 0.571 | 0.959 |
| elo | 228 | 0.601 | 1.007 |
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
| home | 228 | 114.740 | -13.740 | -12.0% | -23.7% | -0.2% | 44.3% | 0.466 |
| draw | 228 | 62.760 | -7.760 | -12.4% | -31.0% | +8.0% | 24.1% | 0.243 |
| away | 228 | 87.190 | -15.190 | -17.4% | -31.4% | -3.0% | 31.6% | 0.347 |
| favorite | 228 | 134.570 | -5.570 | -4.1% | -14.8% | +6.6% | 56.6% | 0.551 |
| underdog | 228 | 56.830 | -12.830 | -22.6% | -42.5% | -1.6% | 19.3% | 0.218 |
| no_draw | 228 | 187.350 | -14.350 | -7.7% | -14.6% | -1.4% | 75.9% | 0.791 |


## Reference-driven strategies, after fees

Buy any YES or NO contract whose reference probability exceeds fill price + fee by at least 0.03.

| reference | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge | p_value_profit_le_0 |
|---|---|---|---|---|---|---|---|---|---|---|
| book | 120 | 64.720 | -5.720 | -8.8% | -24.0% | +5.7% | 49.2% | 0.505 | 0.054 | 0.879 |
| elo | 255 | 95.930 | -14.930 | -15.6% | -31.1% | +1.3% | 31.8% | 0.341 | 0.092 | 0.968 |
| poisson | 260 | 134.310 | 1.690 | +1.3% | -11.0% | +13.2% | 52.3% | 0.481 | 0.089 | 0.426 |
| blend | 107 | 56.540 | -1.540 | -2.7% | -20.2% | +13.7% | 51.4% | 0.493 | 0.060 | 0.627 |
| pro | 63 | 36.750 | -1.750 | -4.8% | -26.3% | +14.7% | 55.6% | 0.549 | 0.056 | 0.682 |


### Edge threshold sweep — book

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 290 | 161.790 | -1.790 | -1.1% | -10.7% | +8.5% | 55.2% | 0.524 | 0.030 |
| 0.020 | 157 | 87.450 | -4.450 | -5.1% | -17.8% | +7.3% | 52.9% | 0.522 | 0.047 |
| 0.040 | 81 | 40.990 | -1.990 | -4.9% | -23.1% | +13.5% | 48.1% | 0.471 | 0.064 |
| 0.060 | 38 | 17.410 | -1.410 | -8.1% | -39.3% | +23.8% | 42.1% | 0.423 | 0.082 |
| 0.080 | 16 | 6.440 | 0.560 | +8.7% | -39.3% | +47.5% | 43.8% | 0.369 | 0.103 |
| 0.100 | 6 | 2.170 | -0.170 | -7.8% | -100.0% | +53.9% | 33.3% | 0.330 | 0.125 |


### Edge threshold sweep — elo

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 393 | 152.620 | -28.620 | -18.8% | -31.8% | -5.4% | 31.6% | 0.353 | 0.065 |
| 0.020 | 295 | 112.280 | -12.280 | -10.9% | -25.9% | +4.6% | 33.9% | 0.345 | 0.083 |
| 0.040 | 225 | 85.000 | -14.000 | -16.5% | -33.3% | +0.5% | 31.6% | 0.342 | 0.099 |
| 0.060 | 164 | 61.590 | -2.590 | -4.2% | -23.0% | +15.8% | 36.0% | 0.340 | 0.118 |
| 0.080 | 118 | 43.570 | -0.570 | -1.3% | -24.0% | +21.2% | 36.4% | 0.333 | 0.137 |
| 0.100 | 88 | 31.500 | 2.500 | +7.9% | -17.5% | +35.8% | 38.6% | 0.322 | 0.152 |


### Edge threshold sweep — poisson

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 384 | 193.540 | -7.540 | -3.9% | -13.7% | +6.5% | 48.4% | 0.469 | 0.065 |
| 0.020 | 299 | 153.790 | -0.790 | -0.5% | -12.4% | +10.6% | 51.2% | 0.479 | 0.080 |
| 0.040 | 214 | 109.830 | 4.170 | +3.8% | -10.5% | +18.2% | 53.3% | 0.477 | 0.100 |
| 0.060 | 156 | 79.130 | 4.870 | +6.2% | -9.3% | +21.4% | 53.8% | 0.471 | 0.119 |
| 0.080 | 112 | 54.440 | 5.560 | +10.2% | -8.8% | +30.1% | 53.6% | 0.449 | 0.138 |
| 0.100 | 88 | 42.670 | 4.330 | +10.1% | -12.6% | +31.8% | 53.4% | 0.447 | 0.152 |


### Edge threshold sweep — blend

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 279 | 144.980 | 2.020 | +1.4% | -9.2% | +12.5% | 52.7% | 0.485 | 0.032 |
| 0.020 | 149 | 79.880 | -0.880 | -1.1% | -15.3% | +13.1% | 53.0% | 0.501 | 0.050 |
| 0.040 | 76 | 39.930 | 1.070 | +2.7% | -16.5% | +23.0% | 53.9% | 0.490 | 0.070 |
| 0.060 | 38 | 17.730 | 1.270 | +7.2% | -25.0% | +36.8% | 50.0% | 0.431 | 0.091 |
| 0.080 | 21 | 9.090 | 0.910 | +10.0% | -32.1% | +48.8% | 47.6% | 0.398 | 0.110 |
| 0.100 | 10 | 4.150 | 1.850 | +44.6% | -23.9% | +102.0% | 60.0% | 0.378 | 0.133 |


### Edge threshold sweep — pro

| min_edge | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate | avg_price | avg_edge |
|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 210 | 119.460 | -3.460 | -2.9% | -12.8% | +7.5% | 55.2% | 0.535 | 0.026 |
| 0.020 | 92 | 53.640 | -1.640 | -3.1% | -19.7% | +12.8% | 56.5% | 0.549 | 0.046 |
| 0.040 | 45 | 26.590 | -2.590 | -9.7% | -33.3% | +12.5% | 53.3% | 0.556 | 0.065 |
| 0.060 | 21 | 11.490 | 1.510 | +13.1% | -21.9% | +46.4% | 61.9% | 0.511 | 0.084 |
| 0.080 | 8 | 3.880 | 1.120 | +28.9% | -32.2% | +82.3% | 62.5% | 0.448 | 0.106 |
| 0.100 | 3 | 1.660 | 1.340 | +80.7% | +42.9% | +117.4% | 100.0% | 0.513 | 0.139 |


### Breakdown — book_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 36 | 23.320 | -0.320 | -1.4% | -24.7% | +19.8% | 63.9% |
| draw | 32 | 10.480 | -4.480 | -42.7% | -81.9% | +3.4% | 18.8% |
| home | 52 | 30.920 | -0.920 | -3.0% | -25.3% | +19.4% | 57.7% |


### Breakdown — book_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 65 | 43.370 | -3.370 | -7.8% | -23.3% | +9.2% | 61.5% |
| yes | 55 | 21.350 | -2.350 | -11.0% | -38.5% | +17.2% | 34.5% |


### Breakdown — book_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 12 | 6.870 | -1.870 | -27.2% | -65.2% | +20.6% | 41.7% |
| epl | 11 | 5.770 | 0.230 | +4.0% | -58.0% | +85.8% | 54.5% |
| laliga | 19 | 7.570 | -0.570 | -7.5% | -53.1% | +34.3% | 36.8% |
| ligue1 | 12 | 6.520 | -1.520 | -23.3% | -68.4% | +25.2% | 41.7% |
| mls | 58 | 32.820 | -1.820 | -5.5% | -23.0% | +13.4% | 53.4% |
| seriea | 8 | 5.170 | -0.170 | -3.3% | -58.7% | +61.9% | 62.5% |


### Breakdown — elo_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 90 | 38.110 | -5.110 | -13.4% | -33.6% | +8.2% | 36.7% |
| draw | 47 | 14.020 | -2.020 | -14.4% | -52.7% | +25.4% | 25.5% |
| home | 118 | 43.800 | -7.800 | -17.8% | -40.8% | +4.8% | 30.5% |


### Breakdown — elo_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 129 | 63.390 | -7.390 | -11.7% | -28.2% | +5.5% | 43.4% |
| yes | 126 | 32.540 | -7.540 | -23.2% | -47.9% | +2.7% | 19.8% |


### Breakdown — elo_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 23 | 8.270 | -1.270 | -15.4% | -59.5% | +32.5% | 30.4% |
| epl | 33 | 14.220 | 0.780 | +5.5% | -39.7% | +58.3% | 45.5% |
| laliga | 38 | 15.660 | 2.340 | +14.9% | -22.2% | +53.7% | 47.4% |
| ligue1 | 23 | 10.170 | -4.170 | -41.0% | -79.9% | +0.9% | 26.1% |
| mls | 117 | 40.680 | -10.680 | -26.3% | -47.5% | -1.5% | 25.6% |
| seriea | 21 | 6.930 | -1.930 | -27.8% | -84.6% | +51.2% | 23.8% |


### Breakdown — poisson_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 102 | 54.780 | 2.220 | +4.1% | -12.5% | +19.8% | 55.9% |
| draw | 47 | 22.780 | -1.780 | -7.8% | -32.2% | +15.4% | 44.7% |
| home | 111 | 56.750 | 1.250 | +2.2% | -16.1% | +19.3% | 52.3% |


### Breakdown — poisson_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 142 | 89.540 | -0.540 | -0.6% | -11.0% | +10.4% | 62.7% |
| yes | 118 | 44.770 | 2.230 | +5.0% | -15.3% | +26.0% | 39.8% |


### Breakdown — poisson_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 14 | 7.090 | -1.090 | -15.4% | -83.7% | +56.4% | 42.9% |
| epl | 32 | 15.710 | 0.290 | +1.8% | -36.5% | +46.4% | 50.0% |
| laliga | 32 | 14.230 | 1.770 | +12.4% | -27.3% | +54.8% | 50.0% |
| ligue1 | 24 | 11.240 | -2.240 | -19.9% | -59.8% | +21.3% | 37.5% |
| mls | 138 | 77.560 | 6.440 | +8.3% | -6.0% | +23.2% | 60.9% |
| seriea | 20 | 8.480 | -3.480 | -41.0% | -87.6% | +15.9% | 25.0% |


### Breakdown — blend_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 35 | 21.340 | 3.660 | +17.2% | -7.1% | +38.0% | 71.4% |
| draw | 28 | 9.790 | -4.790 | -48.9% | -88.4% | -7.7% | 17.9% |
| home | 44 | 25.410 | -0.410 | -1.6% | -25.6% | +21.3% | 56.8% |


### Breakdown — blend_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 58 | 37.350 | -0.350 | -0.9% | -17.4% | +18.0% | 63.8% |
| yes | 49 | 19.190 | -1.190 | -6.2% | -34.6% | +23.1% | 36.7% |


### Breakdown — blend_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 10 | 4.980 | -0.980 | -19.7% | -73.1% | +40.8% | 40.0% |
| epl | 11 | 5.410 | -1.410 | -26.1% | -82.6% | +67.9% | 36.4% |
| laliga | 14 | 4.990 | -0.990 | -19.8% | -76.0% | +29.9% | 28.6% |
| ligue1 | 9 | 4.240 | -1.240 | -29.2% | -100.0% | +48.9% | 33.3% |
| mls | 52 | 31.280 | 3.720 | +11.9% | -7.3% | +28.6% | 67.3% |
| seriea | 11 | 5.640 | -0.640 | -11.3% | -80.8% | +64.3% | 45.5% |


### Breakdown — pro_by_outcome

| outcome | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| away | 20 | 13.080 | 0.920 | +7.0% | -29.6% | +41.5% | 70.0% |
| draw | 12 | 3.900 | -1.900 | -48.7% | -100.0% | +37.0% | 16.7% |
| home | 31 | 19.770 | -0.770 | -3.9% | -29.2% | +17.8% | 61.3% |


### Breakdown — pro_by_side

| side | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| no | 37 | 26.050 | -2.050 | -7.9% | -29.3% | +12.8% | 64.9% |
| yes | 26 | 10.700 | 0.300 | +2.8% | -36.2% | +41.1% | 42.3% |


### Breakdown — pro_by_league

| league | n | risked | profit | roi | roi_ci_low | roi_ci_high | win_rate |
|---|---|---|---|---|---|---|---|
| bundesliga | 6 | 3.790 | -1.790 | -47.2% | -100.0% | +25.0% | 33.3% |
| epl | 6 | 3.460 | 0.540 | +15.6% | -42.6% | +70.0% | 66.7% |
| laliga | 6 | 1.750 | 0.250 | +14.3% | -100.0% | +165.6% | 33.3% |
| ligue1 | 5 | 2.830 | -0.830 | -29.3% | -100.0% | +37.0% | 40.0% |
| mls | 33 | 19.940 | 1.060 | +5.3% | -24.8% | +30.6% | 63.6% |
| seriea | 7 | 4.980 | -0.980 | -19.7% | -74.9% | +20.7% | 57.1% |


## Professional strategy: pooled fair value, confidence tiers, fractional Kelly

Fair probabilities pool the bookmaker line, the venue's own price and the two models with weights fitted walk-forward (only on earlier matches) and bootstrapped for uncertainty. A bet needs a confident, fee-adjusted edge, agreement between independent sources, a tight and fresh market, and a sane price band. One bet per match, fractional Kelly stakes, daily caps.

Rules: bankroll $1,000, 0.25× Kelly, max 2% per bet, 10% per day, 8 bets/day, confidence ≥ 60, edge ≥ 0.03. Gates: quote consistency, spread ≤ 0.06, price 0.10–0.90, last trade ≤ 48h old, conservative edge (20th pct) ≥ 0.00, edge vs mid ≥ 0.01, bookmaker line alone ≥ 0.00 after fees, lot ≥ 10 contracts.

Pooling weights fitted on the whole sample (the walk-forward fits use only earlier matches):

| source_set | w_book | w_mktn | w_poisson | w_elo | intercepts(h,d,a) | n_train |
|---|---|---|---|---|---|---|
| full | 0.47 | 0.49 | 0.22 | 0.01 | -0.06, +0.07, -0.01 | 228 |
| nobook | – | 0.88 | 0.31 | 0.08 | -0.08, +0.13, -0.05 | 228 |


| n | flat_roi | flat_roi_ci_low | flat_roi_ci_high | win_rate | kelly_staked | kelly_profit | kelly_roi | max_drawdown | avg_confidence | avg_edge |
|---|---|---|---|---|---|---|---|---|---|---|
| 10 | -3.1% | -30.1% | 17.9% | 70.0% | 187.270 | -18.270 | -9.8% | 3.6% | 73.820 | 0.069 |


Closing line value (CLV): entry price vs the venue's price at kickoff and vs the de-vigged closing line. Consistently positive CLV is the earliest reliable evidence of an edge; it needs the entry snapshot to be taken before kickoff (`--minutes-before`).

| clv_vs_venue_close_mean | clv_vs_venue_close_positive | clv_vs_book_mean | clv_vs_book_positive |
|---|---|---|---|
| 0.0030 | 30.0% | 0.0866 | 40.0% |


Realized results of **all** candidate contracts by confidence tier (does the score rank bets correctly?):

| tier | n | roi | roi_ci_low | roi_ci_high | win_rate | avg_edge | clv_close_mean |
|---|---|---|---|---|---|---|---|
| A | 5 | +10.8% | -34.6% | +34.8% | 80.0% | 0.0786 | 0.0060 |
| B | 11 | -9.8% | -55.9% | +37.1% | 54.5% | 0.0561 | 0.0018 |
| C | 40 | +7.6% | -14.8% | +27.6% | 60.0% | 0.0284 | 0.0037 |
| pass | 1,307 | -9.9% | -10.8% | -9.0% | 49.3% | -0.0548 | -0.0001 |


Edge-decile monotonicity over all candidates (Spearman rho of decile vs realized ROI = +0.53; a real edge shows profits rising with predicted edge):

| decile | n | pred_edge | roi | roi_ci_low | roi_ci_high | hit_minus_price | clv_close_mean |
|---|---|---|---|---|---|---|---|
| 1.0000 | 137 | -0.1399 | -7.8% | -23.1% | +5.8% | -0.0037 | -0.0040 |
| 2.0000 | 136 | -0.1031 | -25.3% | -38.1% | -11.5% | -0.1041 | -0.0015 |
| 3.0000 | 136 | -0.0853 | -12.7% | -26.2% | +1.0% | -0.0388 | -0.0024 |
| 4.0000 | 136 | -0.0706 | -4.8% | -21.5% | +9.9% | 0.0099 | -0.0005 |
| 5.0000 | 137 | -0.0578 | -20.7% | -31.5% | -9.7% | -0.0774 | 0.0001 |
| 6.0000 | 136 | -0.0440 | -1.5% | -14.5% | +11.9% | 0.0257 | 0.0002 |
| 7.0000 | 136 | -0.0296 | -4.4% | -18.4% | +7.0% | 0.0101 | 0.0012 |
| 8.0000 | 136 | -0.0162 | -11.2% | -25.0% | +2.3% | -0.0260 | 0.0027 |
| 9.0000 | 136 | 0.0010 | +2.7% | -10.4% | +13.9% | 0.0490 | 0.0017 |
| 10.0000 | 137 | 0.0362 | -7.4% | -21.2% | +5.1% | -0.0076 | 0.0033 |


Distance of each probability source to the de-vigged **closing** line (lower = closer to the sharpest price; this converges much faster than ROI):

| source | n | mse_vs_closing_line | mean_abs_diff_pts |
|---|---|---|---|
| mktn | 125 | 0.0068 | 3.8277 |
| book | 125 | 0.0011 | 1.4887 |
| pro | 125 | 0.0027 | 2.3141 |
| poisson | 125 | 0.0193 | 6.0549 |
| elo | 125 | 0.0257 | 7.2445 |


Bets the rules would have placed (first 20):

| kickoff | league | home | away | outcome | side | price | fee | fair | fair_sd | edge | edge_z | agreement | confidence | tier | contracts | clv_close | won | profit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-28 13:00 | bundesliga | Bayern Munich | VfL Wolfsburg | home | no | 0.820 | 0.025 | 0.910 | 0.043 | 0.066 | 1.414 | 0.667 | 72.100 | B | 23 | 0.000 | True | 0.155 |
| 2026-08-28 14:00 | laliga | Real Madrid | Getafe | draw | yes | 0.200 | 0.026 | 0.270 | 0.047 | 0.044 | 0.848 | 1.000 | 74.800 | B | 56 | 0.010 | False | -0.226 |
| 2026-08-28 16:00 | laliga | Sevilla | Elche | home | no | 0.750 | 0.029 | 0.840 | 0.045 | 0.061 | 1.322 | 0.333 | 77.500 | A | 25 | 0.000 | True | 0.221 |
| 2026-08-29 18:00 | seriea | AC Milan | Lecce | home | no | 0.710 | 0.031 | 0.821 | 0.048 | 0.081 | 1.495 | 1.000 | 89.900 | A | 26 | 0.000 | True | 0.259 |
| 2026-08-29 23:00 | mls | Seattle Sounders FC | CF Montréal | home | no | 0.860 | 0.022 | 0.927 | 0.029 | 0.045 | 1.280 | 0.667 | 77.500 | A | 22 | 0.010 | True | 0.118 |
| 2026-08-30 00:00 | mls | Houston Dynamo FC | Austin FC | away | no | 0.820 | 0.025 | 0.893 | 0.048 | 0.048 | 0.897 | 0.667 | 60.000 | B | 23 | 0.000 | True | 0.155 |
| 2026-09-05 23:00 | mls | San Diego FC | New York Red Bulls | away | yes | 0.660 | 0.033 | 0.855 | 0.114 | 0.162 | 1.355 | 0.667 | 79.900 | A | 28 | 0.000 | True | 0.307 |
| 2026-09-05 23:00 | mls | Nashville SC | Sporting Kansas City | home | no | 0.810 | 0.026 | 0.897 | 0.061 | 0.062 | 0.946 | 0.667 | 64.700 | B | 23 | 0.000 | False | -0.836 |
| 2026-09-05 23:00 | mls | Atlanta United FC | Los Angeles FC | away | no | 0.870 | 0.021 | 0.935 | 0.033 | 0.043 | 1.042 | 0.667 | 61.300 | B | 22 | -0.010 | True | 0.109 |
| 2026-09-06 00:00 | mls | Orlando City SC | Real Salt Lake | home | yes | 0.450 | 0.035 | 0.560 | 0.080 | 0.075 | 0.879 | 1.000 | 80.500 | A | 40 | 0.020 | False | -0.485 |


## Largest-edge bets — poisson reference

| kickoff | league | home | away | outcome | side | price | fee | fair | edge | won | profit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-07-27 02:00 | mls | LA Galaxy | New York Red Bulls | away | yes | 0.360 | 0.040 | 0.741 | 0.341 | True | 0.600 |
| 2026-09-06 23:00 | mls | Houston Dynamo FC | Chicago Fire FC | away | no | 0.460 | 0.040 | 0.830 | 0.330 | True | 0.500 |
| 2026-08-17 00:00 | mls | Seattle Sounders FC | Inter Miami CF | away | yes | 0.340 | 0.040 | 0.696 | 0.316 | True | 0.620 |
| 2026-08-22 16:00 | bundesliga | TSG Hoffenheim | Mainz | away | no | 0.420 | 0.040 | 0.750 | 0.290 | True | 0.540 |
| 2026-08-02 00:00 | mls | Colorado Rapids | Sporting Kansas City | away | yes | 0.480 | 0.040 | 0.801 | 0.281 | False | -0.520 |
| 2026-08-24 00:00 | mls | LA Galaxy | Sporting Kansas City | home | no | 0.380 | 0.040 | 0.662 | 0.242 | True | 0.580 |
| 2026-07-26 02:00 | mls | Colorado Rapids | San Jose Earthquakes | home | no | 0.400 | 0.040 | 0.676 | 0.236 | True | 0.560 |
| 2026-08-30 18:00 | seriea | Parma | Juventus | home | no | 0.390 | 0.040 | 0.662 | 0.232 | False | -0.430 |
| 2026-08-23 02:00 | mls | Orlando City SC | New York Red Bulls | away | yes | 0.560 | 0.040 | 0.832 | 0.232 | True | 0.400 |
| 2026-07-27 02:00 | mls | LA Galaxy | New York Red Bulls | home | no | 0.600 | 0.040 | 0.869 | 0.229 | True | 0.360 |
| 2026-08-28 19:00 | laliga | Espanyol | Real Sociedad | away | no | 0.410 | 0.040 | 0.679 | 0.229 | False | -0.450 |
| 2026-09-05 23:00 | mls | San Diego FC | New York Red Bulls | away | yes | 0.660 | 0.040 | 0.916 | 0.216 | True | 0.300 |
| 2026-08-16 14:00 | epl | Crystal Palace | Manchester City | home | yes | 0.270 | 0.030 | 0.509 | 0.209 | False | -0.300 |
| 2026-08-30 02:00 | mls | Atlanta United FC | Inter Miami CF | home | no | 0.390 | 0.040 | 0.633 | 0.203 | True | 0.570 |
| 2026-09-06 00:00 | mls | Charlotte FC | Inter Miami CF | away | yes | 0.230 | 0.030 | 0.461 | 0.201 | False | -0.260 |


## How to read this

- A real, exploitable edge needs three things at once: a bias that is stable across leagues/weeks, ROI whose confidence interval excludes zero **after fees**, and fills at the ask (not the last trade).
- Brier/log-loss differences of < 0.005 are noise at this sample size.
- Model-based strategies (Elo, Poisson) are weak references; `book` (the closing line) is the strongest public benchmark. If a strategy only wins against Elo, that is not evidence of an edge.
- Rothera-routed Robinhood contracts have no public API; import them with `--prices-csv` to include them.
