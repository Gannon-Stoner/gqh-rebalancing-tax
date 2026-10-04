# In-sample correctness audit — 2026-10-03

Scope: read-only review of frozen code and original in-sample data through 2024-10-01; supplementary outputs only in this directory. No new strategy rule, no out-of-sample download or evaluation, and no modification to original results or trial logs. The primary result reproduces in this audit: PG -$36,978.75, P0 +$183,525.00. No evidence found that a sign, roll-gap, fill-accounting or decision-time publication bug explains the primary loss.

## Findings in priority order

### 1. The gate selected the worse subset; execution costs are secondary

Among 104 baseline trades in the common 108-month period:

| Subset | Trades | Net P&L | Mean scaled outcome Y |
|---|---:|---:|---:|
| Selected by PG | 69 | -$36,978.75 | -0.04119 |
| Rejected by PG but tradable in P0 | 35 | +$220,503.75 | +0.14357 |

PG's gross P&L was already negative (-$9,846.875). Costs of $27,131.875 deepen the loss. Thus the failure is not a profitable predictor overwhelmed only by costs. Walk-forward forecast versus realized Y correlation is -0.14669. The coefficient on progress is negative in 88.9% of evaluated months, so the model usually implements the hypothesized direction; nevertheless, its total forecast fails to rank opportunity usefully in this realization.

The time-varying forecast components' standard deviations are intercept 0.08194, dose contribution 0.10478, progress contribution 0.05700. The gate's decisions are not determined by progress alone. These are descriptive, post-result diagnostics, not additional confirmatory discoveries.

Evidence: `audit_results.json` (`gate_selection`), `event_audit.csv`, `risk_target_audit.json`.

### 2. Missing matched execution comparison exaggerates apparent PX improvement

A2 explicitly promises PG on PX-eligible dates (`AMENDMENTS.md:34`). `src/gqh/pipeline.py:103` reports each row on the common calendar but does not also report PG restricted to PX's traded dates.

| Comparison | Trades | Net P&L | Annualized Sharpe |
|---|---:|---:|---:|
| PG, all eligible settlement events | 69 | -$36,978.75 | -0.04707 |
| PG, same dates as PX | 64 | +$36,439.375 | +0.04712 |
| PX | 64 | +$42,295.625 | +0.05528 |

The matched executable-versus-settlement difference is **+$5,856.25 and +0.00815 Sharpe**. The unmatched difference is +0.10235 Sharpe, predominantly because PX omits five early-close events whose settlement PG P&L totaled -$73,418.125. All comparisons above retain all 108 calendar months and put zero in excluded months.

This is an omission in reporting, not a change to or rescue of PG's strategy result. The actual matched quote test supports very similar performance at the two clocks.

Evidence: `audit_results.json` (`matched_execution`, including all excluded months).

### 3. Settlement capacity treats nonexistent early-close windows as zero liquidity

`src/gqh/capacity.py:28` always uses the regular ES and ZN settlement minutes. It does not call the early-close calendar helpers. A2 correctly preserves settlement trades on early-close dates, but these dates have different actual settlement clocks.

All five PG settlement-capacity failures of the one-lot-at-1% criterion come from these early-close events. Querying nonexistent ES regular-clock bars produces zero, labels ES the binding leg, and reports zero capacity. They are not measured failures of actual early-close settlement capacity.

| Settlement-capacity summary | All 69 events as saved | 64 regular-close events |
|---|---:|---:|
| One-lot criterion pass share | 92.75% | 100% |
| Median NAV at 1% window participation | $43.70M | $55.45M |
| 10th percentile | $8.24M | $14.67M |
| ZN binding share | 72.46% | 78.13% |

The correct near-term treatment of the other five capacity observations is **unmeasured at the appropriate early-close clock**. Excluding them is a descriptive complete-case audit, not evidence that they have adequate capacity. PX still has its genuine, separately measured sparse-volume issue at 15:59.

Evidence: `audit_results.json` (`capacity_early_close`). This is a capacity-reporting bug and does not change PG returns.

### 4. The reported final coefficients are one completed event stale

`src/gqh/pipeline.py:183` takes coefficients from the last historical forecast row. That forecast had to exclude the final event's own outcome. The model at the end of the IS period should include that now-completed event.

| Gate | Last forecast training count | All completed IS count | Last-forecast coefficients | Actual end-IS coefficients |
|---|---:|---:|---|---|
| PG, constant/dose/progress | 167 | 168 | 0.044164, -0.029338, -0.062906 | 0.041307, -0.027382, -0.064071 |
| PD, constant/dose | 167 | 168 | 0.036314, -0.001092 | 0.032107, +0.002382 |
| PP, constant/dose/progress | 168 | 169 | -0.035825, -0.068059, -0.006662 | -0.038736, -0.056731, -0.002252 |

