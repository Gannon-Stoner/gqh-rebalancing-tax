# Amendments

Rules (HYPOTHESIS.md, header): after the `prereg-final` tag this file records only **bug fixes** and **data facts**. The constants, variants and tests in HYPOTHESIS.md and `config/frozen.yaml` do not change. Each entry says which kind it is.

## A1. Decision dates are ex-ante (bug fix: look-ahead), approved 2026-10-03

The frozen rule "L−k counts back over sessions" counts back from the realised L. So a session that is missing *after* a decision date changes which day was the decision day. That session can be an unscheduled closure or a missing ES/ZN settlement. The schedule follows the frozen rule as written. `gqh.calendar.decision_shift` recomputes the dates on the calendar a live trader knew at the close of each decision date: the observed sessions through that date, then the scheduled XNYS sessions, with closures not yet announced added back.

On XNYS sessions, 2010-06 through 2026-12, one month shifts. Oct 2012: the Hurricane Sandy closures of 10-29 and 10-30 were announced on 10-28 and 10-29, after the ex-post decision on 10-22.

| Oct 2012 | L−17 | L−14 | L−13 | L−8 | L−5 (decision) | L−4 (entry) | n |
|---|---|---|---|---|---|---|---|
| ex-post (used) | 10-04 | 10-09 | 10-10 | 10-17 | 10-22 | 10-23 | 16 |
| ex-ante | 10-08 | 10-11 | 10-12 | 10-19 | 10-24 | 10-25 | 18 |

The Bush (2018-12-05) and Carter (2025-01-09) closures were public before every decision date they move. **Decision (approved):** the ex-post dates are look-ahead, because a trader at L−5 could not know about a closure announced later. The strategy therefore trades on `gqh.calendar.trading_schedule`, which uses the ex-ante dates for every flagged row and leaves all other rows unchanged. For Oct 2012 the holding window has only 3 returns, because the market was closed. The frozen σ̂·√5 scaling is still applied. Once settlements are loaded, `decision_shift` is rerun on the qualifying-session calendar. Every month it flags because of a missing settlement is added here. An event is invalid if an ex-ante date has no settlement.

## A2. XNYS early closes on schedule dates (data fact: calendar)

On XNYS 13:00 ET early-close sessions, CME equity and rates futures also close early. So the regular settlement clocks (ES 16:15/16:00 ET, ZN 15:00 ET) and the PX fill minute (15:59 ET bbo-1m) do not exist on those days. A 15:59 bar could carry a stale quote. The code does not guess a replacement:

- `es_settle_clock`, `zn_settle_clock`, `executable_fill_minute` and `zn_bond_strike` return `EARLY_CLOSE` on these dates.
- The schedule's `early_close` column, and `early_close_hits`, list every affected date column.

Affected schedule dates (month of the event row):

