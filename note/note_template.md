# Paying for what is left: a pre-registered remaining-return gate on month-end 60/40 rebalancing flow in ES/ZN futures

## Summary

Calendar-based 60/40 rebalancing sells the outperforming asset and buys the laggard. We test how much return remains after earlier price adjustment, using a pre-registered gate (PG; git tag `prereg-final`). At the \(L{-}5\) settlement, PG forecasts the remaining ES–ZN spread return from the rebalancing need (*dose*) and prior signed price movement (*progress*). It enters at \(L{-}4\) only when the forecast exceeds round-trip cost, and exits at the first session of the new month.

In sample ({{rows_IS.months.0}} to {{rows_IS.months.1}}) the gate failed: PG's net Sharpe ratio was {{rows_IS.rows.PG@1x.sharpe:.2f}} against {{rows_IS.rows.P0@1x.sharpe:.2f}} for always trading, and neither confirmatory hypothesis survived (Holm-adjusted \(p = {{confirmatory.holm.H1:.2f}}\) and \({{confirmatory.holm.H2:.2f}}\)). Post-hoc analysis distinguishes poor gate selection from the baseline trade's first-session giveback (Section 4). <!--OOS-->Out of sample ({{rows_OOS.months.0}} to {{rows_OOS.months.1}}) PG did better ({{rows_OOS.rows.PG@1x.sharpe:.2f}} vs {{rows_OOS.rows.P0@1x.sharpe:.2f}}), but on {{rows_OOS.rows.PG@1x.trades}} trades, two of which carry the result, this does not overturn the in-sample failure.<!--/OOS-->

## 1. Economic hypothesis

*Mechanism.* A 60/40 fund whose stocks rise 10% while bonds are flat ends the month 62.3% in stocks and must sell \$2.40 of stocks per \$100 to rebalance. In general the drift in the stock weight is
\[ D = \frac{0.24\,(R_E - R_B)}{1 + 0.6\,R_E + 0.4\,R_B}, \]
where \(R_E\) and \(R_B\) are the month-to-date equity and bond returns. This is accounting, not a forecast: it is the demand of a hypothetical fund, and we observe no orders.

*Edge source: a structural constraint.* Calendar rebalancers and their overlay managers target portfolio weights on scheduled dates. Potential counterparties at entry include liquidity suppliers and earlier anticipators; we do not identify them directly. Rebalancing pressure is documented in [1], but predictable flow need not yield profits after costs [2–3]. Governance constraints and limited risk capital motivate the hypothesis; they do not establish a persistent tradable edge.

*Our contribution.* We test whether prior price adjustment helps predict the remaining return after costs. Anticipation and reduced portfolio drift predict less remaining return; news momentum and persistent orders predict more. Our extension combines four design elements: (i) a gate on the *remaining* move; (ii) a mid-month placebo (PP) to test against ordinary reversal; (iii) an exposure-matched control (PE) to distinguish selection from taking less risk; and (iv) pre-registered kill conditions, with every registered variant reported. The contribution is this joint test in month-end rebalancing, not the invention of these methods.

*Kill conditions (pre-registered).* An in-sample dose slope \(b \le 0\); a progress interaction \(c_E \ge 0\); no gain over the exposure-matched control; a net Sharpe ratio \(\le 0\) at twice the assumed costs; or a binding leg that cannot fill one contract within 1% of execution-window volume.

## 2. Data and universe

*Sources and samples.* Databento GLBX.MDP3 [4] supplies outright quarterly ES/ZN definitions, settlements, open interest, volume and minute quotes/bars; French supplies daily factors [5]. IS runs from 2010-06-07 to 2024-10-01. OOS starts 2024-10-02, covering two years under the track rule, and was evaluated after `freeze-final`<!--OOS--> ({{sample_counts.OOS.events}} usable months)<!--/OOS-->. Published extensions had partly exposed Oct-2024–Dec-2025 before registration; this is a frozen-rule evaluation, not a wholly untouched holdout.

