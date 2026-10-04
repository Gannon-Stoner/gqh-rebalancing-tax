# Paying for what is left: a pre-registered remaining-return gate on month-end 60/40 rebalancing flow in ES/ZN futures

## Summary

Balanced funds must sell the asset that outperformed during the month and buy the laggard, on a calendar. That flow is public, so the question for a trader is not *whether* it moves prices but **how much of the move is still left when we can trade**. We designed one rule to answer it, the gate (PG), and pre-registered it (git tag `prereg-final`, committed before any price data was loaded). At the L−5 settlement we forecast the remaining ES−ZN spread return from the size of the rebalancing need (dose) and how far the spread has already moved our way (progress). We trade at L−4 only if the forecast beats round-trip cost, and exit on the new month's first session. **Result.** In sample (2015-10 to 2024-09) the gate failed: PG's net Sharpe ratio was -0.05 against 0.13 for always trading, and neither confirmatory hypothesis survived (Holm p = 0.64 and 0.64). <!--OOS-->Out of sample (2024-10 to 2026-09) PG did better (0.91 vs 0.14), but on 16 trades, two of which carry the result, that does not overturn the in-sample failure.<!--/OOS-->

## 1. Economic hypothesis

**Mechanism.** A 60/40 fund whose stocks rise 10% while bonds are flat ends the month 62.3% in stocks and must sell $2.40 of stocks per $100 to rebalance. In general the stock-weight drift is D = 0.24(R_E − R_B)/(1 + 0.6R_E + 0.4R_B). This is accounting, not a forecast: it is the demand of a hypothetical fund; we observe no orders.

**Edge source: a structural constraint.** The flow comes from calendar rebalancers (pension plans, balanced and target-date funds) and their overlay managers, whose mandates fix weights at a clock, not at a price; at our fill the other side is liquidity suppliers and earlier anticipators. That this flow moves prices is documented [1–3], and sell-side desks estimate it monthly. It persists because of governance and scarce risk capital, not secrecy: committees set the rules, and harvesting it means about twelve noisy, crash-exposed bets a year. At always-trade's in-sample Sharpe, a t-statistic of 2 would take 2,677 months of data: no arbitrageur can prove it fast enough to compete it away.

**Our contribution.** Knowing that rebalancing moves prices does not tell a trader whether anything is left to capture once everyone can predict it. This strategy is built to answer that: it conditions the trade on how much of the expected move has already happened before entry, and tests whether that improves the trade after costs. Two forces should shrink what is left after early progress (anticipators already pushed the price; the move itself shrinks the drift funds must trade); two predict the opposite (news momentum, persistent orders). Ordinary short-term reversal could mimic the first pair, so the design includes a mid-month placebo. **What is new:** (i) pricing the *remaining* move after anticipation rather than the flow itself; (ii) a mid-month placebo (PP) that separates rebalancing from ordinary reversal; (iii) an exposure-matched control (PE) that separates a better gate from simply taking less risk; (iv) pre-registered, falsifiable kill conditions with every variant reported.

**Kill conditions (pre-registered).** IS dose slope b ≤ 0; c_E ≥ 0; the gate does not beat an exposure-matched control; net Sharpe ≤ 0 at 2× costs; or the binding leg cannot fill one lot at 1% of execution-window volume.

## 2. Data and universe

- **Source.** Databento GLBX.MDP3 [4], all outright quarterly ES and ZN contracts: `definition`, `statistics` (settlements, open interest, volume), `bbo-1m`, `ohlcv-1m`; Ken French daily factors [5]. IS 2010-06-07 to 2024-10-01; OOS from 2024-10-02 (the most recent two years, per the track rule), loaded once after the `freeze-final` tag<!--OOS--> (24 months, all 24 events usable)<!--/OOS-->. Raw licensed data is never committed; every file is logged with its SHA-256.
- **Sessions and contracts.** CME dates on which both legs settle and NYSE is open (171 IS months, 168 valid events, 169 pseudo-events). L is the month's last such session, F1 the next month's first. ES: highest open interest at L−8; ZN: nearest contract whose first position day is after F1. Daily settlements drive signals and P&L; 1-minute quotes and bars serve fills (PX) and capacity. One contract per leg per event, so no roll enters a return; futures have no survivorship bias and no splits or dividends to adjust. Months without a usable settlement (3 of 171 IS) are skipped; no price is ever filled from a later date. Pre-2015 vendor gaps (no "final" settlement flag, no open interest) use frozen fallback rules validated where both exist (App. 1).

