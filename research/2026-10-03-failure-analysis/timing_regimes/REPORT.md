# Exploratory timing, leg, and regime decomposition

Only settlements dated through 2024-10-01 were loaded. Original sources/configuration/results were not changed. All seven variants in PLAN.md are reported. Baseline reconciles exactly to registered P0; ES-only + ZN-only reconciles to baseline. No OOS was loaded.

All variants use original ex-ante quantities; short windows and single legs are not relevered. Later entries keep L-5 direction, dose, quantities, and contracts. Net means registered fees and half-spreads; settlement clocks remain asynchronous. Chronological subsets are exploratory stability checks after prior IS inspection, not validation on an untouched holdout.

## Seven-variant common-period summary

| variant | segment | months | trades | net | gross | costs | sharpe | sharpe_2x | mean_bp | positive_years | years | worst_month | best_month | top3_months | without_best3_net | mean_bp_ci90_lo | mean_bp_ci90_hi | loo_year_sharpe_min | loo_year_sharpe_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | common | 108 | 104 | 183525.0000 | 241062.5000 | 57537.5000 | 0.1339 | 0.0919 | 1.6993 | 5 | 10 | -116627.5000 | 176000.0000 | 470939.3750 | -287414.3750 | -4.6948 | 8.4007 | -0.0224 | 0.2577 |
| exit_L | common | 108 | 104 | 794478.1250 | 852015.6250 | 57537.5000 | 0.6342 | 0.5889 | 7.3563 | 7 | 10 | -103302.5000 | 197443.1250 | 488251.8750 | 306226.2500 | 1.2120 | 13.8121 | 0.4616 | 0.8138 |
| last_day | common | 108 | 104 | 312359.3750 | 369896.8750 | 57537.5000 | 0.4709 | 0.3843 | 2.8922 | 6 | 10 | -49615.0000 | 117999.3750 | 273673.1250 | 38686.2500 | -0.2107 | 6.2498 | 0.2936 | 0.6733 |
| F1_only | common | 108 | 104 | -668490.6250 | -610953.1250 | 57537.5000 | -0.9961 | -1.0759 | -6.1897 | 2 | 10 | -105380.0000 | 65260.0000 | 137925.6250 | -806416.2500 | -9.6327 | -2.9589 | -1.2317 | -0.8841 |
| ES_only | common | 108 | 104 | 252677.5000 | 275812.5000 | 23135.0000 | 0.2105 | 0.1912 | 2.3396 | 5 | 10 | -75915.0000 | 177345.0000 | 405207.5000 | -152530.0000 | -3.0762 | 8.0376 | -0.0710 | 0.3494 |
| ZN_only | common | 108 | 104 | -69152.5000 | -34750.0000 | 34402.5000 | -0.1220 | -0.1828 | -0.6403 | 5 | 10 | -70644.3750 | 76670.0000 | 179870.0000 | -249022.5000 | -3.2463 | 2.3252 | -0.2024 | 0.0878 |
| midmonth | common | 108 | 106 | -447090.6250 | -396109.3750 | 50981.2500 | -0.3881 | -0.4312 | -4.1397 | 1 | 10 | -164857.5000 | 90673.1250 | 259731.2500 | -706821.8750 | -9.1779 | 0.8943 | -0.4622 | -0.3336 |

## Fixed calendar era summaries