*Sessions and contracts.* A session is a CME date on which both legs settle and NYSE is open ({{sample_counts.IS.events}} IS months, {{sample_counts.IS.valid_events}} valid events, {{sample_counts.IS.valid_pseudos}} pseudo-events). \(L\) is the last such session of a month and \(F_1\) the first of the next. The ES contract is the one with the highest open interest at \(L{-}8\); the ZN contract is the nearest one whose first position day falls after \(F_1\). Settlements drive signals and P&L; minute data support PX fills and capacity. Each leg holds one expiry in variable whole-contract quantities, without rolling during an event. The full futures universe needs no equity split/dividend adjustment. Two initial months lack the volatility warm-up; Sep-2014 lacks a decision-day settlement. These three events are excluded; prices are never filled from later dates. Pre-2015 final flags and open interest are missing; validated frozen fallbacks apply (App. 1).

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

*Six rows, all reported (\(N = 6\)).* PG, the gate; P0, always trade; PD, a dose-only gate (does progress add anything?); PE, P0 scaled to PG's participation (is any gain just less risk?); PX, PG filled at the 15:59 ET bid and ask; PP, PG applied to mid-month pseudo-events (is it ordinary reversal?). All rows share one walk-forward segment, {{segment_start}} to 2024-09.

*Confirmatory tests (Holm, one-sided, \(\alpha = 0.05\)).* H1: \(b > 0\) in \(Y = a + b\,\text{dose} + \gamma\,\text{QE}\), where QE marks quarter-end months. H2: \(c_E < 0\) in the stacked event and pseudo-event regression, that is, progress matters more at month-end than mid-month. The studentized month-block bootstrap has {{calibration.scenarios.h2_reversal.H2_month_block.rate:.1%}}–{{calibration.scenarios.base.H1_month_block.rate:.1%}} size at nominal 5% on synthetic GARCH histories; low power was disclosed in advance (App. 2). Webull-kit Backtrader matches {{backtrader_replay.PG@1x.events}} PG and {{backtrader_replay.P0@1x.events}} P0 event P&Ls to \$0.01. At 1× costs, it matches their IS/OOS trade counts, annualized return and volatility, Sharpe, max drawdown, worst month and turnover (A21); it verifies ledger accounting, not independent signal generation.

<div class="pagebreak"></div>

## 4. Results (net of costs, % of a \$10M reference NAV)

### In sample ({{rows_IS.months.0}} to {{rows_IS.months.1}}, walk-forward segment)