## 3. Methodology (frozen before any backtest)

<figure><img src="reports/figures/timeline.png"><figcaption>Figure 1. One month. Pseudo-events use the same formulas twelve sessions earlier. Returns between decision (L−5) and fill (L−4) never count.</figcaption></figure>

- **Signal at L−5.** σ̂ is a zero-mean EWMA (λ = 0.94) of the daily spread return X = r_ES − r_ZN. Dose = min(|z|, 2), z = D/(0.24·σ̂·√n). Direction s = −sign(D), with the coming rebalancing. Progress A = s·X(L−8→L−5)/(σ̂√3); outcome Y = s·X(L−4→F1)/(σ̂√5).
- **Gate.** Ŷ = â + b̂·dose + ĉ·A by OLS on completed past events only (≥ 60), frozen at the end of IS for OOS. Trade iff Ŷ exceeds round-trip cost in risk units; otherwise flat; never reverse. At most one trade a month, flat between events.
- **Position and costs.** Equal-notional legs sized so a full-dose event risks 0.87% of NAV over five days; caps 0.75×NAV per leg, 1.5× gross; whole contracts at a $10M reference NAV. Entry at the L−4 settlement, exit at F1. Per contract per side: half a tick (ES $6.25, ZN $7.81) + $2.50 fee, about 0.3–0.9 bp of notional over 2015–24; every row is also run at 2×.
- **Six rows, all reported (N = 6).** **PG** gate · **P0** always trade · **PD** dose-only gate (does progress add anything?) · **PE** P0 scaled to PG's participation (is the gain just less risk?) · **PX** PG filled at the 15:59 ET bid/ask · **PP** PG on mid-month pseudo-events (ordinary reversal?). One walk-forward segment, 2015-10 to 2024-09.
- **Confirmatory tests (Holm, one-sided, α = 0.05).** H1: b > 0 in Y = a + b·dose + γ·QE (QE: quarter-end month). H2: c_E < 0 in the stacked event/pseudo-event regression: progress matters more at month-end than mid-month. Studentized month-block bootstrap, size 3.8%–6.4% at nominal 5% on synthetic GARCH histories run through the real code; power is low and stated up front (App. 2). PG and P0 also run end to end in the Webull starter kit's Backtrader harness: all 85 PG and 127 P0 event P&Ls match to $0.01, and every reported return, Sharpe and drawdown is reproduced exactly (amendment A21).

## 4. Results (net of costs, % of a $10M reference NAV)

### In sample (2015-10 to 2024-09, walk-forward segment)

| Row | Trades | Ret/yr | Vol/yr | SR 1× | SR 2× | Max DD | Worst mo. | Turn./yr | DSR |
|---|---|---|---|---|---|---|---|---|---|
| PG | 69 | -0.04% | 0.87% | -0.05 | -0.08 | 2.55% | -1.17% | 4.4× | 0.08 |
| P0 | 104 | 0.20% | 1.52% | 0.13 | 0.09 | 2.23% | -1.17% | 9.1× | 0.18 |
| PD | 82 | -0.13% | 1.08% | -0.12 | -0.16 | 3.01% | -1.17% | 5.4× | 0.05 |
| PE | 103 | 0.14% | 1.00% | 0.14 | 0.09 | 1.48% | -0.77% | 6.1× | 0.18 |
| PX | 64 | 0.05% | 0.85% | 0.06 | 0.02 | 1.88% | -1.14% | 4.0× | 0.13 |
| PP | 12 | -0.13% | 0.34% | -0.40 | -0.41 | 1.50% | -0.86% | 0.6× | 0.00 |

Monthly returns (zero in flat months), annualized, uncompounded on fixed NAV. DSR: deflated Sharpe ratio at N = 6 [6] (lower at the logged prior-look counts, App. 2).

