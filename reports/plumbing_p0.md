# Masked plumbing run: P0, in-sample (no returns, no gate decisions)

## events

- IS rows 171; valid 168; traded 160; not traded: {'below_one_lot': 8, 'invalid': 3}
- Invalid because: not tradable 0, data incomplete 0, signal undefined (e.g. sigma warm-up) 3
- Min / median / 95th pct / max over traded events:
  - ES contracts 1 / 14 / 46 / 69; ZN contracts 1 / 14 / 38 / 57
  - leg notional / NAV 0.01 / 0.17 / 0.45 / 0.69; gross / NAV 0.02 / 0.34 / 0.91 / 1.39 (caps 0.75 per leg, 1.50 gross); cap bound on 0 events
  - round-trip cost $38 / $543 / $1,522 / $2,033 = 0.04 / 0.54 / 1.52 / 2.03 bp of NAV
  - cost hurdle C (risk units) 0.0023 / 0.0157 / 0.0249 / 0.0344
- Traded events per year: {2010: 4, 2011: 10, 2012: 12, 2013: 11, 2014: 10, 2015: 12, 2016: 10, 2017: 12, 2018: 12, 2019: 12, 2020: 12, 2021: 12, 2022: 12, 2023: 12, 2024: 7}
- P&L digest (sha256 of the event-return column, values not shown): bfc651b68266d8c1

## pseudos

- IS rows 171; valid 169; traded 166; not traded: {'below_one_lot': 3, 'invalid': 2}
- Invalid because: not tradable 0, data incomplete 0, signal undefined (e.g. sigma warm-up) 2
- Min / median / 95th pct / max over traded events:
  - ES contracts 1 / 11 / 46 / 57; ZN contracts 1 / 11 / 31 / 60
  - leg notional / NAV 0.01 / 0.15 / 0.38 / 0.75; gross / NAV 0.03 / 0.29 / 0.75 / 1.48 (caps 0.75 per leg, 1.50 gross); cap bound on 1 events
  - round-trip cost $38 / $434 / $1,481 / $2,182 = 0.04 / 0.43 / 1.48 / 2.18 bp of NAV
  - cost hurdle C (risk units) 0.0026 / 0.0150 / 0.0274 / 0.0360
- Traded events per year: {2010: 4, 2011: 12, 2012: 11, 2013: 12, 2014: 12, 2015: 12, 2016: 12, 2017: 12, 2018: 12, 2019: 10, 2020: 12, 2021: 12, 2022: 12, 2023: 12, 2024: 9}
- P&L digest (sha256 of the event-return column, values not shown): 8f43bb41f872d21e