| Row | Trades | Ret/yr | Vol/yr | SR 1× | SR 2× | Max DD | Worst mo. | Turn./yr | DSR |
|---|---|---|---|---|---|---|---|---|---|
| PG | {{rows_IS.rows.PG@1x.trades}} | {{rows_IS.rows.PG@1x.ann_return:.2%}} | {{rows_IS.rows.PG@1x.ann_vol:.2%}} | {{rows_IS.rows.PG@1x.sharpe:.2f}} | {{rows_IS.rows.PG@2x.sharpe:.2f}} | {{rows_IS.rows.PG@1x.max_drawdown:.2%}} | {{rows_IS.rows.PG@1x.worst_month:.2%}} | {{rows_IS.rows.PG@1x.turnover:.1f}}× | {{rows_IS.rows.PG@1x.dsr.registered_6:.2f}} |
| P0 | {{rows_IS.rows.P0@1x.trades}} | {{rows_IS.rows.P0@1x.ann_return:.2%}} | {{rows_IS.rows.P0@1x.ann_vol:.2%}} | {{rows_IS.rows.P0@1x.sharpe:.2f}} | {{rows_IS.rows.P0@2x.sharpe:.2f}} | {{rows_IS.rows.P0@1x.max_drawdown:.2%}} | {{rows_IS.rows.P0@1x.worst_month:.2%}} | {{rows_IS.rows.P0@1x.turnover:.1f}}× | {{rows_IS.rows.P0@1x.dsr.registered_6:.2f}} |
| PD | {{rows_IS.rows.PD@1x.trades}} | {{rows_IS.rows.PD@1x.ann_return:.2%}} | {{rows_IS.rows.PD@1x.ann_vol:.2%}} | {{rows_IS.rows.PD@1x.sharpe:.2f}} | {{rows_IS.rows.PD@2x.sharpe:.2f}} | {{rows_IS.rows.PD@1x.max_drawdown:.2%}} | {{rows_IS.rows.PD@1x.worst_month:.2%}} | {{rows_IS.rows.PD@1x.turnover:.1f}}× | {{rows_IS.rows.PD@1x.dsr.registered_6:.2f}} |
| PE | {{rows_IS.rows.PE@1x.trades}} | {{rows_IS.rows.PE@1x.ann_return:.2%}} | {{rows_IS.rows.PE@1x.ann_vol:.2%}} | {{rows_IS.rows.PE@1x.sharpe:.2f}} | {{rows_IS.rows.PE@2x.sharpe:.2f}} | {{rows_IS.rows.PE@1x.max_drawdown:.2%}} | {{rows_IS.rows.PE@1x.worst_month:.2%}} | {{rows_IS.rows.PE@1x.turnover:.1f}}× | {{rows_IS.rows.PE@1x.dsr.registered_6:.2f}} |
| PX | {{rows_IS.rows.PX@1x.trades}} | {{rows_IS.rows.PX@1x.ann_return:.2%}} | {{rows_IS.rows.PX@1x.ann_vol:.2%}} | {{rows_IS.rows.PX@1x.sharpe:.2f}} | {{rows_IS.rows.PX@2x.sharpe:.2f}} | {{rows_IS.rows.PX@1x.max_drawdown:.2%}} | {{rows_IS.rows.PX@1x.worst_month:.2%}} | {{rows_IS.rows.PX@1x.turnover:.1f}}× | {{rows_IS.rows.PX@1x.dsr.registered_6:.2f}} |
| PP | {{rows_IS.rows.PP@1x.trades}} | {{rows_IS.rows.PP@1x.ann_return:.2%}} | {{rows_IS.rows.PP@1x.ann_vol:.2%}} | {{rows_IS.rows.PP@1x.sharpe:.2f}} | {{rows_IS.rows.PP@2x.sharpe:.2f}} | {{rows_IS.rows.PP@1x.max_drawdown:.2%}} | {{rows_IS.rows.PP@1x.worst_month:.2%}} | {{rows_IS.rows.PP@1x.turnover:.1f}}× | {{rows_IS.rows.PP@1x.dsr.registered_6:.2f}} |

Monthly returns (zero in flat months), annualized and uncompounded on a fixed NAV. DSR is the deflated Sharpe ratio at \(N = 6\) [6]; it is lower at the logged prior-look counts (App. 2).

<figure><img src="reports/figures/equity_is.png"><figcaption>Figure 2. Cumulative net return, all six rows, IS (1× costs).</figcaption></figure>

*Does the gate help in sample?* Sharpe-ratio differences (90% month-block intervals): PG − P0 {{rows_IS.delta_sharpe.PG-P0@1x.estimate:+.2f}} [{{rows_IS.delta_sharpe.PG-P0@1x.ci90.0:+.2f}}, {{rows_IS.delta_sharpe.PG-P0@1x.ci90.1:+.2f}}], PG − PD {{rows_IS.delta_sharpe.PG-PD@1x.estimate:+.2f}} [{{rows_IS.delta_sharpe.PG-PD@1x.ci90.0:+.2f}}, {{rows_IS.delta_sharpe.PG-PD@1x.ci90.1:+.2f}}] and PG − PE {{rows_IS.delta_sharpe.PG-PE@1x.estimate:+.2f}} [{{rows_IS.delta_sharpe.PG-PE@1x.ci90.0:+.2f}}, {{rows_IS.delta_sharpe.PG-PE@1x.ci90.1:+.2f}}]. PG trades {{pe_participation_p:.0%}} of P0's events yet trails both P0 and PE: the gate removed good trades along with the bad. Neither confirmatory hypothesis survives. For H1, \(\hat b = {{confirmatory.H1.month_block.estimate:+.3f}}\) σ per unit of dose (90% CI [{{confirmatory.H1.month_block.ci90.0:+.3f}}, {{confirmatory.H1.month_block.ci90.1:+.3f}}], Holm \(p = {{confirmatory.holm.H1:.3f}}\)): no positive dose effect is established at a tradable lag. For H2, \(\hat c_E = {{confirmatory.H2.month_block.estimate:+.3f}}\) ([{{confirmatory.H2.month_block.ci90.0:+.3f}}, {{confirmatory.H2.month_block.ci90.1:+.3f}}], Holm \(p = {{confirmatory.holm.H2:.3f}}\)): the estimate has the predicted sign, but its confidence interval is wide; non-rejection does not establish absence. Wild-bootstrap and Newey–West \(p\)-values agree (App. 2). PG's monthly skew is {{rows_IS.rows.PG@1x.skew:+.2f}} and it wins {{rows_IS.rows.PG@1x.hit_rate:.0%}} of its trades. Observed skew does not rule out unobserved tail risk. Descriptively, the signed spread path rises over the holding window in 2010–20 but is flat in 2021–24 (App. 3).

