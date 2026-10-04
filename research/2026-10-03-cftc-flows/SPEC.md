# CFTC positioning test of month-end rebalancing flows — fixed specification

Status: written 2026-10-04 before any CFTC position value was downloaded or inspected. Only column names and
contract codes were looked up. `run.py` refuses to run unless this file's hash matches `spec_lock.json`.

## 1. Question

Do institutions' futures positions actually move the way 60/40 rebalancing predicts at month-end? This tests the
**flow** (quantities) behind the HMM mechanism, not returns. The return-based results (original H1/H2, phase
validation, HMM replication) are unchanged.

Prediction: when stocks have outperformed bonds month to date (Calendar drift D > 0, equities overweight),
rebalancers **sell ES and buy ZN** around month-end. The reverse holds when D < 0.

## 2. Data

- CFTC Traders in Financial Futures, futures only (Socrata dataset `gpe5-46if`), public.
  - ES: contract code `13874A` (E-mini S&P 500, CME; the market name changed over time, the code did not).
  - ZN: contract code `043602` (10-year T-note, CBOT).
- Positions are as of each report's Tuesday close (`report_date_as_yyyy_mm_dd`).
- Sample: report dates from 2010-06-08 to 2024-10-01 inclusive, matching the IS settlement data. Later reports
  are not used: they are in the OOS period.
- Signal: the Calendar drift series from `research/2026-10-03-hmm-replication` (`daily_panel.csv`; HMM
  Appendix B), using ES/ZN within-contract settlement returns.

## 3. Variables

- Net position of category k: N_k = long_k − short_k. Spread positions are excluded because they are net zero.
- **Month-end window m**: from the last report date strictly before session L−4 to the first report date on or
  after L (L = the month's last qualifying session). This covers HMM's last-week window and the rebalance close.
  It spans one or two report intervals.
- **Outcome**: y_k,m = (N_k at window end − N_k at window start) / open interest at window start.
- **Drift**: D_m = the Calendar signal at L (the weight deviation the calendar rebalancer must trade; known only
  at L). This is a flow test, not a trading rule, so using D at L is appropriate.
- **Mid-month placebo window**: from the last report date strictly before L−14 to the first report date on or
  after L−10, using the Calendar signal (month-to-date drift) at L−10.

## 4. Confirmatory tests (Holm over two, one-sided, α = 0.05; HC1 standard errors)

y_k,m = a + b·D_m + e, one observation per month, asset managers (k = asset_mgr):

- **F1 (ES)**: b < 0. Asset managers sell ES when equities are overweight.
- **F2 (ZN)**: b > 0. Asset managers buy ZN when equities are overweight.

Power is unknown in advance: there is no prior estimate in contract units. With about 170 months, the minimum
detectable t-statistic at 80% power is about 2.5.

## 5. Secondary (pre-declared, no pass/fail)

1. The same regression for dealers, leveraged funds, other reportables and non-reportables, for both contracts.
   Expected sign is unknown. Liquidity providers or front-runners may trade the other way.
2. Mid-month placebo window: the same regressions. Prediction: |b| is smaller than at month-end.
3. Pooled difference: stack the month-end and placebo windows, with y = a + a_ME·ME + b·D + b_ME·ME·D. Report
   b_ME.
4. Quarter-end interaction: add QE·D (March, June, September, December).
5. Dollar scale: implied rebalanced assets V = −Δ(ES net notional)/D. Report the median of ES notional per contract
   (50 × the ES settlement price) times the coefficient times open interest, as an order of magnitude only.
6. Subperiods: 2010-06 → 2015-09, 2015-10 → 2024-09.
7. Quarterly ES roll months: a dummy for windows that overlap the ES roll week (the 7 sessions before the third
   Friday of March, June, September and December) as a control.

## 6. Caveats, stated now

- Weekly Tuesday snapshots blur timing. Most rebalancing may be in cash securities, swaps or other contracts
  (MES, TY options, Ultra 10s), and CFTC category labels are self-reported. A null therefore only bounds ES/ZN
  futures overlay flow; it does not refute rebalancing.
- Asset-manager futures positions also reflect index-fund cash equitization, which responds to fund flows rather
  than drift.
