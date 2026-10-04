# CFTC positioning test of month-end rebalancing flows: result

Spec: `SPEC.md`, SHA-256 `43c0c196…56db`, locked before any CFTC position value was downloaded (`spec_lock.json`).
Data: CFTC TFF futures-only, ES `13874A` and ZN `043602`. Files are in `data/`; the SHA-256 is printed at download.
Report dates are from 2010-06-08 to 2024-10-01; there are 171 month-end windows. OOS not used.
Reproduce: `python research/2026-10-03-cftc-flows/run.py`.

## Confirmatory (asset managers, month-end window, Holm over two one-sided tests)

| Test | Prediction | Coefficient (t) | Holm p | Outcome |
|---|---|---|---|---|
| F1: ES | Sell when equities are overweight (b < 0) | **+0.75 (+1.94)**, wrong sign | 0.97 | Not confirmed |
| F2: ZN | Buy when equities are overweight (b > 0) | +0.41 (+1.51) | 0.13 | Not confirmed |

## Secondary (pre-declared, no pass/fail)

Asset managers, coefficient on drift D (t):

| | Month-end | Mid-month placebo | Pooled difference (month-end × D) |
|---|---|---|---|
| ES | +0.75 (1.94) | +1.90 (9.20) | **−1.15 (−2.62)** |
| ZN | +0.41 (1.51) | −1.25 (−4.21) | **+1.66 (+4.13)** |

Other rows: in ES at month-end, dealers −0.50 (t −2.38) and non-reportables −0.34 (t −2.09). By subperiod, ZN at
month-end is +1.40 (t 2.58) in 2010–15 and −0.06 (t −0.21) in 2015–24. The quarter-end interaction is not
significant. The roll-week control changes nothing.

## Post-hoc (not in the spec): control for returns inside the window

D includes returns earned during the position window itself, and asset managers' futures positions track same-week
returns strongly (index-fund equitization and flow chasing). Splitting D into the drift before the window
(D_pre ≈ D − 0.24·R_win) and the in-window return gives (sample from 2011-06, n = 160):

| | Month-end D_pre | Mid-month D_pre | Pooled difference (month-end × D_pre) |
|---|---|---|---|
| ES | −0.01 (−0.04) | +0.96 (3.87) | **−0.97 (−2.74)** |
| ZN | +0.58 (2.09) | −0.81 (−1.95) | **+1.39 (2.78)** |

Order of magnitude: −0.97 × the median ES open-interest notional (about $362bn) implies roughly **$350bn** of assets
rebalancing through ES futures. This is a scale indication only.

## Reading

- On the locked absolute tests, asset managers do **not** sell ES and buy ZN at month-end in response to drift.
  Their dominant behaviour is pro-cyclical: they add equity futures after equity gains.
- Relative to their own mid-month behaviour, both legs shift in the rebalancing direction at month-end. This was
  pre-declared but secondary, and it survives the post-hoc control for in-window returns. At month-end the usual
  trend-following in ES switches off, and in ZN it reverses into bond buying.
- The ZN month-end buying is concentrated in 2010–15. That is consistent with flow-based evidence weakening in the
  same period where our return evidence is weakest.
- Weekly snapshots, cash, swap and other-contract rebalancing, and self-reported trader categories all limit this
  test. It cannot measure total rebalancing flow.