*Failure diagnosis (post-hoc, IS only).* PG kept 69 trades netting −\$36,979 and rejected 35 netting +\$220,504: poor selection explains its shortfall to P0. Separately, split at the month-end close, always-trade's 104 IS positions earned +\$852,016 gross from entry to \(L\), then lost −\$610,953 in the single session from \(L\) to \(F_1\), almost entirely in short-ES positions; costs were \$57,538. Exiting at \(L\) instead would have netted \$794,478 (Sharpe 0.63; 0.59 at twice the costs), profitably in both trade directions and in every era. But this was one of 57 series examined after the result, and adjusted for all of them its \(p\)-value is 0.65; ordinary turn-of-month strength in equities is a competing explanation. The frozen rule was not changed; the analysis is in the repository's `research/` folder.

<!--OOS-->
<div class="pagebreak"></div>

### Out of sample ({{rows_OOS.months.0}} to {{rows_OOS.months.1}}, opened once after `freeze-final`)

| Row | Trades | Ret/yr | Vol/yr | SR 1× | SR 2× | Max DD | Worst mo. | Turn./yr | DSR |
|---|---|---|---|---|---|---|---|---|---|
| PG | {{rows_OOS.rows.PG@1x.trades}} | {{rows_OOS.rows.PG@1x.ann_return:.2%}} | {{rows_OOS.rows.PG@1x.ann_vol:.2%}} | {{rows_OOS.rows.PG@1x.sharpe:.2f}} | {{rows_OOS.rows.PG@2x.sharpe:.2f}} | {{rows_OOS.rows.PG@1x.max_drawdown:.2%}} | {{rows_OOS.rows.PG@1x.worst_month:.2%}} | {{rows_OOS.rows.PG@1x.turnover:.1f}}× | {{rows_OOS.rows.PG@1x.dsr.registered_6:.2f}} |
| P0 | {{rows_OOS.rows.P0@1x.trades}} | {{rows_OOS.rows.P0@1x.ann_return:.2%}} | {{rows_OOS.rows.P0@1x.ann_vol:.2%}} | {{rows_OOS.rows.P0@1x.sharpe:.2f}} | {{rows_OOS.rows.P0@2x.sharpe:.2f}} | {{rows_OOS.rows.P0@1x.max_drawdown:.2%}} | {{rows_OOS.rows.P0@1x.worst_month:.2%}} | {{rows_OOS.rows.P0@1x.turnover:.1f}}× | {{rows_OOS.rows.P0@1x.dsr.registered_6:.2f}} |
| PD | {{rows_OOS.rows.PD@1x.trades}} | {{rows_OOS.rows.PD@1x.ann_return:.2%}} | {{rows_OOS.rows.PD@1x.ann_vol:.2%}} | {{rows_OOS.rows.PD@1x.sharpe:.2f}} | {{rows_OOS.rows.PD@2x.sharpe:.2f}} | {{rows_OOS.rows.PD@1x.max_drawdown:.2%}} | {{rows_OOS.rows.PD@1x.worst_month:.2%}} | {{rows_OOS.rows.PD@1x.turnover:.1f}}× | {{rows_OOS.rows.PD@1x.dsr.registered_6:.2f}} |
| PE | {{rows_OOS.rows.PE@1x.trades}} | {{rows_OOS.rows.PE@1x.ann_return:.2%}} | {{rows_OOS.rows.PE@1x.ann_vol:.2%}} | {{rows_OOS.rows.PE@1x.sharpe:.2f}} | {{rows_OOS.rows.PE@2x.sharpe:.2f}} | {{rows_OOS.rows.PE@1x.max_drawdown:.2%}} | {{rows_OOS.rows.PE@1x.worst_month:.2%}} | {{rows_OOS.rows.PE@1x.turnover:.1f}}× | {{rows_OOS.rows.PE@1x.dsr.registered_6:.2f}} |
| PX | {{rows_OOS.rows.PX@1x.trades}} | {{rows_OOS.rows.PX@1x.ann_return:.2%}} | {{rows_OOS.rows.PX@1x.ann_vol:.2%}} | {{rows_OOS.rows.PX@1x.sharpe:.2f}} | {{rows_OOS.rows.PX@2x.sharpe:.2f}} | {{rows_OOS.rows.PX@1x.max_drawdown:.2%}} | {{rows_OOS.rows.PX@1x.worst_month:.2%}} | {{rows_OOS.rows.PX@1x.turnover:.1f}}× | {{rows_OOS.rows.PX@1x.dsr.registered_6:.2f}} |

