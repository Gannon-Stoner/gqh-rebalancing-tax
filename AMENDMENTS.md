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