- IS decision L−5: 2012-11, 2018-11.
- IS entry L−4: 2012-12, 2013-12, 2014-12, 2015-12, 2017-11, 2018-12, 2019-12, 2020-12, 2023-11.
- IS L: 2013-11, 2014-11, 2019-11 (and the next row's drift base prev_L).
- IS exit F1: 2017-06, 2023-06.
- That is 16 of 171 IS event rows. No pseudo-event date is affected.
- OOS (calendar only, no data loaded): L in 2024-11 and 2025-11; L−4 in 2024-12, 2025-12 and 2026-12.

**Decision (approved):** on these dates there is no 15:59 ET fill minute, so PX drops every event whose entry (L−4) or exit (F1) falls on an early close. That is 11 of 171 IS events, flagged by `px_eligible` in `trading_schedule`. PG is also reported on the same PX-eligible subset, so the PX vs PG comparison is matched. Settlement-based rows (PG, P0, PD, PE, PP) keep every event, because CME publishes settlements on early-close days. The §6.2 clock diagnostic excludes early-close days.

## A3. Pseudo-event n (bug fix: code)

The §3 pseudo-event rule says "same formulas with drift since the previous L". For a pseudo decision at M = L−14, n is therefore the number of sessions in (prev_L, L−14] = `n_sessions_month − 14`. The first schedule draft exposed only the event n (sessions in (prev_L, L−5]), which would have shrunk every pseudo |z| by about √(6/15). The schedule now carries `n_since_prev_L_pseudo`. `n_since_prev_L(cal, date)` gives n for any decision date, including the §6.1 dose frozen at L−12.

## A4. Synthetic null specification for size/power checks (harness specification; approved 2026-10-03, before any market data)

The protocol names the null family (AR(1)-GARCH(1,1)-t5) but not its parameters. They are fixed here, before any data, in `gqh.synth.PROTOCOL_NULLS`:

| Setting | Values |
|---|---|
| Base | φ = 0.05, GARCH α = 0.08, β = 0.90, t with ν = 5, ES daily vol 1.1%, ZN daily vol 0.40%, ES/ZN correlation −0.2 |
| Stress | the same, with correlation +0.3 (the 2022 regime) |
| H2 null | ordinary reversal with the same slope at month-end and pseudo-events: c = c_pseudo = −0.10, c_E = 0 (`H2_REVERSAL_NULL`) |

Each null is generated as daily ES/ZN legs and run through the real schedule and signal code. The H1/H2 bootstrap must reject at 3–7% under every null, over at least 500 panels.

## A5. Pseudo-event signal timing (clarification; approved 2026-10-03)

Pseudo-event σ̂ and drift are computed with data through the pseudo decision date M = L−14 only. "Data through L−5" in §3 refers to the month-end event; using it for a pseudo-event would be look-ahead, because L−5 is after the pseudo exit at L−8.

## A6. Pseudo-event ES contract (clarification; before any market data)

The event rule takes the "highest open-interest outright at L−8". Applied literally at the pseudo anchor L−17, it picks the expiring front contract in every quarterly month, because the ES front still holds the most open interest early in March, June, September and December. That contract expires before the pseudo exit, so those pseudo-events would become untradable. Pseudo-events would then exclude every quarter-end month, which biases the H2 comparison.

Pseudo-events therefore take the highest-OI ES outright **among contracts expiring after the pseudo exit**. Events keep the frozen rule verbatim: if the selected contract expires on or before F1, the event is flagged untradable rather than substituted. On realistic open-interest roll patterns this never binds for events, because open interest leaves the front before L−8. For ZN, pseudo-events take the nearest contract whose first position day is after the pseudo exit.

## A7. EWMA initialization (implementation detail; before any market data)

σ̂ is a zero-mean EWMA (λ = 0.94) of daily X, using data through the decision date.
- The recursion starts from the mean of the first 21 squared returns.
- σ̂ is undefined until 63 valid daily returns have been seen. Events before that are invalid; with data from 2010-06-07, the first valid event is September 2010.
- A missing daily return leaves the variance unchanged; it is never filled.

## A8. Which contracts feed which quantity (clarification; before any market data)

- **Drift D and σ̂** use reference daily within-contract returns. The return on session t is computed on the outright with the highest open interest on t−1 that still trades on t (ES: not expired; ZN: before its first position day). Both prices come from one contract, so roll gaps never enter.
- **Progress A and outcome Y** use the contracts the event actually holds (A6 and §2), so Y is the traded position's return.

Missing settlements are never filled. A gap inside a drift window makes D undefined, and the event is invalid.

## A9. Pilot data facts (data facts; pilot 2020-10-01 to 2021-01-29, no returns computed)

From `reports/pilot_audit.md`, produced by `scripts/pilot_audit.py`:

- **Settlement records.** CME publishes several settlement records per contract and trade date. The loader keeps the last record carrying the FINAL flag (bit 1) and excludes intraday settlements (bit 8), as Databento documents; `ts_ref` is not localized. CME also publishes a FINAL price of 0.0 for newly listed deferred contracts that have not traded yet (e.g. ESH2 and ZNU1 in Dec 2020). That 0.0 is a placeholder and is treated as no settlement. In the pilot, front contracts had a final settlement on every XNYS session (83/83 for each leg), published at a median of 19:13 ET and no later than 20:20 ET, which is always before the next session.
- **Settlement clocks.** ES settlements sit closest to the 16:15 ET quote before 2020-10-26 and to the 16:00 ET quote after it. ZN settlements sit within half a tick of the 15:00 ET quote. Both match the frozen clocks.
- **Quote and bar stamps.** `bbo-1m` records are stamped at the end of their minute, and a missing minute means no change. `ohlcv-1m` bars are stamped at the start of their minute. The PX fill "at 15:59 ET" is therefore the bid/ask state at 15:59:00 ET: the last `bbo-1m` record with `ts_recv` ≤ 15:59:00 ET, no more than 5 minutes stale. Otherwise there is no fill. The 2 pilot dates without a fresh quote are early closes, consistent with A2.
- **Cost assumptions.** The front ES and ZN bid/ask spreads at 15:59 ET were 1 tick at the median and at the 95th percentile, which supports the frozen half-spread costs.
- **Rolls.** The reference series switched ES on 2020-12-15 (before the 12-18 expiry) and ZN on 2020-11-25 (before its derived 11-27 first position day). The Nov-2020 event holds ESZ0/ZNH1 and the Dec-2020 event holds ESH1/ZNH1, as the frozen rules require.

## A10. In-sample pull boundaries (data fact; 2026-10-03, before any return was computed)

`data/download.py` buys the in-sample data as follows. Every file is recorded with its request and SHA-256 in `data/manifest.json`.

- **Statistics run to 2024-10-02 06:00 UTC (02:00 ET), not midnight.** CME can publish the final settlement after 00:00 UTC; in the pilot the latest arrived at 20:20 ET, which is 00:20 UTC (A9). Without the tail, the 2024-10-01 final settlement could be lost, and that settlement is the exit of the last in-sample event (Sep 2024).
  - The tail also carries records for trade date 2024-10-02, which CME publishes during the overnight session that opens at 18:00 ET on 10-01.
  - `gqh.panel` drops every record dated 2024-10-02 or later until the `freeze-final` tag exists. `reports/is_coverage.md` counts those records by type only.
- **Definitions and minute data end at 2024-10-02 00:00 UTC (20:00 ET on 10-01).** Their last two hours belong to the 2024-10-02 Globex session. Nothing reads them, because the minute extract keeps only 14:00–16:30 ET on in-sample sessions.
- **Minute data covers outright quarterly contracts only.** `bbo-1m` and `ohlcv-1m` are requested by exchange symbol (ES/ZN × H/M/U/Z × one-digit year), and Databento resolves each symbol to the contract listed on each date. Calendar spreads are not bought; the strategy never trades them.
- **Data quality.** Databento flags 22 days in the range as "degraded" and none as missing (`data/dataset_condition.json`, queried 2026-10-03). The coverage report lists every in-sample event whose window touches one of these days.

## A11. Engine implementation details (clarification; 2026-10-03, before any return was computed)

The protocol fixes sizing, caps, integer contracts and costs, but not the details below. `gqh.engine` implements them, and `tests/test_engine.py` tests them on synthetic data only.

- **Contract count.** Each leg holds round-half-up(N / (price × multiplier)) contracts, where N is the frozen leg notional (after the 0.75×NAV per-leg cap). The price is the held contract's settlement on the decision session (L−5; L−14 for pseudo-events), the last price known when the decision is taken. A leg that would exceed the cap after rounding is floored to it, so gross stays ≤ 1.5×NAV.
- **Below one lot.** If either leg rounds to zero contracts, the event is not traded. One leg alone is not the 1:1 spread.
- **Rounding error.** "Ideal" P&L uses the unrounded contract counts on the same prices. Integer minus ideal is the rounding error that §9 reports.
- **Gate hurdle.** C = (round-trip cost of the integer position at 1× costs) / (N·σ̂·√5). It is computed ex ante with the sizing above.
- **Cost multiplier.** Gate decisions are taken at 1× costs. The 2× rows re-cost the same trades, so decisions are identical across cost rows.
- **PX fills.** Fills use the A9 quote state at 15:59 ET: buys pay the ask, sells receive the bid. The fill already pays the real half-spread, so PX charges k·fee + (k−1)·half-spread per contract per side: fee only at 1×, and one extra frozen half-spread plus a second fee at 2×.
  - No fresh entry quote on either leg: PX does not trade the event (`no_entry_quote`).
  - No exit quote: that leg exits at the exit settlement and pays the settlement-row cost for that side (`px_exit_fallback`). Both cases are counted in the results.
- **Units.** P&L is in USD on the fixed $10M reference NAV, with no compounding; an event return is net P&L / NAV. The daily series marks the held contracts to their settlements and books costs half on the entry session and half on the exit session. Its sum equals the ledger (tested).

## A12. Strategy-row details (clarification; 2026-10-03, before any return was computed)

`gqh.gate` and `gqh.strategy` implement §3–§4, tested in `tests/test_gate.py` and `tests/test_strategy.py` on synthetic data only.

- **Completed past events.** These are valid events whose exit session is strictly before the current decision session. After `is_end`, only events that exited by `is_end` are used, so every OOS forecast uses the single model frozen at the end of IS.
- **PD** fits the restricted model Y = a + b·dose on the same window.
- **PP** runs the same procedure on pseudo-events: it is trained on past pseudo-events and uses the pseudo-event hurdle.
- **Common segment.** §4 compares all rows "on the same walk-forward IS segment". That segment starts in the first month in which both the event gate (PG/PD) and the pseudo-event gate (PP) have at least 60 completed observations. Every row is flat before it.
- **PE.** p is PG's IS participation rate: the share of the events P0 trades in the IS segment that PG also trades. PE trades every P0 event at p × the frozen leg notional, with the same integer rounding (A11). p is frozen for OOS.

## A13. Inference implementation (clarification; 2026-10-03, before any return was computed)

`gqh.stats` implements §3 "Inference" and §5. `tests/test_stats.py` checks it against statsmodels and the Bailey–López de Prado worked example.

- **Month-block bootstrap.** The bootstrap is a circular block bootstrap over the contiguous calendar-month range of the sample, block 3, with months that have no observation kept as empty slots. A drawn month brings every row it holds, so an event and its pseudo-event stay together. A draw is therefore the original rows with integer weights.
- **Test statistic.** The tests are studentized (percentile-t): t* = (β̂* − β̂)/se*, with HC0 standard errors recomputed in every draw. The one-sided p-value is (1 + #{t* ≥ t̂})/(B + 1) for H1 (b > 0), and the mirror image for H2 (c_E < 0). CIs are 90% percentile-t intervals.
- **Fallback and sensitivity.** The fallback is a Rademacher wild bootstrap with one sign per month, null imposed, studentized the same way. Newey-West(3) uses Bartlett weights over month-summed scores with a lag of 3 months.
- **ΔSR CIs** use the same circular month-block draws applied jointly to both rows' monthly returns (0 in flat months).
- **DSR.** The DSR uses per-period (monthly) returns with ddof = 1, sample skewness and raw kurtosis. V[SR] defaults to the null 1/T. E[max SR] is floored at 0.
- **Size/power calibration.** `scripts/calibrate_inference.py` runs 500 panels per scenario. Each panel is a full IS history from the A4 nulls, run through the real schedule, contract and signal code, with 9,999 draws per test. Planted effects are added to Y of the computed signal panel (Y += b·dose + c·A), so the planted slopes are exact and do not feed back into later drifts or σ̂.
  - Under the H2 reversal null, only H2's null holds. H1 omits A, and A is mechanically correlated with dose: both are built from the same month-to-date move. So that scenario's H1 rejection rate measures how much ordinary reversal leaks into H1. It is reported, not held to the size band.

## A14. Pre-MDP 3.0 statistics: settlement flags and missing open interest (data fact and bug fix; 2026-10-03, before any return was computed)

The in-sample statistics show two gaps before CME's MDP 3.0 feed (June 2010 to November 2015). The first coverage run surfaced them; `reports/is_coverage.md` has the counts, which are aggregates only.

1. **Settlement flags.** No settlement record carries the FINAL flag from 2010-06 to 2011-03. From 2011-04 to 2015-09, only about 22% of outright (contract, trade date) keys have one. From 2015-Q4, 98–99% do.
   - The A9 rule "no FINAL record means no settlement" therefore dropped about 1,140 in-sample sessions. That is a bug, not a data fact: the frozen rule is "final SETTLEMENT_PRICE; last record per (instrument_id, ts_ref)".
   - **Fix:** the settlement is the last FINAL-flagged record of the key (non-intraday, price > 0); if the key has none, it is the key's last such record (`final_flag` = False in the panel).
   - **Evidence:** wherever both exist, the last record's price equals the flagged final on 100% of 26,400 keys from 2015-Q4 and on 99.75% of 2,364 keys from 2011–2015. The 6 exceptions (ES, 2012-12-03/04, ≤ 0.1 points) resolve to the flagged final.
   - Without a flag, the last record is published on the trade date between 17:00 and 21:00 ET (CME's settlement publication window) for 96% of keys.
   - Fallback use: ES 5,859 and ZN 5,753 settlements, almost all 2010–2015; 2–28 a year afterwards.
2. **Open interest and cleared volume** are absent from the feed until 2015-11-19 for both roots. The frozen selection rules (ES: highest open interest at L−8; reference returns: the previous session's highest-open-interest contract) cannot be applied to those dates as written.
   - **Substitute:** on a date where no contract of the root has published open interest, contracts are ranked by that trade date's traded volume, summed from the outright ohlcv-1m bars (Globex day 18:00–17:00 ET; `gqh.data.daily_volume`). Dates with open interest use it as frozen.
   - The same date's volume is known at that session's close, so the ranking stays ex ante, as open interest does.
   - **Validation**, where both exist (2015-11-19 → 2024-10-01): the volume ranking picks the same reference contract on 98.9% (ES) and 98.0% (ZN) of sessions. It picks the same ES event contract at L−8 on 106/106 events. The differences sit in roll weeks, where volume moves a few days before open interest; both contracts are then liquid, and returns are within-contract either way.
   - Capacity and impact use the same traded volume where cleared volume is absent.
3. **Remaining gaps and decision shifts.** After the fix, ES settles exist on 3,601 of 3,605 XNYS sessions and ZN on 3,603.
   - Missing: ES on 2014-06-12 and 2014-09-23/24/25; ZN on 2020-02-27 and 2020-06-30. All six are days Databento flags as degraded.
   - Under A1, `decision_shift` on the qualifying calendar flags, beyond Oct 2012: 2014-06 (pseudo-event), 2014-09, 2020-02 and 2020-06. These trade on the ex-ante dates.
   - 2014-09 is invalid, because its ex-ante decision day 2014-09-23 has no ES settlement.
   - Result: 170 of 171 IS events and 171 of 171 pseudo-events are usable; 159 events are PX-eligible.
   - Seven usable events and six pseudo-events have a degraded day inside their window, and all have the settlements they need. They are listed in the coverage report.

## A15. Calibration results, deflation counts, second engine and risk inputs (data facts and clarification; 2026-10-03, before any return was computed)

- **Inference calibration** (`reports/inference_calibration.md`; 500 synthetic panels per scenario, 9,999 draws, A4 nulls through the real schedule and signal code).
  - Every size cell is inside [0.03, 0.07] for the month-block bootstrap: H1 0.064 and H2 0.048 (base), H1 0.054 and H2 0.056 (stress correlation), H2 0.038 (ordinary-reversal null). The registered primary method stands, and the wild fallback is not triggered.
  - Recorded, not tested:
    - Under the ordinary-reversal null, H1 rejects at 0.126. Reversal leaks into H1 because A and dose are correlated (A13).
    - H1 power is 0.11 at b = 0.05 and 0.20 at b = 0.12, so H1 is weak across the whole predicted range.
    - H2 power at c_E = −0.27 is 0.58, not the registered 0.80. With the real signal construction, the 80%-power MDE is about 0.37.
  - The note reports these powers and does not read a null H1 or H2 as evidence of absence.
- **Deflation counts.** The DSR is reported at N = 6 (the registered rows), N = 35 (adding the 29 logged prior month-end variants) and N = 80 (adding the 45 logged trend/vol variants).
- **Second engine.** `gqh.bt_replay` replays every traded event of the settlement rows in Backtrader 1.9.78.123, the engine of the track's Webull starter kit. It uses:
  - Databento settlement bars of the held contracts;
  - the frozen multipliers;
  - CME margins;
  - the frozen per-side cost as a fixed per-contract commission;
  - fills at the close of the order bar (cheat-on-close). A flat placeholder bar after the exit lets the exit fill at the exit settlement.
  - Decisions, contracts and sizes come from the engine, so the replay checks fills and accounting, not the signal. On synthetic data it matches the engine to the cent at 1× and 2× costs.
  - PX (minute quotes) is not replayed.
- **Margins.** These are CME maintenance margins as published on 2026-10-03 (`config/margins.yaml`, with sources): ES $26,164 per contract (12/2026, long) and ZN $1,875. Today's levels are applied to every year, which overstates margin needs in earlier, lower-priced years.
- **Factors.** Ken French daily Mkt-RF, SMB, HML and Mom were retrieved 2026-10-03 (`data/download_factors.py`; URLs and SHA-256 in `data/factors/manifest.json`). The ZN reference return is added as a factor. Dates after `is_end` stay hidden until `freeze-final`.

## A16. Disclosure: partial unmasking during the masked dry run (2026-10-03, before `freeze-is`)

Before tagging `freeze-is`, `scripts/masked_dry_run.py` ran the full pipeline on the real IS data to catch crashes and accounting errors without showing results. It ran twice: first with quotes for 2010–2012 only, then again after its output was reduced. It confirmed that every results section is produced and that Backtrader reproduces the engine on every replayed trade. It also revealed more than intended:

- The number of PG trades in the IS walk-forward segment: 69, against 104 P0 trades. The PX "not selected" count gave the same figure.
- **The sign of the headline results.** The list of undefined fields showed that "months needed for t = 2" is undefined for PG, which happens only when PG's IS Sharpe at 1× costs is ≤ 0. It is defined for P0, so P0's IS Sharpe is > 0.

No magnitude, p-value, coefficient, confidence interval or other statistic was seen. Nothing in `HYPOTHESIS.md` or `config/frozen.yaml` can change. **No code, parameter or reporting choice is changed in response.** Any later change before `freeze-is` is a bug fix or a structural fix whose need is evident without results, and it is documented here with its reason.

The dry-run script now prints only pass/fail checks: no gate-dependent counts and no list of undefined fields. The incident is logged in `trials.jsonl`, and the note discloses it under prior looks.

**Stress table (structural fix, approved by the author 2026-10-03, after the disclosure above).** The registered stress months 2011-08 and 2015-08 fall before the common walk-forward segment, where every row is flat, so a stress table of the rows would show no position there. The stress table therefore reports the underlying trade: P0 on every valid IS event, sized and costed as frozen. The need for this is evident from the schedule alone, without results. It is descriptive and does not touch PG, the confirmatory tests or any reported row. The segment-limited stress tables of PG and P0 stay in `results_is.json`.

## A17. In-sample minute-data facts (data facts; 2026-10-03, from `reports/is_coverage.md`, before `freeze-is`)

- **Files.** 20 streamed files plus 142 monthly bbo-1m batch files (2013-01 to 2024-10-01). All 162 SHA-256 values match the manifest. Quoted cost $80.28 (the approved quote); 0.81 GB compressed.
- **Contracts.** Every contract ever held or used for reference returns (117) is present in both bbo-1m and ohlcv-1m, including all 98 whose one-digit exchange symbols repeat across decades. No non-outright instrument entered the files.
- **Quotes at the 15:59 ET fill minute.** The front contracts have a fresh quote (≤ 5 minutes old, A9) on every regular session except 3 in 2014 (Databento-degraded days) and 1 in 2010. For the 159 usable PX-eligible IS events, every held contract has a fresh quote on both the entry (L−4) and exit (F1) days. No PX fill needs the exit fallback for lack of data. Spreads are 1 tick at the median and the 95th percentile, 2 ticks at most, which supports the frozen half-spread costs.
- **Thin ZN volume at 15:59 ET.** The held ZN contract's 15:59 ET bar trades a median of 1,190 contracts (10th percentile 94, minimum 0). ZN settles at 15:00 ET, and around rolls the held contract can be the deferred one. Quotes exist at that minute, but trades can be sparse, so PX capacity is reported on that minute and is expected to bind on ZN. Settlement rows use the 14:59 ET ZN window.