PD equals P0 under the frozen IS coefficients. PP is omitted from this table because its frozen model generated no OOS trades (App. 4).

<figure><img src="reports/figures/equity_oos.png"><figcaption>Figure 3. Cumulative net return, all six rows, OOS (1× costs).</figcaption></figure>

*Better out of sample, but 24 months cannot carry the claim.* PG − P0 is {{rows_OOS.delta_sharpe.PG-P0@1x.estimate:+.2f}} [{{rows_OOS.delta_sharpe.PG-P0@1x.ci90.0:+.2f}}, {{rows_OOS.delta_sharpe.PG-P0@1x.ci90.1:+.2f}}], and PG − PE is {{rows_OOS.delta_sharpe.PG-PE@1x.estimate:+.2f}} [{{rows_OOS.delta_sharpe.PG-PE@1x.ci90.0:+.2f}}, {{rows_OOS.delta_sharpe.PG-PE@1x.ci90.1:+.2f}}]. The result survives real quotes (PX {{rows_OOS.rows.PX@1x.sharpe:.2f}}), and descriptive OOS slope estimates have the predicted signs (\(b = {{oos_slopes.b.OOS:+.2f}}\), \(c_E = {{oos_slopes.c_E.OOS:+.2f}}\)), but neither slope nor its change from IS excludes zero (App. 4). Skew is {{rows_OOS.rows.PG@1x.skew:+.2f}}: the result comes from a few large wins. Two events ({{diagnostics.action_ledger_PG.month.117}}: {{diagnostics.action_ledger_PG.net.117:+,.0f}} USD; {{diagnostics.action_ledger_PG.month.121}}: {{diagnostics.action_ledger_PG.net.121:+,.0f}} USD) earned more than PG's whole OOS net of {{risk_OOS.PG.stop_2sigma_stress.net_without_stop:+,.0f}} USD. The DSR is {{rows_OOS.rows.PG@1x.dsr.registered_6:.2f}}, and at this Sharpe ratio a \(t\)-statistic of 2 would take {{risk_OOS.PG.months_to_t2:.0f}} months. Three performance kill conditions were met in sample, and holiday-window capacity remains unverified (Section 6), and a short positive OOS does not undo them: we report the result as unconfirmed and worth monitoring on paper, not as evidence that the gate works.

<!--/OOS-->

<div class="pagebreak"></div>

## 5. Risk management

*Limits.* Frozen sizing targets a five-day standard deviation of 0.87% of NAV at full dose, capped at 0.75 × NAV per leg and 1.5 × NAV gross. No mid-event reduction is applied. A separate 2σ stop stress closes {{risk_IS.PG.stop_2sigma_stress.stopped_events}} PG events, changing IS net P&L from {{risk_IS.PG.stop_2sigma_stress.net_without_stop:,.0f}} to {{risk_IS.PG.stop_2sigma_stress.net_with_stop:,.0f}} USD.

