# Paying for what is left: a pre-registered remaining-return gate on month-end 60/40 rebalancing flow in ES/ZN futures

## Summary

Calendar-based 60/40 rebalancing sells the outperforming asset and buys the laggard. We test how much return remains after earlier price adjustment, using a pre-registered gate (PG; git tag `prereg-final`). At the \(L{-}5\) settlement, PG forecasts the remaining ES–ZN spread return from the rebalancing need (*dose*) and prior signed price movement (*progress*). It enters at \(L{-}4\) only when the forecast exceeds round-trip cost, and exits at the first session of the new month.

In sample (2015-10 to 2024-09) the gate failed: PG's net Sharpe ratio was −0.05 against 0.13 for always trading, and neither confirmatory hypothesis survived (Holm-adjusted \(p = 0.64\) and \(0.64\)). Post-hoc analysis distinguishes poor gate selection from the baseline trade's first-session giveback (Section 4). <!--OOS-->Out of sample (2024-10 to 2026-09) PG did better (0.91 vs 0.14), but on 16 trades, two of which carry the result, this does not overturn the in-sample failure.<!--/OOS-->

## 1. Economic hypothesis

*Mechanism.* A 60/40 fund whose stocks rise 10% while bonds are flat ends the month 62.3% in stocks and must sell \$2.40 of stocks per \$100 to rebalance. In general the drift in the stock weight is
\[ D = \frac{0.24\,(R_E - R_B)}{1 + 0.6\,R_E + 0.4\,R_B}, \]
where \(R_E\) and \(R_B\) are the month-to-date equity and bond returns. This is accounting, not a forecast: it is the demand of a hypothetical fund, and we observe no orders.

*Edge source: a structural constraint.* Calendar rebalancers and their overlay managers target portfolio weights on scheduled dates. Potential counterparties at entry include liquidity suppliers and earlier anticipators; we do not identify them directly. Rebalancing pressure is documented in [1], but predictable flow need not yield profits after costs [2–3]. Governance constraints and limited risk capital motivate the hypothesis; they do not establish a persistent tradable edge.

*Our contribution.* We test whether prior price adjustment helps predict the remaining return after costs. Anticipation and reduced portfolio drift predict less remaining return; news momentum and persistent orders predict more. Our extension combines four design elements: (i) a gate on the *remaining* move; (ii) a mid-month placebo (PP) to test against ordinary reversal; (iii) an exposure-matched control (PE) to distinguish selection from taking less risk; and (iv) pre-registered kill conditions, with every registered variant reported. The contribution is this joint test in month-end rebalancing, not the invention of these methods.

*Kill conditions (pre-registered).* An in-sample dose slope \(b \le 0\); a progress interaction \(c_E \ge 0\); no gain over the exposure-matched control; a net Sharpe ratio \(\le 0\) at twice the assumed costs; or a binding leg that cannot fill one contract within 1% of execution-window volume.

## 2. Data and universe

*Sources and samples.* Databento GLBX.MDP3 [4] supplies outright quarterly ES/ZN definitions, settlements, open interest, volume and minute quotes/bars; French supplies daily factors [5]. IS runs from 2010-06-07 to 2024-10-01. OOS starts 2024-10-02, covering two years under the track rule, and was evaluated after `freeze-final`<!--OOS--> (24 usable months)<!--/OOS-->. Published extensions had partly exposed Oct-2024–Dec-2025 before registration; this is a frozen-rule evaluation, not a wholly untouched holdout.

*Sessions and contracts.* A session is a CME date on which both legs settle and NYSE is open (171 IS months, 168 valid events, 169 pseudo-events). \(L\) is the last such session of a month and \(F_1\) the first of the next. The ES contract is the one with the highest open interest at \(L{-}8\); the ZN contract is the nearest one whose first position day falls after \(F_1\). Settlements drive signals and P&L; minute data support PX fills and capacity. Each leg holds one expiry in variable whole-contract quantities, without rolling during an event. The full futures universe needs no equity split/dividend adjustment. Two initial months lack the volatility warm-up; Sep-2014 lacks a decision-day settlement. These three events are excluded; prices are never filled from later dates. Pre-2015 final flags and open interest are missing; validated frozen fallbacks apply (App. 1).

