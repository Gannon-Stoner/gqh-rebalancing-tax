# In-sample data coverage (2010-06-07 to 2024-10-01)

Data quality only: no strategy returns were computed. Prices appear only as spreads in ticks.

Databento dataset condition, 2010-06-06 to 2024-10-01: 4485 days, not 'available' on 22: 2014-06-11 degraded, 2014-06-12 degraded, 2014-06-13 degraded, 2014-06-15 degraded, 2014-09-22 degraded, 2014-09-23 degraded, 2014-09-24 degraded, 2014-09-25 degraded, 2017-11-13 degraded, 2018-10-21 degraded, 2019-01-15 degraded, 2019-02-22 degraded, 2019-03-13 degraded, 2019-03-26 degraded, 2020-02-27 degraded, 2020-02-28 degraded, 2020-05-05 degraded, 2020-06-30 degraded, 2020-07-01 degraded, 2021-12-05 degraded, 2022-01-02 degraded, 2024-09-18 degraded.

## 0. Purchase

- Streamed files expected 20, in manifest 20; missing: none
- Batch jobs 1 (GLBX-20261003-5BNS8Q9CPN is_bbo_1m from 2013-01-01); batch files in manifest 142
- SHA-256 matches on disk: 162 of 162; quoted cost $80.28; 0.81 GB compressed

## 1. Settlement coverage

- XNYS sessions 3605; with an ES final settle 3601; with a ZN final settle 3603
- Gap-audit rows: 19
  - 2010-12-24: settle on non-XNYS day
  - 2011-04-22: settle on non-XNYS day
  - 2012-04-06: settle on non-XNYS day
  - 2012-10-29: settle on non-XNYS day
  - 2012-10-30: settle on non-XNYS day
  - 2013-03-29: settle on non-XNYS day
  - 2014-04-18: settle on non-XNYS day
  - 2014-06-12: missing ES
  - 2014-09-23: missing ES
  - 2014-09-24: missing ES
  - 2014-09-25: missing ES
  - 2015-04-03: settle on non-XNYS day
  - 2015-07-03: settle on non-XNYS day
  - 2018-12-05: settle on non-XNYS day
  - 2020-02-27: missing ZN
  - 2020-06-30: missing ZN
  - 2021-04-02: settle on non-XNYS day
  - 2023-04-07: settle on non-XNYS day
  - 2023-07-15: settle on non-XNYS day
- ES settlements without a FINAL-flag record (last record used, A14): 5859 of 26682; by year {2010: 743, 2011: 1070, 2012: 1006, 2013: 1017, 2014: 1006, 2015: 912, 2016: 11, 2017: 2, 2018: 2, 2019: 18, 2020: 28, 2021: 9, 2022: 28, 2023: 4, 2024: 3}
- ZN settlements without a FINAL-flag record (last record used, A14): 5753 of 13694; by year {2010: 743, 2011: 1069, 2012: 1005, 2013: 1009, 2014: 1009, 2015: 861, 2016: 7, 2017: 4, 2018: 4, 2019: 4, 2020: 8, 2021: 7, 2022: 14, 2023: 4, 2024: 5}
- Last settlement date in the panels: ES 2024-10-01, ZN 2024-10-01 (2024-10-01 is the Sep-2024 exit)
- Statistics records with trade date >= 2024-10-02 in the raw file (A10 tail), by stat_type: none; rows in the panels: 0

## 2. Calendar, decision dates and events

- Qualifying sessions (ES and ZN final settle, XNYS open): 3599
- Months whose ex-ante dates differ from ex-post (A1): 5
  - 2012-10: event shift True (ex-ante L-5 2012-10-24), pseudo shift True
  - 2014-06: event shift False (ex-ante L-5 2014-06-23), pseudo shift True
  - 2014-09: event shift True (ex-ante L-5 2014-09-23), pseudo shift True
  - 2020-02: event shift True (ex-ante L-5 2020-02-21), pseudo shift True
  - 2020-06: event shift True (ex-ante L-5 2020-06-23), pseudo shift True
- events in IS: 171; usable (valid, tradable, data complete): 170; usable and PX-eligible: 159
  - 2014-09: event_valid False