`src/gqh/gate.py:56` correctly builds future forecasts using all outcomes completed by `is_end`; therefore the implementation's future frozen model is correct. The JSON field is misleading and should be corrected before presenting it as the exact frozen coefficients. This has **zero effect on historical trades or returns**.

Evidence: `audit_results.json` (`final_coefficients`).

## Timing and data integrity checks

- Independently recomputed every valid outcome from the held contracts' entry and exit prices. Maximum discrepancy from Y is exactly 0. Every decision precedes entry and every entry precedes exit.
- Neither held-contract decision settlements nor settlements used in monthly drift were published after the next entry's 15:00 ET deadline. Final settlements may be published after the decision session's clock, but there is a full session before entry; the implementation does not claim the intervening return.
- Audited 39,366 IS outright OI records and 4,452 selected reference OI observations. Four were published later than the following session's 15:00 ET: both legs on 2017-04-24 and 2020-09-21. None was late for the actual event or pseudo-event signal's next-entry deadline. No event-contract OI record was late for actual use. The general statement that previous-day OI is always known by the next close is imperfect, but no decision-level leakage was demonstrated here.
- The official [Databento GLBX.MDP3 specification](https://databento.com/docs/venues-and-datasets/glbx-mdp3) confirms the implementation's settlement flag values: final 1, actual 2, trading tick 4, intraday 8. The same source notes that pre-May-2017 `ts_recv` mirrors exchange sending time; availability checks in that era are source-timestamp checks rather than independent capture-time verification.
- The final-settlement loader preserves publication timestamps, but the OI loader discards them (`src/gqh/panel.py:100`). A production-quality as-of panel should retain OI timestamps to make this check automatic, even though it did not explain the observed loss.
- PG has no cap-bound trades. Recomputing annual realized-to-target RMS against capped continuous-position risk gives the exact same values and the same 70% band hit rate. The calibration miss is not caused by the notional cap.

## Tests and reproduction

Targeted existing tests: **121 passed, 1 skipped**, covering calendar, contract selection, signal timing, gate freezing/leakage, engine accounting, quote freshness, inference, and Backtrader replay. No strategy parameters or frozen files were changed.

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/audit/audit.py
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/audit/oi_publication_audit.py
.venv/bin/python -m pytest -q tests/test_calendar.py tests/test_contracts.py tests/test_signals.py tests/test_gate.py tests/test_engine.py tests/test_quotes.py tests/test_stats.py tests/test_bt_replay.py
```

The independent return/sign checks, publication-time checks, and matched execution comparison provide evidence against an easy software-error explanation. The negative primary result stands; the above corrections improve the precision of the execution/capacity/model-freeze narrative.

## Independent follow-up: the final holding day destroys much of the baseline return

A separate timing analysis prompted this targeted audit. I independently reconstructed the final holding increment using **the exact original P0 positions, integer quantities, and held contracts**, and compared the result against fresh simultaneous 15:59 quotes. This is a post-result diagnostic, not the registered strategy.

| Original position subset | Number | L→F1 gross P&L |
|---|---:|---:|
| All P0 trades | 104 | -$610,953.125 |
| Short ES / long ZN | 72 | -$619,978.125 |
| Long ES / short ZN | 32 | +$9,025.00 |
| PG-selected trades | 69 | -$166,481.25 |

The ES leg accounts for -$524,687.50 of the all-P0 final-day loss; ZN accounts for -$86,265.625. Removing that day while keeping the original P0 position and charged round-trip costs changes total net P&L from **+$183,525 to +$794,478.125**, and annualized Sharpe from **0.13390 to 0.63422**. For PG the corresponding net P&L changes from -$36,978.75 to +$129,502.50.

The loss is not a roll-price discontinuity or a date-order mistake: all 104 L/F1 pairs are consecutive qualifying sessions, F1 is in the following calendar month, and both contracts remain tradable at F1. No cross-contract price ratio enters this audit.

**Quote corroboration:** 101 of the 104 observations have fresh 15:59 bid/ask on both L and F1. On those same dates, L→F1 P&L is -$612,021.875 using settlements and **-$565,239.0625 using simultaneous 15:59 midquotes**. Comparing liquidation on the same executable bid/ask side instead gives -$565,131.25. The per-event midquote/settlement P&L correlation is 0.97916. Thus most of the adverse final-day result survives an independent simultaneous mark. The three unmatched months are 2017-06, 2019-11 and 2023-06 (early-close quote availability); they are retained in the settlement diagnostic and omitted only from the matched quote check.

This supports a real timing mismatch in the tested holding window. It does not establish that an L exit will work on unseen data, nor does it alter the original failed registered result. It provides a concrete, economically interpretable subject for a separately labeled follow-up.

Evidence and reproduction: `f1_audit_results.json`, `f1_event_audit.csv`, and

```sh
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/audit/f1_audit.py
```