## 3. Frozen strategy and methodology

| Schedule | Progress | Decision | Entry | Exit |
|---|---|---|---|---|
| Month-end | \(L-8\) to \(L-5\) | \(L-5\) | \(L-4\) | \(F_1\) |
| Pseudo-event | \(L-17\) to \(L-14\) | \(L-14\) | \(L-13\) | \(L-8\) |

Figure 1. Event schedule. Pseudo-events occur nine sessions earlier. Decision-to-entry returns never enter holding-period P&L.

*Signal at \(L{-}5\).* Let \(X = r_{ES} - r_{ZN}\) be the daily spread return and \(\hat\sigma\) its zero-mean EWMA volatility (\(\lambda = 0.94\)). With \(n\) sessions since the previous \(L\),
\[ z = \frac{D}{0.24\,\hat\sigma\sqrt{n}}, \qquad \text{dose} = \min(|z|, 2), \qquad s = -\operatorname{sign}(D), \]
so the trade goes with the coming rebalancing. Progress and the outcome are
\[ A = \frac{s\,X_{L-8 \to L-5}}{\hat\sigma\sqrt{3}}, \qquad Y = \frac{s\,X_{L-4 \to F_1}}{\hat\sigma\sqrt{5}}. \]

*Gate.* The forecast \(\hat Y = \hat a + \hat b\,\text{dose} + \hat c\,A\) is fitted by OLS on completed past events only (at least 60), and the coefficients are frozen at the end of IS for OOS. PG trades if and only if \(\hat Y\) exceeds round-trip cost in risk units; otherwise it stays flat, and it never reverses. There is at most one trade a month.

*Position and costs.* Legs target equal notional and a full-dose five-day standard deviation of 0.87% of NAV, with caps of 0.75 × NAV per leg and 1.5 × NAV gross, in whole contracts at a \$10M reference NAV. Entry is at the \(L{-}4\) settlement and exit at \(F_1\). Cost per contract per side is half a tick (ES \$6.25, ZN \$7.81) plus a \$2.50 fee, about 0.3–0.9 bp of notional over 2015–24; every row is also run at twice these costs.

*Six rows, all reported (\(N = 6\)).* PG, the gate; P0, always trade; PD, a dose-only gate (does progress add anything?); PE, P0 scaled to PG's participation (is any gain just less risk?); PX, PG filled at the 15:59 ET bid and ask; PP, PG applied to mid-month pseudo-events (is it ordinary reversal?). All rows share one walk-forward segment, 2015-10 to 2024-09.

*Confirmatory tests (Holm, one-sided, \(\alpha = 0.05\)).* H1: \(b > 0\) in \(Y = a + b\,\text{dose} + \gamma\,\text{QE}\), where QE marks quarter-end months. H2: \(c_E < 0\) in the stacked event and pseudo-event regression, that is, progress matters more at month-end than mid-month. The studentized month-block bootstrap has 3.8%–6.4% size at nominal 5% on synthetic GARCH histories; low power was disclosed in advance (App. 2). Webull-kit Backtrader matches 85 PG and 127 P0 event P&Ls to \$0.01. At 1× costs, it matches their IS/OOS trade counts, annualized return and volatility, Sharpe, max drawdown, worst month and turnover (A21); it verifies ledger accounting, not independent signal generation.

<div class="pagebreak"></div>

## 4. Results (net of costs, % of a \$10M reference NAV)

### In sample (2015-10 to 2024-09, walk-forward segment)

