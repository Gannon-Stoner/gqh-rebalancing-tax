# Inference calibration (synthetic data only)

500 panels per scenario, 9,999 bootstrap draws per test, one-sided alpha = 0.05. Each panel is a full IS history (2010-06-07 to 2024-10-01) of daily ES/ZN returns run through the real schedule and signal code. Runtime 37.8 min.

| Scenario | Test | Month-block | Wild | Newey-West(3) | Mean estimate |
|---|---|---|---|---|---|
| base | H1 | 0.064 [0.044, 0.089] | 0.056 [0.038, 0.080] | 0.072 [0.051, 0.098] | +0.0054 |
| base | H2 | 0.048 [0.031, 0.071] | 0.044 [0.028, 0.066] | 0.048 [0.031, 0.071] | -0.0023 |
| stress_corr | H1 | 0.054 [0.036, 0.078] | 0.052 [0.034, 0.075] | 0.060 [0.041, 0.085] | +0.0101 |
| stress_corr | H2 | 0.056 [0.038, 0.080] | 0.056 [0.038, 0.080] | 0.060 [0.041, 0.085] | +0.0049 |
| h2_reversal | H1 | 0.126 [0.098, 0.158] | 0.108 [0.082, 0.139] | 0.132 [0.104, 0.165] | +0.0490 |
| h2_reversal | H2 | 0.038 [0.023, 0.059] | 0.032 [0.018, 0.051] | 0.042 [0.026, 0.063] | +0.0038 |
| h1_power | H1 | 0.112 [0.086, 0.143] | 0.106 [0.080, 0.136] | 0.126 [0.098, 0.158] | +0.0514 |
| h1_power | H2 | 0.038 [0.023, 0.059] | 0.028 [0.015, 0.047] | 0.042 [0.026, 0.063] | +0.0069 |
| h1_power_hi | H1 | 0.202 [0.168, 0.240] | 0.194 [0.160, 0.231] | 0.212 [0.177, 0.250] | +0.1191 |
| h1_power_hi | H2 | 0.030 [0.017, 0.049] | 0.030 [0.017, 0.049] | 0.030 [0.017, 0.049] | +0.0105 |
| h2_power | H1 | 0.174 [0.142, 0.210] | 0.176 [0.144, 0.212] | 0.190 [0.157, 0.227] | +0.1106 |
| h2_power | H2 | 0.584 [0.539, 0.628] | 0.568 [0.523, 0.612] | 0.592 [0.547, 0.635] | -0.2731 |

Rates are rejection frequencies with 95% Clopper-Pearson intervals. Size rows (H1 and H2 under base and stress_corr; H2 under h2_reversal) must lie in [0.03, 0.07] for the month-block bootstrap; otherwise the registered fallback (wild) is used. H1 under h2_reversal measures leakage of ordinary reversal into H1 (its null does not hold there). Power rows are recorded, not tested.