| variant | segment | trades | net | sharpe | sharpe_2x | mean_bp_ci90_lo | mean_bp_ci90_hi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | era_2010-2015 | 59 | -123963.7500 | -0.1547 | -0.2066 | -9.1622 | 5.6158 |
| baseline | era_2016-2020 | 58 | 177632.5000 | 0.2275 | 0.1796 | -5.1635 | 11.9814 |
| baseline | era_2021-2024 | 43 | 66677.5000 | 0.1179 | 0.0839 | -7.5374 | 11.8830 |
| exit_L | era_2010-2015 | 59 | 628875.0000 | 1.1057 | 1.0343 | 3.5070 | 15.7965 |
| exit_L | era_2016-2020 | 58 | 588623.1250 | 0.7899 | 0.7403 | 1.2177 | 19.4578 |
| exit_L | era_2021-2024 | 43 | 232405.6250 | 0.4781 | 0.4392 | -3.0294 | 13.9817 |
| last_day | era_2010-2015 | 59 | 162263.7500 | 0.5304 | 0.3955 | -0.9218 | 5.8069 |
| last_day | era_2016-2020 | 58 | 212941.8750 | 0.5885 | 0.4849 | -0.5277 | 8.0951 |
| last_day | era_2021-2024 | 43 | 87330.6250 | 0.2969 | 0.2317 | -3.1247 | 7.3408 |
| F1_only | era_2010-2015 | 59 | -794737.5000 | -1.3642 | -1.4274 | -17.1817 | -6.8950 |
| F1_only | era_2016-2020 | 58 | -448255.0000 | -1.0960 | -1.1800 | -12.3337 | -2.8573 |
| F1_only | era_2021-2024 | 43 | -185019.3750 | -0.7503 | -0.8260 | -9.4053 | 0.4906 |
| ES_only | era_2010-2015 | 59 | -14142.5000 | -0.0233 | -0.0632 | -5.8396 | 5.6529 |
| ES_only | era_2016-2020 | 58 | 263127.5000 | 0.3703 | 0.3468 | -3.4209 | 12.6303 |
| ES_only | era_2021-2024 | 43 | 32595.0000 | 0.0695 | 0.0567 | -6.7901 | 9.3974 |
| ZN_only | era_2010-2015 | 59 | -109821.2500 | -0.3931 | -0.4553 | -4.1798 | 0.8368 |
| ZN_only | era_2016-2020 | 58 | -85495.0000 | -0.3005 | -0.3718 | -4.3244 | 1.3748 |
| ZN_only | era_2021-2024 | 43 | 34082.5000 | 0.1267 | 0.0774 | -4.6226 | 6.5856 |
| midmonth | era_2010-2015 | 63 | -296325.6250 | -0.5152 | -0.5849 | -9.1923 | 0.5293 |
| midmonth | era_2016-2020 | 58 | -287825.0000 | -0.4026 | -0.4462 | -12.1343 | 2.2888 |
| midmonth | era_2021-2024 | 45 | -146957.5000 | -0.3552 | -0.3971 | -11.2654 | 4.3797 |

## Actual versus early sign paths

| era | n | sign_changed_n | sign_changed_frac | old_L | actual_L | actual_predecision | actual_held_L | actual_held_F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2010-2015 | 63 | 9 | 0.1429 | 0.4856 | -0.7898 | -1.5943 | 0.6450 | -0.0872 |
| 2016-2020 | 60 | 8 | 0.1333 | 0.0918 | -1.0229 | -1.7057 | 0.6181 | 0.2160 |
| 2021-2024 | 44 | 8 | 0.1818 | 0.0892 | -1.6980 | -2.0080 | 0.3654 | 0.1180 |

## Paired mean differences

| a | b | mean_diff_bp | ci90_lo | ci90_hi |
| --- | --- | --- | --- | --- |
| exit_L | baseline | 5.6570 | 2.4047 | 9.0944 |
| last_day | baseline | 1.1929 | -3.9797 | 6.1357 |
| F1_only | baseline | -7.8890 | -14.1013 | -1.7733 |
| ES_only | baseline | 0.6403 | -2.2054 | 3.3971 |
| ZN_only | baseline | -2.3396 | -8.2575 | 3.1436 |
| baseline | midmonth | 5.8390 | -2.2936 | 14.3951 |

Confidence intervals are pointwise 90% circular three-month block bootstrap intervals (4,999 draws). They are not corrected for the exploratory family or prior searches. Detailed CSVs retain each monthly return, all years, direction and quarter-end subsets, daily attribution, and gate omitted-event attribution.

Reproduce: `.venv/bin/python research/2026-10-03-failure-analysis/timing_regimes/analyze.py`