*Correlation and factors.* Negative stock–bond correlation amplifies spread variance at fixed leg volatilities: long ES / short ZN loses on both legs when stocks fall and bonds rally. Higher covariance reduces it (App. 5). Regressing IS event returns on Mkt-RF, SMB, HML, Mom and ZN gives alpha {{risk_IS.PG.factor_regression.coef.alpha:+.4f}} per event (\(t={{risk_IS.PG.factor_regression.t.alpha:.2f}}\)), market \(t={{risk_IS.PG.factor_regression.t.Mkt-RF:.2f}}\), and \(R^2={{risk_IS.PG.factor_regression.r2:.2f}}\). This specification detects neither significant market loading nor alpha.

*Tails and capital.* The historical bootstrap has no 7.5% drawdown breaches over 36 months; it does not cover unseen regimes. Margin-to-equity is {{risk_IS.PG.margin.margin_to_equity_median:.1%}} at the median event ({{risk_IS.PG.margin.margin_to_equity_max:.1%}} maximum). An illustrative 20% long-ES shock costs {{pg_size.crash_loss_median:.1%}} of NAV at median size and {{pg_size.crash_loss_max:.1%}} at maximum size, excluding concurrent ZN moves and execution effects; this is not a loss bound. The worst realized event lost {{pg_size.worst_event_usd:,.0f}} USD.

*Proposed governance (not backtested).* A 24-event loss or decay trigger would pause trading pending review; thresholds and validation remain prospective.

## 6. Liquidity and capital

*Execution.* Settlement marks are assumed fills (ZN 15:00 ET; ES 16:15 before 2020-10-26, then 16:00). PX pays the 15:59 bid/ask and excludes early-close entries/exits. On matching dates, PG/PX Sharpe is 0.05/0.06 IS and 0.76/0.81 OOS (A22); unmatched table rows also differ in event coverage.

*Volume-based capacity.* ZN binds in {{rows_IS.capacity.PG_settle_windows.binding_share_ZN:.0%}} of events. Median NAV limits at 1%, 5% and 10% execution-minute participation are \${{rows_IS.capacity.PG_settle_windows.max_nav_1pct.median:,.0f}}, \${{rows_IS.capacity.PG_settle_windows.max_nav_5pct.median:,.0f}} and \${{rows_IS.capacity.PG_settle_windows.max_nav_10pct.median:,.0f}}; the 1% limit is \${{rows_IS.capacity.PG_settle_windows.max_nav_1pct.p10:,.0f}} at the 10th percentile. The {{rows_IS.capacity.PG_settle_windows.lot_at_1pct_share:.0%}} one-lot pass rate covers all 64 regular-window events; five early closes lack that window. Holiday capacity is unverified, not observed illiquidity. The registered condition is not satisfied throughout; no liquidity filter is backtested.

*Costs and impact.* At \$10M, costs are {{rows_IS.rows.PG@1x.cost_share_of_gross:.0%}} of the sum of absolute gross event P&Ls, not aggregate gross profit. Square-root impact changes IS Sharpe from {{rows_IS.rows.PG@1x.sharpe:.2f}} to {{risk_IS.impact_PG.1.sharpe:.2f}} at \$10M, {{risk_IS.impact_PG.2.sharpe:.2f}} at \$100M and {{risk_IS.impact_PG.4.sharpe:.2f}} at \$1B (App. 6). Negative IS Sharpe means these volume limits do not demonstrate profitable capacity.

## 7. Limitations and next steps

- *Power.* About 170 events give H1 at most ~20% power and H2 58% at \(c_E = -0.27\); wide intervals leave both effects unresolved.
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

