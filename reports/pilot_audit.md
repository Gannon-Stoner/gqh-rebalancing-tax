# Pilot data audit (2020-10-01 to 2021-01-29)

Data quality only: no strategy returns were computed. Prices appear only as tick distances.

## 1. Session coverage

- XNYS sessions in window: 83
- Dates with an ES final settlement: 83; ZN: 83
- Gap-audit rows (missing settle on an XNYS session, or settle on a non-XNYS day): 0

## 2. Settlement records

- Settlement records: 5670; with FINAL flag: 2520; flag values: {1: 14, 2: 2299, 3: 1980, 5: 6, 6: 851, 7: 520}
- ES: front contract has a final settle on 83/83 dates; final published median 19:13 ET (latest 20:19); 79% published on the trade date itself (rest after midnight ET)
- ZN: front contract has a final settle on 83/83 dates; final published median 19:13 ET (latest 20:20); 78% published on the trade date itself (rest after midnight ET)

## 3. Settlement clock check

- bbo-1m records stamped exactly on a minute boundary: 100.0% (ts_recv = interval end)

| Root | Period | Candidate mark (ET) | Median |settle - mid| (ticks) | Dates |
|---|---|---|---|---|
| ES | before 2020-10-26 | 15:59 | 11.50 | 17 |
| ES | before 2020-10-26 | 16:00 | 10.50 | 17 |
| ES | before 2020-10-26 | 16:14 | 4.50 | 17 |
| ES | before 2020-10-26 | 16:15 | 1.50 | 17 |
| ES | from 2020-10-26 | 15:59 | 5.50 | 64 |
| ES | from 2020-10-26 | 16:00 | 3.50 | 64 |
| ES | from 2020-10-26 | 16:14 | 12.00 | 64 |
| ES | from 2020-10-26 | 16:15 | 11.25 | 64 |
| ZN | before 2020-10-26 | 14:59 | 0.50 | 17 |
| ZN | before 2020-10-26 | 15:00 | 0.50 | 17 |
| ZN | before 2020-10-26 | 16:00 | 0.50 | 17 |
| ZN | from 2020-10-26 | 14:59 | 0.50 | 64 |
| ZN | from 2020-10-26 | 15:00 | 0.50 | 64 |
| ZN | from 2020-10-26 | 16:00 | 1.50 | 64 |

## 4. Quotes at the 15:59 ET fill minute (front contract)

| Root | Dates with a fresh quote (<= 5 min) | Median staleness (min) | Median spread (ticks) | 95th pct spread (ticks) |
|---|---|---|---|---|
| ES | 81/83 | 0.0 | 1.00 | 1.00 |
| ZN | 81/83 | 0.0 | 1.00 | 1.00 |

## 5. Minute volume in settlement windows (front contract)

- ohlcv-1m bars stamped on a minute boundary: 100.0% (stamp = bar start)

| Root | Bar (ET, start) | Median contracts | 10th pct |
|---|---|---|---|
| ES | 15:59 | 41,562 | 28,241 |
| ZN | 14:59 | 13,159 | 5,731 |
| ZN | 15:59 | 2,051 | 487 |

## 6. Rolls and contract selection

Reference-series contract switches (previous-session highest OI):
- 2020-12-15 ES: ESZ0 -> ESH1
- 2020-11-25 ZN: ZNZ0 -> ZNH1

ZN first position days (derived): ZNZ0 2020-11-27, ZNH1 2021-02-25, ZNM1 2021-05-27, ZNU1 2021-08-30

| Event month | L-8 | F1 | ES held | ZN held | Tradable | Data complete |
|---|---|---|---|---|---|---|
| 2020-11 | 2020-11-17 | 2020-12-01 | ESZ0 | ZNH1 | True | True |
| 2020-12 | 2020-12-18 | 2021-01-04 | ESH1 | ZNH1 | True | True |