- pseudos in IS: 171; usable (valid, tradable, data complete): 171
- Usable IS events whose window (anchor..exit) touches a Databento-degraded day: 7: ['2018-10 (2018-10-21)', '2019-02 (2019-02-22)', '2019-03 (2019-03-26)', '2020-02 (2020-02-27, 2020-02-28)', '2020-06 (2020-06-30, 2020-07-01)', '2021-12 (2022-01-02)', '2024-09 (2024-09-18)']
- Usable IS pseudos whose window (anchor..exit) touches a Databento-degraded day: 6: ['2014-06 (2014-06-11, 2014-06-12, 2014-06-13, 2014-06-15)', '2017-11 (2017-11-13)', '2019-01 (2019-01-15)', '2019-03 (2019-03-13)', '2020-05 (2020-05-05)', '2024-09 (2024-09-18)']

## 3. Reference series

- Missing daily reference returns (after the first session): ES 0, ZN 0
- Contract switches: ES 58, ZN 57; years with other than 4 per leg (2010 and 2024 are partial): {2010: {'ES': 3, 'ZN': 2}, 2024: {'ES': 3, 'ZN': 3}}

## 3b. Contract selection without open interest (A14)

- ES: share of panel rows ranked by traded volume, by year: {2010: 1.0, 2011: 1.0, 2012: 1.0, 2013: 1.0, 2014: 1.0, 2015: 0.885, 2018: 0.004, 2023: 0.0}
- ZN: share of panel rows ranked by traded volume, by year: {2010: 1.0, 2011: 1.0, 2012: 1.0, 2013: 1.0, 2014: 1.0, 2015: 0.909, 2018: 0.004}
- ES reference contract, 2015-11-19 to 2024-10-01: volume ranking agrees with open interest on 2202/2226 sessions (98.9%)
- ZN reference contract, 2015-11-19 to 2024-10-01: volume ranking agrees with open interest on 2182/2226 sessions (98.0%)
- ES event contract at L-8: volume ranking agrees with open interest on 106/106 events

## 4. Minute data (outrights requested by exchange symbol, 14:00-16:30 ET extract)

- Outrights alive in IS per definitions: 141 (ES 79, ZN 62); held or reference contracts: 117
- bbo-1m: ids not in the outright definitions 0; outrights with no 14:00-16:30 record 15; of them held or reference: []
  - records per year 7,264-1,750,989; stamped on a minute boundary 100.0%
- ohlcv-1m: ids not in the outright definitions 0; outrights with no 14:00-16:30 record 19; of them held or reference: []
  - records per year 464,495-923,048; stamped on a minute boundary 100.0%
- Symbols reused across decades: 61; their held/reference contracts present in both files: 98/98

## 5. Quotes at the 15:59 ET fill minute

Front = reference contract of the session (A8). Regular sessions only (early closes have no 15:59 minute, A2).

| Year | Regular sessions | ES fresh | ZN fresh | ES median spread (ticks) | ZN median spread (ticks) |
|---|---|---|---|---|---|
| 2010 | 144 | 144 | 143 | 1.0 | 1.0 |
| 2011 | 251 | 251 | 251 | 1.0 | 1.0 |
| 2012 | 247 | 247 | 247 | 1.0 | 1.0 |
| 2013 | 249 | 249 | 249 | 1.0 | 1.0 |
| 2014 | 245 | 243 | 244 | 1.0 | 1.0 |
| 2015 | 250 | 250 | 250 | 1.0 | 1.0 |
| 2016 | 251 | 251 | 251 | 1.0 | 1.0 |
| 2017 | 249 | 249 | 249 | 1.0 | 1.0 |
| 2018 | 248 | 248 | 248 | 1.0 | 1.0 |
| 2019 | 249 | 249 | 249 | 1.0 | 1.0 |
| 2020 | 249 | 249 | 249 | 1.0 | 1.0 |
| 2021 | 251 | 251 | 251 | 1.0 | 1.0 |
| 2022 | 250 | 250 | 250 | 1.0 | 1.0 |
| 2023 | 248 | 248 | 248 | 1.0 | 1.0 |
| 2024 | 188 | 188 | 188 | 1.0 | 1.0 |

Held contracts on PX fill days: 159 usable PX-eligible IS events x 2 legs x (entry L-4, exit F1).

- Fills without a fresh quote: 0
- ES: spread median 1.0, 95th pct 1.0, max 2.0 ticks; 15:59 bar volume median 40,874, 10th pct 25,159, min 14,242 contracts
- ZN: spread median 1.0, 95th pct 1.0, max 2.0 ticks; 15:59 bar volume median 1,190, 10th pct 94, min 0 contracts