| Row | Trades | Ret/yr | Vol/yr | SR 1× | SR 2× | Max DD | Worst mo. | Turn./yr | DSR |
|---|---|---|---|---|---|---|---|---|---|
| PG | 69 | −0.04% | 0.87% | −0.05 | −0.08 | 2.55% | −1.17% | 4.4× | 0.08 |
| P0 | 104 | 0.20% | 1.52% | 0.13 | 0.09 | 2.23% | −1.17% | 9.1× | 0.18 |
| PD | 82 | −0.13% | 1.08% | −0.12 | −0.16 | 3.01% | −1.17% | 5.4× | 0.05 |
| PE | 103 | 0.14% | 1.00% | 0.14 | 0.09 | 1.48% | −0.77% | 6.1× | 0.18 |
| PX | 64 | 0.05% | 0.85% | 0.06 | 0.02 | 1.88% | −1.14% | 4.0× | 0.13 |
| PP | 12 | −0.13% | 0.34% | −0.40 | −0.41 | 1.50% | −0.86% | 0.6× | 0.00 |

Monthly returns (zero in flat months), annualized and uncompounded on a fixed NAV. DSR is the deflated Sharpe ratio at \(N = 6\) [6]; it is lower at the logged prior-look counts (App. 2).

<figure><img src="reports/figures/equity_is.png"><figcaption>Figure 2. Cumulative net return, all six rows, IS (1× costs).</figcaption></figure>

*Does the gate help in sample?* Sharpe-ratio differences (90% month-block intervals): PG − P0 −0.18 [−0.62, +0.30], PG − PD +0.07 [−0.36, +0.49] and PG − PE −0.18 [−0.62, +0.29]. PG trades 66% of P0's events yet trails both P0 and PE: the gate removed good trades along with the bad. Neither confirmatory hypothesis survives. For H1, \(\hat b = −0.010\) σ per unit of dose (90% CI [−0.189, +0.179], Holm \(p = 0.638\)): no positive dose effect is established at a tradable lag. For H2, \(\hat c_E = −0.062\) ([−0.279, +0.156], Holm \(p = 0.638\)): the estimate has the predicted sign, but its confidence interval is wide; non-rejection does not establish absence. Wild-bootstrap and Newey–West \(p\)-values agree (App. 2). PG's monthly skew is +0.14 and it wins 43% of its trades. Observed skew does not rule out unobserved tail risk. Descriptively, the signed spread path rises over the holding window in 2010–20 but is flat in 2021–24 (App. 3).

*Failure diagnosis (post-hoc, IS only).* PG kept 69 trades netting −\$36,979 and rejected 35 netting +\$220,504: poor selection explains its shortfall to P0. Separately, split at the month-end close, always-trade's 104 IS positions earned +\$852,016 gross from entry to \(L\), then lost −\$610,953 in the single session from \(L\) to \(F_1\), almost entirely in short-ES positions; costs were \$57,538. Exiting at \(L\) instead would have netted \$794,478 (Sharpe 0.63; 0.59 at twice the costs), profitably in both trade directions and in every era. But this was one of 57 series examined after the result, and adjusted for all of them its \(p\)-value is 0.65; ordinary turn-of-month strength in equities is a competing explanation. The frozen rule was not changed; the analysis is in the repository's `research/` folder.

<!--OOS-->
<div class="pagebreak"></div>

### Out of sample (2024-10 to 2026-09, opened once after `freeze-final`)

| Row | Trades | Ret/yr | Vol/yr | SR 1× | SR 2× | Max DD | Worst mo. | Turn./yr | DSR |
|---|---|---|---|---|---|---|---|---|---|
| PG | 16 | 1.00% | 1.11% | 0.91 | 0.88 | 0.35% | −0.35% | 5.6× | 0.49 |
| P0 | 23 | 0.18% | 1.34% | 0.14 | 0.10 | 1.30% | −0.62% | 8.9× | 0.13 |
| PD | 23 | 0.18% | 1.34% | 0.14 | 0.10 | 1.30% | −0.62% | 8.9× | 0.13 |
| PE | 23 | 0.18% | 0.90% | 0.20 | 0.16 | 0.87% | −0.41% | 6.0× | 0.15 |
| PX | 14 | 0.90% | 1.11% | 0.81 | 0.78 | 0.37% | −0.37% | 5.2× | 0.42 |