**Does the gate help? No.** ΔSR (90% month-block CI): PG − P0 -0.18 [-0.62, +0.30]; PG − PD +0.07 [-0.36, +0.49]; PG − PE -0.18 [-0.62, +0.29]. PG trades 66% of P0's events yet trails both P0 and the exposure-matched PE: the gate removed good trades with the bad. **Neither confirmatory hypothesis survives.** H1: b̂ = -0.010 σ per unit dose, 90% CI [-0.189, +0.179], Holm p = 0.638; the need's size did not predict the remaining return at a tradable lag. H2: ĉ_E = -0.062 [-0.279, +0.156], Holm p = 0.638: right sign, small, and with 58% power at c_E = −0.27 a null was likely, so we read it as an upper bound. Wild-bootstrap and Newey-West p-values agree (App. 2). PG's monthly skew is +0.14 and it wins 43% of trades, so the Sharpe hides no short-volatility tail. The pressure itself has faded: the signed spread path rises over the holding window in 2010–20 but is flat in 2021–24 (App. 3).

<div class="row">
<figure><img src="reports/figures/key_y_vs_a.png"><figcaption>Figure 2. Remaining return vs pre-entry progress, month-end events vs mid-month pseudo-events (IS).</figcaption></figure>
<figure><img src="reports/figures/equity_is.png"><figcaption>Figure 3. Cumulative net return of the six rows, 1× costs (IS).</figcaption></figure>
</div>

<!--OOS-->
### Out of sample (2024-10 to 2026-09, opened once after `freeze-final`)

| Row | Trades | Ret/yr | Vol/yr | SR 1× | SR 2× | Max DD | Worst mo. | Turn./yr | DSR |
|---|---|---|---|---|---|---|---|---|---|
| PG | 16 | 1.00% | 1.11% | 0.91 | 0.88 | 0.35% | -0.35% | 5.6× | 0.49 |
| P0 | 23 | 0.18% | 1.34% | 0.14 | 0.10 | 1.30% | -0.62% | 8.9× | 0.13 |
| PD | 23 | 0.18% | 1.34% | 0.14 | 0.10 | 1.30% | -0.62% | 8.9× | 0.13 |
| PE | 23 | 0.18% | 0.90% | 0.20 | 0.16 | 0.87% | -0.41% | 6.0× | 0.15 |
| PX | 14 | 0.90% | 1.11% | 0.81 | 0.78 | 0.37% | -0.37% | 5.2× | 0.42 |
| PP | 0 | 0.00% | 0.00% | n/a | n/a | 0.00% | 0.00% | 0.0× | n/a |

PD equals P0 and PP never trades by construction of the frozen IS coefficients, not by error: PD's forecast is almost constant (0.032 + 0.002·dose) and always clears cost; PP's (-0.039 -0.057·dose -0.002·A) stayed below cost on every OOS pseudo-event.

**Better out of sample, but 24 months cannot carry the claim.** PG − P0 ΔSR +0.77 [+0.09, +1.69]; vs the exposure-matched PE +0.70 [+0.02, +1.59]. It survives real quotes (PX 0.81), and the frozen-model slopes have the predicted signs (b = +0.26, c_E = -0.31), but neither slope nor its change from IS excludes zero (App. 4). Skew is +2.29: the result is a few large wins. Two events (2025-07: +113,622 USD; 2025-11: +90,965 USD) earned more than PG's whole OOS net (+200,726 USD); DSR is 0.49, and a t-statistic of 2 at this Sharpe would take 58 months. Three pre-registered kill conditions were met in sample; a short positive OOS does not undo them. We report it as unconfirmed and worth paper-monitoring, not as evidence the gate works.

<div class="row">
<figure><img src="reports/figures/equity_oos.png"><figcaption>Figure 4. Cumulative net return of the six rows, 1× costs (OOS).</figcaption></figure>
<figure><img src="reports/figures/pg_oos_events.png"><figcaption>Figure 5. PG net P&amp;L per OOS event (grey: flat). Two events carry the result.</figcaption></figure>
</div>
<!--/OOS-->

## 5. Risk management