*App. 2. Inference.* Studentized circular month-block bootstrap (block 3, 9,999 draws, seed 20261003). On 500 synthetic AR(1)-GARCH(1,1)-t₅ histories per null run through the real signal code, size is {{calibration.scenarios.h2_reversal.H2_month_block.rate:.1%}}–{{calibration.scenarios.base.H1_month_block.rate:.1%}} at nominal 5% (registered band 3–7%). H1 rejects {{calibration.scenarios.h1_power.H1_month_block.rate:.0%}} of the time at \(b = 0.05\) and {{calibration.scenarios.h1_power_hi.H1_month_block.rate:.0%}} at \(b = 0.12\); H2 rejects {{calibration.scenarios.h2_power.H2_month_block.rate:.0%}} at \(c_E = -0.27\) (80%-power minimum detectable effect ≈ 0.37). Ordinary reversal alone makes H1 reject {{calibration.scenarios.h2_reversal.H1_month_block.rate:.1%}} of the time, which is why H2 and PP exist. Confirmatory p-values, one-sided: H1 {{confirmatory.H1.month_block.p_one_sided:.3f}} (wild {{confirmatory.H1.wild.p_one_sided:.3f}}, Newey-West(3) {{confirmatory.H1.newey_west.p_one_sided:.3f}}); H2 {{confirmatory.H2.month_block.p_one_sided:.3f}} ({{confirmatory.H2.wild.p_one_sided:.3f}}, {{confirmatory.H2.newey_west.p_one_sided:.3f}}). PG's DSR at the logged prior-look counts (35 and 80) is {{rows_IS.rows.PG@1x.dsr.month_end_family_35:.2f}} and {{rows_IS.rows.PG@1x.dsr.all_logged_80:.2f}}. PE scales P0's target size by p = {{pe_participation_p:.2f}}; whole-contract rounding leaves {{rows_IS.rows.PE@1x.trades}} IS trades versus P0's {{rows_IS.rows.P0@1x.trades}}, because one scaled position falls below a tradable lot. Backtrader replay at 2× costs: {{backtrader_replay.PG@2x.matched}}/{{backtrader_replay.PG@2x.events}} PG, {{backtrader_replay.P0@2x.matched}}/{{backtrader_replay.P0@2x.events}} P0.

*App. 3. Diagnostics (IS).* With sign and dose frozen at L−12, the dose-weighted cumulative spread path rises from {{is_run.diagnostics.event_path_by_era.2010-15.k-4:+.2f}} σ at L−4 to {{is_run.diagnostics.event_path_by_era.2010-15.k+0:+.2f}} σ at L in 2010–15 and from {{is_run.diagnostics.event_path_by_era.2016-20.k-4:+.2f}} to {{is_run.diagnostics.event_path_by_era.2016-20.k+0:+.2f}} σ in 2016–20; in 2021–24 it is flat ({{is_run.diagnostics.event_path_by_era.2021-24.k-4:+.2f}}, {{is_run.diagnostics.event_path_by_era.2021-24.k+0:+.2f}}). P0's small positive result does not establish alpha: the {{is_run.diagnostics.legs_direction.P0.1.events}} events that buy ES after stocks lagged netted {{is_run.diagnostics.legs_direction.P0.1.net:+,.0f}} USD, the {{is_run.diagnostics.legs_direction.P0.-1.events}} that sell ES {{is_run.diagnostics.legs_direction.P0.-1.net:+,.0f}} USD. P0's factor-adjusted alpha is {{is_run.risk_IS.P0.factor_regression.coef.alpha:+.5f}} per event (t = {{is_run.risk_IS.P0.factor_regression.t.alpha:.2f}}); it loads on ZN (t = {{is_run.risk_IS.P0.factor_regression.t.ZN:.2f}}). After 2021-01-14, ZN's 15:00→16:00 ET return on L is {{is_run.diagnostics.benchmark_clock.0.L_flow_signed_mean_bp:+.1f}} bp signed toward the flow vs {{is_run.diagnostics.benchmark_clock.0.other_mean_bp:+.1f}} bp on other days. PG's ZN loading is {{risk_IS.PG.factor_regression.coef.ZN:+.3f}} (t = {{risk_IS.PG.factor_regression.t.ZN:.2f}}), market {{risk_IS.PG.factor_regression.coef.Mkt-RF:+.3f}}. P0 also has no 7.5% drawdown breaches in the 36-month historical bootstrap; unseen regimes are not covered. At P0's IS Sharpe a t-statistic of 2 would need {{risk_IS.P0.months_to_t2:,.0f}} months. Realized-to-target risk lies in [0.6, 1.5] in {{rows_IS.realized_to_target_PG_share_in_band:.0%}} of years.