PD equals P0 under the frozen IS coefficients. PP is omitted from this table because its frozen model generated no OOS trades (App. 4).

<figure><img src="reports/figures/equity_oos.png"><figcaption>Figure 3. Cumulative net return, all six rows, OOS (1× costs).</figcaption></figure>

*Better out of sample, but 24 months cannot carry the claim.* PG − P0 is +0.77 [+0.09, +1.69], and PG − PE is +0.70 [+0.02, +1.59]. The result survives real quotes (PX 0.81), and descriptive OOS slope estimates have the predicted signs (\(b = +0.26\), \(c_E = −0.31\)), but neither slope nor its change from IS excludes zero (App. 4). Skew is +2.29: the result comes from a few large wins. Two events (2025-07: +113,622 USD; 2025-11: +90,965 USD) earned more than PG's whole OOS net of +200,726 USD. The DSR is 0.49, and at this Sharpe ratio a \(t\)-statistic of 2 would take 58 months. Three performance kill conditions were met in sample, and holiday-window capacity remains unverified (Section 6), and a short positive OOS does not undo them: we report the result as unconfirmed and worth monitoring on paper, not as evidence that the gate works.

<!--/OOS-->

<div class="pagebreak"></div>

## 5. Risk management

*Limits.* Frozen sizing targets a five-day standard deviation of 0.87% of NAV at full dose, capped at 0.75 × NAV per leg and 1.5 × NAV gross. No mid-event reduction is applied. A separate 2σ stop stress closes 2 PG events, changing IS net P&L from −36,979 to −45,029 USD.

*Correlation and factors.* Negative stock–bond correlation amplifies spread variance at fixed leg volatilities: long ES / short ZN loses on both legs when stocks fall and bonds rally. Higher covariance reduces it (App. 5). Regressing IS event returns on Mkt-RF, SMB, HML, Mom and ZN gives alpha −0.0002 per event (\(t=−0.44\)), market \(t=0.35\), and \(R^2=0.03\). This specification detects neither significant market loading nor alpha.

*Tails and capital.* The historical bootstrap has no 7.5% drawdown breaches over 36 months; it does not cover unseen regimes. Margin-to-equity is 2.0% at the median event (8.7% maximum). An illustrative 20% long-ES shock costs 2.3% of NAV at median size and 8.7% at maximum size, excluding concurrent ZN moves and execution effects; this is not a loss bound. The worst realized event lost −116,628 USD.

*Proposed governance (not backtested).* A 24-event loss or decay trigger would pause trading pending review; thresholds and validation remain prospective.

## 6. Liquidity and capital

*Execution.* Settlement marks are assumed fills (ZN 15:00 ET; ES 16:15 before 2020-10-26, then 16:00). PX pays the 15:59 bid/ask and excludes early-close entries/exits. On matching dates, PG/PX Sharpe is 0.05/0.06 IS and 0.76/0.81 OOS (A22); unmatched table rows also differ in event coverage.

*Volume-based capacity.* ZN binds in 72% of events. Median NAV limits at 1%, 5% and 10% execution-minute participation are \$43,700,000, \$218,500,000 and \$437,000,000; the 1% limit is \$8,236,120 at the 10th percentile. The 93% one-lot pass rate covers all 64 regular-window events; five early closes lack that window. Holiday capacity is unverified, not observed illiquidity. The registered condition is not satisfied throughout; no liquidity filter is backtested.

*Costs and impact.* At \$10M, costs are 2% of the sum of absolute gross event P&Ls, not aggregate gross profit. Square-root impact changes IS Sharpe from −0.05 to −0.06 at \$10M, −0.08 at \$100M and −0.15 at \$1B (App. 6). Negative IS Sharpe means these volume limits do not demonstrate profitable capacity.

