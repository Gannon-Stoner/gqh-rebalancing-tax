# HMM rebalancing-pressure replication: result

Spec: `SPEC.md`, SHA-256 `d171a42e…c6cc`, locked 2026-10-04 00:25 UTC before any return was computed (`spec_lock.json`).
Data: ES/ZN within-contract settlement returns, IS only, through 2024-10-01. OOS not opened. Protected files unchanged.
Reproduce: `python research/2026-10-03-hmm-replication/run.py` (about 4 s).

## Confirmatory (Holm over two one-sided tests, α = 0.05)

| Test | Ours (2011-06 → 2024-09, n = 3,346) | HMM (1997–2023, n = 6,226) | Holm p | Outcome |
|---|---|---|---|---|
| R1: Threshold < 0 | −0.369 (t −2.20) | −0.414 (t −3.6) | 0.027 | **Replicated** |
| R2: Calendar × week4 < 0 | −0.125 (t −1.25) | −0.303 (t −3.7) | 0.105 | **Not replicated** |

## Secondary (pre-declared, no pass/fail)

| Row | Threshold coef (t) | Calendar × week4 coef (t) |
|---|---|---|
| Newey-West(5) | −0.369 (−1.83) | −0.125 (−1.52) |
| Without momentum control | −0.255 (−1.94) | −0.119 (−1.18) |
| week4 excluding day L | −0.385 (−2.34) | **−0.238 (−2.45)** |
| From 2015-10 | −0.528 (−2.48) | −0.125 (−0.97) |
| Post-HMM sample (2023-03 → 2024-09, n = 386) | −0.498 (−1.22) | −0.015 (−0.09) |
| Equity leg only | −0.305 (−1.97) | −0.142 (−1.52) |
| Bond leg (−R_10Y) | −0.065 (−1.83) | +0.016 (+0.95) |

HMM front-running strategy (descriptive, approximate costs of 1.3 bp per unit |Δw|):

| Variant | Net annual return | Volatility | Sharpe | Skew | Ex Feb–Apr 2020 Sharpe |
|---|---|---|---|---|---|
| No first-session flip | 4.9% | 7.3% | 0.67 | 4.6 | 0.48 |
| With first-session flip (HMM) | 8.1% | 7.2% | 1.14 | 5.0 | 1.07 |

## Post-hoc (not in the spec, disclosed)

| Sample | Threshold coef (t) | Calendar × week4 coef (t) |
|---|---|---|
| Excluding Feb 15 – Apr 30, 2020 (51 days) | −0.169 (−1.29) | −0.132 (−1.74) |
| Excluding all of 2020 | −0.165 (−1.19) | −0.143 (−1.76) |

## Reading

- The Threshold effect has the right sign and HMM's magnitude, and passes the locked test. **More than half of
  the coefficient comes from the COVID crash.** Without those 51 days it is about −0.17, not significant.
- The month-end (Calendar) effect fails as specified. It is roughly twice as large and significant when day L
  (predicting the first session) is excluded, consistent with the phase-validation finding that first-session
  returns behave differently. That row was pre-declared but is secondary and not a confirmatory pass.
- Most of the strategy's edge over our earlier ES candidate comes from the first-session flip. Earlier work showed
  that part is mostly long-equity turn-of-month exposure, not rebalancing.
- Out of HMM's sample (386 days), the coefficients have the right sign but are not significant, as the power
  statement predicted.