<!--OOS-->
<div class="pagebreak"></div>

*App. 4. Frozen trading coefficients and descriptive OOS slopes.* PD's forecast is almost constant ({{gate_final_coefficients.PD.coef_const:.3f}} + {{gate_final_coefficients.PD.coef_dose:.3f}}·dose) and always clears cost, so PD trades every event like P0; PP's ({{gate_final_coefficients.PP.coef_const:.3f}} {{gate_final_coefficients.PP.coef_dose:+.3f}}·dose {{gate_final_coefficients.PP.coef_A:+.3f}}·A) stayed below cost on every OOS pseudo-event. \(b_{\mathrm{OOS}} = {{oos_slopes.b.OOS:+.3f}}\) (\(\Delta b = {{oos_slopes.b.delta:+.3f}}\), 90% CI [{{oos_slopes.b.delta_ci90.0:+.3f}}, {{oos_slopes.b.delta_ci90.1:+.3f}}]); \(c_{E,\mathrm{OOS}} = {{oos_slopes.c_E.OOS:+.3f}}\) (\(\Delta c = {{oos_slopes.c_E.delta:+.3f}}\), [{{oos_slopes.c_E.delta_ci90.0:+.3f}}, {{oos_slopes.c_E.delta_ci90.1:+.3f}}]).
<!--/OOS-->

*App. 5. Stress periods* (P0 on every valid IS event; event P&L by leg, % of NAV). Spread variance is \(h_E^2\sigma_E^2 + h_B^2\sigma_B^2 - 2h_E h_B\,\mathrm{Cov}(r_E, r_B)\).

| Period | Events | ES leg | ZN leg | Costs | Net |
|---|---|---|---|---|---|
| {{risk_IS.stress_P0_all.0.period}} | {{risk_IS.stress_P0_all.0.events}} | {{risk_IS.stress_P0_all.0.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.0.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.0.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.0.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.1.period}} | {{risk_IS.stress_P0_all.1.events}} | {{risk_IS.stress_P0_all.1.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.1.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.1.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.1.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.2.period}} | {{risk_IS.stress_P0_all.2.events}} | {{risk_IS.stress_P0_all.2.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.2.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.2.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.2.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.3.period}} | {{risk_IS.stress_P0_all.3.events}} | {{risk_IS.stress_P0_all.3.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.3.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.3.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.3.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.4.period}} | {{risk_IS.stress_P0_all.4.events}} | {{risk_IS.stress_P0_all.4.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.4.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.4.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.4.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.5.period}} | {{risk_IS.stress_P0_all.5.events}} | {{risk_IS.stress_P0_all.5.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.5.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.5.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.5.net_pct:+.2f}}% |

*App. 6. Event path and impact.* Margins used (CME, 2026-10-03): ES $26,164, ZN $1,875 per contract. ES settled 16:14:30–16:15 ET before 2020-10-26.

<figure><img src="reports/figures/event_path.png"><figcaption>Figure A1. Signed spread path, L−12 to F1+5, by era (event counts in parentheses; sign and dose frozen at L−12).</figcaption></figure>
<figure><img src="reports/figures/impact.png"><figcaption>Figure A2. PG net Sharpe vs NAV under square-root impact.</figcaption></figure>

Full audit (data coverage, decision-date shifts, action ledger, Backtrader reconciliation, inference calibration) and every amendment: `AMENDMENTS.md`, `reports/`.

*App. 7. Additional diagnostics.*

<figure><img src="reports/figures/key_y_vs_a.png"><figcaption>Figure A3. Remaining return against pre-entry progress (IS); bin means with 90% intervals.</figcaption></figure>

<figure><img src="reports/figures/pg_oos_events.png"><figcaption>Figure A4. PG net P&amp;L by OOS event. Grey ticks denote no trade; two events carry the result.</figcaption></figure>