## 7. Limitations and next steps

- *Power.* About 170 events give H1 at most ~20% power and H2 58% at \(c_E = −0.27\); wide intervals leave both effects unresolved.
- *Every look, counted.* Prior work: a private 2010–22 proxy study and at least 29 month-end and 45 trend/volatility variants (DSR in App. 2). A masked run exposed PG's IS count and two Sharpe signs (A16); no changes followed. Post-result IS work: 57 diagnostic series; replication of [1] (threshold Holm \(p = 0.027\), calendar signal unconfirmed); an unconfirmed CFTC test; and 11 multi-signal trials without a holdout. None changed the strategy.
- *Data, clocks and identification.* Vendor fallbacks (App. 1), changing benchmark clocks and unobserved trader identities limit interpretation.<!--OOS--> Seven OOS settlements lack a final flag, including the largest winner's exit; quotes and minute bars confirm that price (amendment A20).<!--/OOS-->
- *Next.* Pre-register an exit at the month-end close (\(L\)) and test it on new data, since both samples have been seen; then study depth and execution timing.

<div class="endbody"></div>

## References

1. Harvey, C. R., Mazzoleni, M., and Melone, A. (2025). *The Unintended Consequences of Rebalancing.* NBER Working Paper w33554.
2. Brøgger, Søren Bundgaard (2020). *The Market Impact of Predictable Flows: Evidence from Leveraged VIX Products.* Working paper, April 3. [SSRN 3497537](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3497537).
3. Bessembinder, H., Carrion, A., Tuttle, L., and Venkataraman, K. (2016). Liquidity, resiliency and market quality around predictable trades: Theory and evidence. *Journal of Financial Economics* 121(1), 142–166.
4. Databento. CME Globex MDP 3.0 (GLBX.MDP3): `definition`, `statistics`, `bbo-1m`, `ohlcv-1m` schemas. databento.com.
5. French, K. R. Data Library: Fama/French 3 factors (daily) and Momentum factor (daily). mba.tuck.dartmouth.edu/pages/faculty/ken.french.
6. Bailey, D. H., and López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management* 40(5), 94–107.
7. Backtrader (v1.9.78), backtrader.com; exchange_calendars; CME Group performance-bond (margin) requirements, retrieved 2026-10-03.

## Appendix (optional reading; not needed for the main argument)

*App. 1. Vendor data facts (amendment A14).* Before CME's MDP 3.0 feed (2010–2015) the vendor's settlement records carry no "final" flag and open interest is not published. Settlements use the frozen "last record per contract and day" rule, which matches the flagged final on 99.75–100% of contract-days where both exist. Where open interest is missing, contracts are ranked by volume, which picks the same contract on 98–99% of days and 106/106 event dates where both exist. Decision dates are recomputed on the calendar a trader knew at the time (Hurricane Sandy; four vendor-degraded months).

*App. 2. Inference.* Studentized circular month-block bootstrap (block 3, 9,999 draws, seed 20261003). On 500 synthetic AR(1)-GARCH(1,1)-t₅ histories per null run through the real signal code, size is 3.8%–6.4% at nominal 5% (registered band 3–7%). H1 rejects 11% of the time at \(b = 0.05\) and 20% at \(b = 0.12\); H2 rejects 58% at \(c_E = −0.27\) (80%-power minimum detectable effect ≈ 0.37). Ordinary reversal alone makes H1 reject 12.6% of the time, which is why H2 and PP exist. Confirmatory p-values, one-sided: H1 0.523 (wild 0.522, Newey-West(3) 0.536); H2 0.319 (0.317, 0.315). PG's DSR at the logged prior-look counts (35 and 80) is 0.01 and 0.00. PE scales P0's target size by p = 0.66; whole-contract rounding leaves 103 IS trades versus P0's 104, because one scaled position falls below a tradable lot. Backtrader replay at 2× costs: 85/85 PG, 127/127 P0.