Rules were fixed before the backtest and apply to every row. Size scales with dose; a full-dose event targets five-day risk of 0.87% of NAV; legs capped at 0.75×NAV, gross at 1.5×; size is set at entry and never cut mid-event. We disclose that choice rather than add a stop: a 2σ intra-event stop, run as a stress row, would have stopped 2 PG events and moved IS net P&L from -36,979 to -45,029 USD. **Both legs can lose at once:** long ES / short ZN loses twice when stocks fall and bonds rally, and the 2022 positive stock-bond correlation removed the usual hedge; stress-period P&L by leg is in App. 5. **Exposures:** regressing event returns on Mkt-RF, SMB, HML, Mom and ZN gives alpha -0.0002 per event (t = -0.44), market t = 0.35, R² 0.03: no hidden beta, and no alpha. **Tail and capital:** bootstrap P(−7.5% drawdown in 36 months) is 0.0%; margin-to-equity at CME maintenance margins is 2.0% at the median event (8.7% max); the worst one-day variation-margin draw was -0.52% of NAV. **Largest plausible single-position loss:** the ES leg is 11% of NAV at the median trade and 44% at the largest, so a 1987-size −20% day would cost about 2.3% and 8.7% of NAV; the worst realized event lost -116,628 USD. The binding risk is a lack of edge, not a drawdown. **Governance:** pause if 24-event net P&L falls below −2σ of its forecast or OOS slopes signal decay; resume only after documented review; never change parameters after a loss.

## 6. Liquidity and capital

**Execution.** Settlement rows fill at the official settlement marks (ZN 14:59–15:00 ET; ES 15:59:30–16:00 ET). PX instead buys at the 15:59 ET ask and sells at the bid from `bbo-1m`, paying the spread in the fill; IS PX Sharpe is 0.06 vs PG's -0.05. **Capacity (scenario, not a forecast).** ZN is the binding leg in 72% of events (median execution-minute volume ES 10,377, ZN 5,959 contracts). Maximum NAV at 1% / 5% / 10% participation: $43,700,000 / $218,500,000 / $437,000,000 at the median event, $8,236,120 at the 10th percentile at 1%. One lot fits within 1% in 93% of events. **Where the edge erodes.** Costs are not what decides this trade: at $10M they take 2% of gross P&L, and adding square-root market impact to those costs moves IS net Sharpe from -0.05 (table) to -0.06 at $10M, -0.08 at $100M and -0.15 at $1B (App. 6). Capacity is set by participation limits, not by cost. Costs doubled are in every table.

## 7. Limitations and next steps

- **Power.** About 170 events give H1 at most ~20% power across the predicted range and H2 58% at c_E = −0.27; nulls are upper bounds, not proof of absence.
- **Every look, counted.** Before pre-registration: a private 2010–22 event study on proxy data and at least 29 month-end and 45 trend/vol variants (DSR at those counts in App. 2). A masked crash-test run revealed PG's IS trade count and two Sharpe signs before the freeze (amendment A16); nothing was changed. After the IS result, and never touching post-2024-10-01 data: 57 exploratory return series diagnosing the failure, a replication of [1] (threshold signal replicated, Holm p = 0.027; calendar signal not), a CFTC positioning test (not confirmed), and an 11-trial multi-signal futures program with no holdout yet. None of these changed the registered strategy or its results.
- **Data and clocks.** Pre-2015 settlements rely on documented vendor fallbacks (App. 1); ES and bond benchmark clocks moved in 2020–21.<!--OOS--> Seven OOS days lack a final-flag settlement, one being the exit of the largest OOS winner; its 15:59 quotes and minute bars agree with the price used (amendment A20).<!--/OOS-->
- **No causal identification.** We forecast returns from prices; we do not observe who traded.
- **Next.** Depth on the side the flow needs, execution timing within the window, and the interaction with volatility-targeting deleveraging.

<div class="endbody"></div>

## References

1. Harvey, C. R., Mazzoleni, M., and Melone, A. (2025). *The Unintended Consequences of Rebalancing.* NBER Working Paper w33554.
2. Brøgger, A. (2021). *The Market Impact of Predictable Flows: Evidence from Leveraged VIX Products.* Working paper.
3. Bessembinder, H., Carrion, A., Tuttle, L., and Venkataraman, K. (2016). Liquidity, resiliency and market quality around predictable trades: Theory and evidence. *Journal of Financial Economics* 121(1), 142–166.
4. Databento. CME Globex MDP 3.0 (GLBX.MDP3): `definition`, `statistics`, `bbo-1m`, `ohlcv-1m` schemas. databento.com.
5. French, K. R. Data Library: Fama/French 3 factors (daily) and Momentum factor (daily). mba.tuck.dartmouth.edu/pages/faculty/ken.french.
6. Bailey, D. H., and López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management* 40(5), 94–107.
7. Backtrader (v1.9.78), backtrader.com; exchange_calendars; CME Group performance-bond (margin) requirements, retrieved 2026-10-03.

