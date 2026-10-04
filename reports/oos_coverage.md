# Out-of-sample data coverage (2024-10-02 to 2026-10-02)

Data quality only, run before the single OOS evaluation: no strategy returns were computed. Prices appear only as spreads in ticks.

Databento dataset condition, 2024-10-02 to 2026-10-02: 670 days, not 'available' on 10: 2025-09-17 degraded, 2025-09-24 degraded, 2025-11-28 degraded, 2026-01-31 degraded, 2026-03-15 degraded, 2026-03-16 degraded, 2026-03-21 degraded, 2026-04-10 degraded, 2026-05-24 degraded, 2026-08-29 degraded.

## 0. Purchase

- Streamed files expected 5, in manifest 5; missing: none
- Batch jobs 1 (GLBX-20261004-SNWNBQG8VA oos_bbo_1m); batch files in manifest 25
- SHA-256 matches on disk: 30 of 30; quoted cost $11.44; 135 MB compressed

## 1. Settlement coverage

- XNYS sessions 502; with an ES final settle 502; with a ZN final settle 502
- Gap-audit rows: 3
  - 2024-12-07: settle on non-XNYS day
  - 2025-01-09: settle on non-XNYS day
  - 2026-04-03: settle on non-XNYS day
- ES: OOS panel rows 10559; without a FINAL-flag record (last record used, A14) 138; ranked by traded volume for want of open interest (A14) 22
- ZN: OOS panel rows 1521; without a FINAL-flag record (last record used, A14) 30; ranked by traded volume for want of open interest (A14) 3
- Last settlement date in the panels: ES 2026-10-02, ZN 2026-10-02 (2026-10-01 is the Sep-2026 exit)

## 2. Calendar, decision dates and events

- Qualifying sessions in the OOS window: 502
- Schedule rows by sample after the IS end: {'OOS': 24}; OOS months 2024-10 to 2026-09
- OOS months whose ex-ante dates differ from ex-post (A1): 0
- events in OOS: 24; usable (valid, tradable, data complete): 24; usable and PX-eligible: 22
- pseudos in OOS: 24; usable (valid, tradable, data complete): 24
- Databento-degraded days that are OOS sessions, and the schedule dates they carry:
  - 2025-09-17 (Wed): no schedule date
  - 2025-09-24 (Wed): 2025-09 entry
  - 2025-11-28 (Fri), early close: 2025-11 L
  - 2026-03-16 (Mon): no schedule date
  - 2026-04-10 (Fri): 2026-04 pseudo decision
- Usable OOS events whose window (anchor..exit) touches a Databento-degraded day: 6: ['2025-09 (2025-09-24)', '2025-11 (2025-11-28)', '2026-01 (2026-01-31)', '2026-03 (2026-03-21)', '2026-05 (2026-05-24)', '2026-08 (2026-08-29)']
- Usable OOS pseudos whose window (anchor..exit) touches a Databento-degraded day: 3: ['2025-09 (2025-09-17)', '2026-03 (2026-03-15, 2026-03-16)', '2026-04 (2026-04-10)']

## 3. Reference series

- OOS sessions 502; missing daily reference returns: ES 0, ZN 0
- Contract switches (8 per leg expected over two years): ES 8 (2024-12-17, 2025-03-18, 2025-06-17, 2025-09-16, 2025-12-16, 2026-03-17, 2026-06-16, 2026-09-15); ZN 8 (2024-11-26, 2025-02-25, 2025-05-27, 2025-08-26, 2025-11-24, 2026-02-25, 2026-05-27, 2026-08-26)

## 4. Minute data (outrights requested by exchange symbol, 14:00-16:30 ET extract)

- Held or reference contracts in OOS: 18 (ESH5, ESH6, ESM5, ESM6, ESU5, ESU6, ESZ4, ESZ5, ESZ6, ZNH5, ZNH6, ZNM5, ZNM6, ZNU5, ZNU6, ZNZ4, ZNZ5, ZNZ6)
- bbo-1m: OOS files 25 (records per file 12,239-169,903); ids not among the outright definitions 0; held or reference contracts with no OOS record: none
- ohlcv-1m: OOS files 3 (records per file 217,077-867,309); ids not among the outright definitions 0; held or reference contracts with no OOS record: none

## 5. Quotes at the 15:59 ET fill minute

Front = reference contract of the session (A8). Regular sessions only (early closes have no 15:59 minute, A2).

| Year | Regular sessions | ES fresh | ZN fresh | ES median spread (ticks) | ZN median spread (ticks) |
|---|---|---|---|---|---|
| 2024 | 61 | 61 | 61 | 1.0 | 1.0 |
| 2025 | 247 | 247 | 247 | 1.0 | 1.0 |
| 2026 | 189 | 189 | 189 | 1.0 | 1.0 |

Held contracts on PX fill days: 22 usable PX-eligible OOS events x 2 legs x (entry L-4, exit F1).

- Fills without a fresh quote: 0
- ES: spread median 1.0, 95th pct 1.0, max 1.0 ticks; 15:59 bar volume median 53,069, 10th pct 40,050, min 31,752 contracts
- ZN: spread median 1.0, 95th pct 1.0, max 1.0 ticks; 15:59 bar volume median 11,119, 10th pct 4,202, min 143 contracts