*App. 3. Diagnostics (IS).* With sign and dose frozen at L−12, the dose-weighted cumulative spread path rises from +0.05 σ at L−4 to +0.49 σ at L in 2010–15 and from −0.68 to +0.09 σ in 2016–20; in 2021–24 it is flat (+0.11, +0.09). P0's small positive result does not establish alpha: the 32 events that buy ES after stocks lagged netted +394,194 USD, the 72 that sell ES −210,669 USD. P0's factor-adjusted alpha is −0.00006 per event (t = −0.13); it loads on ZN (t = 2.03). After 2021-01-14, ZN's 15:00→16:00 ET return on L is +1.6 bp signed toward the flow vs +0.6 bp on other days. PG's ZN loading is −0.010 (t = −0.13), market +0.013. P0 also has no 7.5% drawdown breaches in the 36-month historical bootstrap; unseen regimes are not covered. At P0's IS Sharpe a t-statistic of 2 would need 2,677 months. Realized-to-target risk lies in [0.6, 1.5] in 70% of years.

<!--OOS-->
<div class="pagebreak"></div>

*App. 4. Frozen trading coefficients and descriptive OOS slopes.* PD's forecast is almost constant (0.032 + 0.002·dose) and always clears cost, so PD trades every event like P0; PP's (−0.039 −0.057·dose −0.002·A) stayed below cost on every OOS pseudo-event. \(b_{\mathrm{OOS}} = +0.262\) (\(\Delta b = +0.271\), 90% CI [−0.300, +1.314]); \(c_{E,\mathrm{OOS}} = −0.311\) (\(\Delta c = −0.249\), [−0.816, +0.327]).
<!--/OOS-->

*App. 5. Stress periods* (P0 on every valid IS event; event P&L by leg, % of NAV). Spread variance is \(h_E^2\sigma_E^2 + h_B^2\sigma_B^2 - 2h_E h_B\,\mathrm{Cov}(r_E, r_B)\).

| Period | Events | ES leg | ZN leg | Costs | Net |
|---|---|---|---|---|---|
| 2011-08 | 1 | +0.28% | −0.03% | 0.00% | +0.25% |
| 2015-08 | 1 | +0.43% | +0.03% | 0.01% | +0.45% |
| 2018-02 | 1 | −0.10% | −0.05% | 0.00% | −0.15% |
| 2020-03 | 1 | −0.03% | −0.03% | 0.00% | −0.06% |
| 2022 | 12 | +1.11% | −0.15% | 0.03% | +0.92% |
| 2023-03 | 1 | +0.29% | −0.03% | 0.00% | +0.26% |

*App. 6. Event path and impact.* Margins used (CME, 2026-10-03): ES $26,164, ZN $1,875 per contract. ES settled 16:14:30–16:15 ET before 2020-10-26.

<figure><img src="reports/figures/event_path.png"><figcaption>Figure A1. Signed spread path, L−12 to F1+5, by era (event counts in parentheses; sign and dose frozen at L−12).</figcaption></figure>
<figure><img src="reports/figures/impact.png"><figcaption>Figure A2. PG net Sharpe vs NAV under square-root impact.</figcaption></figure>

Full audit (data coverage, decision-date shifts, action ledger, Backtrader reconciliation, inference calibration) and every amendment: `AMENDMENTS.md`, `reports/`.

*App. 7. Additional diagnostics.*

<figure><img src="reports/figures/key_y_vs_a.png"><figcaption>Figure A3. Remaining return against pre-entry progress (IS); bin means with 90% intervals.</figcaption></figure>

<figure><img src="reports/figures/pg_oos_events.png"><figcaption>Figure A4. PG net P&amp;L by OOS event. Grey ticks denote no trade; two events carry the result.</figcaption></figure>