## Appendix (optional reading; not needed for the main argument)

**App. 1. Vendor data facts (amendment A14).** Before CME's MDP 3.0 feed (2010–2015) the vendor's settlement records carry no "final" flag and open interest is not published. Settlements use the frozen "last record per contract and day" rule, which matches the flagged final on 99.75–100% of contract-days where both exist. Where open interest is missing, contracts are ranked by volume, which picks the same contract on 98–99% of days and 106/106 event dates where both exist. Decision dates are recomputed on the calendar a trader knew at the time (Hurricane Sandy; four vendor-degraded months).

**App. 2. Inference.** Studentized circular month-block bootstrap (block 3, 9,999 draws, seed 20261003). On 500 synthetic AR(1)-GARCH(1,1)-t₅ histories per null run through the real signal code, size is 3.8%–6.4% at nominal 5% (registered band 3–7%). H1 rejects 11% of the time at b = 0.05 and 20% at b = 0.12; H2 rejects 58% at c_E = −0.27 (80%-power MDE ≈ 0.37). Ordinary reversal alone makes H1 reject 12.6% of the time, which is why H2 and PP exist. Confirmatory p-values, one-sided: H1 0.523 (wild 0.522, Newey-West(3) 0.536); H2 0.319 (0.317, 0.315). PG's DSR at the logged prior-look counts (35 and 80) is 0.01 and 0.00. PE trades every P0 event at p = 0.66 of the size. Backtrader replay at 2× costs: 85/85 PG, 127/127 P0.

**App. 3. Diagnostics (IS).** With sign and dose frozen at L−12, the dose-weighted cumulative spread path rises from +0.05 σ at L−4 to +0.49 σ at L in 2010–15 and from -0.68 to +0.09 σ in 2016–20; in 2021–24 it is flat (+0.11, +0.09). P0's small positive result is not alpha: the 32 events that buy ES after stocks lagged netted +394,194 USD, the 72 that sell ES -210,669 USD. P0's factor-adjusted alpha is -0.00006 per event (t = -0.13); it loads on ZN (t = 2.03). After 2021-01-14, ZN's 15:00→16:00 ET return on L is +1.6 bp signed toward the flow vs +0.6 bp on other days. PG's ZN loading is -0.010 (t = -0.13), market +0.013. P0's bootstrap drawdown probability is 0.0%; at P0's IS Sharpe a t-statistic of 2 would need 2,677 months. Realized-to-target risk lies in [0.6, 1.5] in 70% of years.

<!--OOS-->
**App. 4. OOS slopes, frozen model.** b_OOS = +0.262 (Δb = +0.271, 90% CI [-0.300, +1.314]); c_E,OOS = -0.311 (Δc = -0.249, [-0.816, +0.327]).
<!--/OOS-->

**App. 5. Stress periods** (P0 on every valid IS event; event P&L by leg, % of NAV). Spread variance is h_E²σ_E² + h_B²σ_B² − 2h_E h_B Cov(r_E, r_B).

| Period | Events | ES leg | ZN leg | Costs | Net |
|---|---|---|---|---|---|
| 2011-08 | 1 | +0.28% | -0.03% | 0.00% | +0.25% |
| 2015-08 | 1 | +0.43% | +0.03% | 0.01% | +0.45% |
| 2018-02 | 1 | -0.10% | -0.05% | 0.00% | -0.15% |
| 2020-03 | 1 | -0.03% | -0.03% | 0.00% | -0.06% |
| 2022 | 12 | +1.11% | -0.15% | 0.03% | +0.92% |
| 2023-03 | 1 | +0.29% | -0.03% | 0.00% | +0.26% |

**App. 6. Event path and impact.** Margins used (CME, 2026-10-03): ES $26,164, ZN $1,875 per contract. ES settled 16:14:30–16:15 ET before 2020-10-26.

<div class="row">
<figure><img src="reports/figures/event_path.png"><figcaption>Figure A1. Signed spread path, L−12 to F1+5, by era (sign and dose frozen at L−12).</figcaption></figure>
<figure><img src="reports/figures/impact.png"><figcaption>Figure A2. PG net Sharpe vs NAV under square-root impact.</figcaption></figure>
</div>

Full audit (data coverage, decision-date shifts, action ledger, Backtrader reconciliation, inference calibration) and every amendment: `AMENDMENTS.md`, `reports/`.
