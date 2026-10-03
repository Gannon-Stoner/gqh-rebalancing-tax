# Paying for what is left: a pre-registered remaining-return gate on month-end 60/40 rebalancing flow in ES/ZN futures

<div class="byline">Gannon Stoner · Gator Quant Hacks 2026, Systematic Trading · repo: github.com/Gannon-Stoner/gqh-rebalancing-tax · pre-registration: tag <code>prereg-final</code> (pushed before any price data) · every number below is produced by <code>python -m gqh.reproduce</code></div>

## Summary

Balanced funds must sell the asset that outperformed during the month and buy the laggard, and they do it on a calendar. That flow is public knowledge, so the question that matters to a trader is not *whether* it moves prices but **how much of the move is still left when we can trade**. We pre-registered one rule that answers it. At the L−5 settlement we forecast the remaining ES−ZN spread return from two inputs: the size of the rebalancing need (dose) and how far the spread has already moved our way (progress). We trade at L−4 only if the forecast beats round-trip cost, and we exit on the first session of the new month. [[VERDICT: one-sentence IS result for PG vs P0, H1/H2 and the OOS read]]

## 1. Economic hypothesis

**Mechanism.** A 60/40 fund that starts the month with $100 and sees stocks rise 10% while bonds are flat ends with 62.3% in stocks, so it must sell $2.40 of stocks and buy $2.40 of bonds to get back to target. In general the stock-weight drift is D = 0.24(R_E − R_B)/(1 + 0.6R_E + 0.4R_B), and the required stock trade is 0.24·V₀(R_B − R_E). This is accounting, not a forecast. It is the demand of a hypothetical fund; we observe no orders.

**Counterparty and persistence.** The other side of our trade at the fill is liquidity suppliers and earlier anticipators; the flow itself comes from calendar rebalancers and their overlay managers, who care about weights at a clock more than about price. The effect is published (Harvey, Mazzoleni and Melone 2025, NBER w33554) and estimated every month by sell-side desks. It persists because of governance and scarce risk capital, not secrecy: committees set rebalancing rules, and harvesting the effect means about twelve noisy, crash-exposed bets a year.

**Our claim, and only this one.** Rebalancing pressure and its anticipation are prior art (HMM 2025; Brøgger 2021; Bessembinder et al. 2016). We claim a pre-registered, executable test of whether conditioning on pre-entry progress improves a known allocation-flow trade after costs. Two forces should shrink what is left after early progress: anticipators already pushed the price, and the move itself shrinks the drift that funds must trade. Two others predict the opposite: news with momentum and persistent orders. Ordinary short-term reversal could mimic the first pair, so the design includes a mid-month placebo.

**Kill conditions (pre-registered).** IS dose slope b ≤ 0; c_E ≥ 0 (progress is ordinary reversal or nothing); the gate does not beat an exposure-matched control; net Sharpe ≤ 0 at 2× costs; or the binding leg cannot fill one lot at 1% of execution-window volume.

## 2. Data and universe

- **Source.** Databento GLBX.MDP3 for ES and ZN, all outright quarterly contracts: `definition`, `statistics` (final settlements, open interest, volume), `bbo-1m` and `ohlcv-1m`. Ken French daily factors. In sample (IS) 2010-06-07 to 2024-10-01; out of sample (OOS) from 2024-10-02, loaded once after the `freeze-final` tag. Raw licensed data is never committed; every file is recorded with its SHA-256.
- **Sessions.** CME trade dates on which both ES and ZN publish a settlement and NYSE is open ({{sample_counts.IS.events}} IS months, {{sample_counts.IS.valid_events}} valid events, {{sample_counts.IS.valid_pseudos}} valid pseudo-events). L is the month's last such session and F1 the next month's first; L−k counts back over sessions. Decision dates are recomputed on the calendar a trader knew at the time (Hurricane Sandy, and four months with missing settlements on vendor-degraded days).
- **Contracts.** ES: highest open interest at L−8. ZN: nearest contract whose first position day is after F1. One contract per leg per event, so no roll ever enters a return. Futures carry no survivorship bias.
- **Data facts found in the audit (amendment A14).** Before CME's MDP 3.0 feed (2010–2015), the vendor's settlement records carry no "final" flag, and open interest is not published at all. Settlements use the frozen "last record per contract and day" rule, which matches the flagged final on 99.75–100% of contract-days where both exist. Where open interest is missing, contracts are ranked by traded volume; that picks the same contract as open interest on 98–99% of days and on 106/106 event dates where both exist.

## 3. Methodology (frozen before any backtest)

<figure><img src="reports/figures/timeline.png"><figcaption>Figure 1. One month. Pseudo-events (mid-month placebo) use the same formulas twelve sessions earlier. Returns between the decision (L−5) and the fill (L−4) never count.</figcaption></figure>

- **Signal at L−5.** Drift D from month-to-date within-contract returns. σ̂ is a zero-mean EWMA (λ = 0.94) of the daily 1:1 spread return X = r_ES − r_ZN. Dose = min(|z|, 2) with z = D/(0.24·σ̂·√n), n sessions since the previous L. Direction s = −sign(D): trade with the coming rebalancing. Progress A = s·X(L−8→L−5)/(σ̂√3). Outcome Y = s·X(L−4→F1)/(σ̂√5).
- **Gate.** Ŷ = â + b̂·dose + ĉ·A from OLS on completed past events only (exit before the current decision), at least 60 of them, coefficients frozen at the end of IS for OOS. Trade iff Ŷ > C, the round-trip cost in units of position risk; otherwise flat; never reverse.
- **Position and costs.** Equal-notional legs, leg notional = (dose/2)·κ·NAV/(σ̂√5) with κ = 3%/√12 (a full-dose event risks about 0.87% of NAV over five days), caps 0.75×NAV per leg and 1.5× gross, whole contracts at a $10M reference NAV. Entry at the L−4 settlement, exit at the F1 settlement. Per contract per side: half-spread (ES $6.25, ZN $7.81) + $2.50 fee; every row is also reported at 2×.
- **Six rows (all reported, N = 6).** **PG** (primary: gate) · **P0** (always trade) · **PD** (gate on dose only, c ≡ 0: does progress add anything?) · **PE** (P0 scaled to PG's participation: is the gain just less risk?) · **PX** (PG filled at the 15:59 ET bid/ask: real quotes) · **PP** (PG on mid-month pseudo-events: ordinary reversal?). All rows share one walk-forward segment, from {{segment_start}} to 2024-09.
- **Confirmatory tests (Holm, one-sided, α = 0.05).** H1: b > 0 in Y = a + b·dose + γ·QE on IS events. H2: c_E < 0 in the stacked regression of events (ME = 1) and pseudo-events (ME = 0) with ME interactions; progress should matter *more* at month-end than mid-month.
- **Inference, calibrated before use.** Studentized circular month-block bootstrap (block 3, 9,999 draws, seed 20261003). On 500 synthetic AR(1)-GARCH(1,1)-t₅ histories per null, run through the real signal code, its size is {{calibration.scenarios.h2_reversal.H2_month_block.rate:.1%}}–{{calibration.scenarios.base.H1_month_block.rate:.1%}} at a nominal 5% (registered band 3–7%). Power is modest and stated up front: H1 rejects {{calibration.scenarios.h1_power.H1_month_block.rate:.0%}} of the time at b = 0.05 and {{calibration.scenarios.h1_power_hi.H1_month_block.rate:.0%}} at b = 0.12; H2 rejects {{calibration.scenarios.h2_power.H2_month_block.rate:.0%}} at c_E = −0.27 (80%-power MDE ≈ 0.37). Ordinary reversal alone makes H1 reject {{calibration.scenarios.h2_reversal.H1_month_block.rate:.1%}} of the time, which is why H2 and PP exist.
- **Two engines.** The frozen engine produces every number. As an independent check, every settlement-row trade is replayed in Backtrader (the engine of the track's Webull starter kit) on the same Databento settlements, sizes and costs: {{backtrader_replay.PG@1x.matched}} of {{backtrader_replay.PG@1x.events}} PG trades and {{backtrader_replay.P0@1x.matched}} of {{backtrader_replay.P0@1x.events}} P0 trades match the engine to within $0.01 at 1× costs ({{backtrader_replay.PG@2x.matched}}/{{backtrader_replay.PG@2x.events}} and {{backtrader_replay.P0@2x.matched}}/{{backtrader_replay.P0@2x.events}} at 2×).


## 4. Results

### In sample ({{rows_IS.months.0}} to {{rows_IS.months.1}}, walk-forward segment, net of costs, % of a $10M reference NAV)

| Row | Trades | Return/yr | Vol/yr | Sharpe 1× | Sharpe 2× | Max DD | Worst month | DSR (N=6) |
|---|---|---|---|---|---|---|---|---|
| PG | {{rows_IS.rows.PG@1x.trades}} | {{rows_IS.rows.PG@1x.ann_return:.2%}} | {{rows_IS.rows.PG@1x.ann_vol:.2%}} | {{rows_IS.rows.PG@1x.sharpe:.2f}} | {{rows_IS.rows.PG@2x.sharpe:.2f}} | {{rows_IS.rows.PG@1x.max_drawdown:.2%}} | {{rows_IS.rows.PG@1x.worst_month:.2%}} | {{rows_IS.rows.PG@1x.dsr.registered_6:.2f}} |
| P0 | {{rows_IS.rows.P0@1x.trades}} | {{rows_IS.rows.P0@1x.ann_return:.2%}} | {{rows_IS.rows.P0@1x.ann_vol:.2%}} | {{rows_IS.rows.P0@1x.sharpe:.2f}} | {{rows_IS.rows.P0@2x.sharpe:.2f}} | {{rows_IS.rows.P0@1x.max_drawdown:.2%}} | {{rows_IS.rows.P0@1x.worst_month:.2%}} | {{rows_IS.rows.P0@1x.dsr.registered_6:.2f}} |
| PD | {{rows_IS.rows.PD@1x.trades}} | {{rows_IS.rows.PD@1x.ann_return:.2%}} | {{rows_IS.rows.PD@1x.ann_vol:.2%}} | {{rows_IS.rows.PD@1x.sharpe:.2f}} | {{rows_IS.rows.PD@2x.sharpe:.2f}} | {{rows_IS.rows.PD@1x.max_drawdown:.2%}} | {{rows_IS.rows.PD@1x.worst_month:.2%}} | {{rows_IS.rows.PD@1x.dsr.registered_6:.2f}} |
| PE | {{rows_IS.rows.PE@1x.trades}} | {{rows_IS.rows.PE@1x.ann_return:.2%}} | {{rows_IS.rows.PE@1x.ann_vol:.2%}} | {{rows_IS.rows.PE@1x.sharpe:.2f}} | {{rows_IS.rows.PE@2x.sharpe:.2f}} | {{rows_IS.rows.PE@1x.max_drawdown:.2%}} | {{rows_IS.rows.PE@1x.worst_month:.2%}} | {{rows_IS.rows.PE@1x.dsr.registered_6:.2f}} |
| PX | {{rows_IS.rows.PX@1x.trades}} | {{rows_IS.rows.PX@1x.ann_return:.2%}} | {{rows_IS.rows.PX@1x.ann_vol:.2%}} | {{rows_IS.rows.PX@1x.sharpe:.2f}} | {{rows_IS.rows.PX@2x.sharpe:.2f}} | {{rows_IS.rows.PX@1x.max_drawdown:.2%}} | {{rows_IS.rows.PX@1x.worst_month:.2%}} | {{rows_IS.rows.PX@1x.dsr.registered_6:.2f}} |
| PP | {{rows_IS.rows.PP@1x.trades}} | {{rows_IS.rows.PP@1x.ann_return:.2%}} | {{rows_IS.rows.PP@1x.ann_vol:.2%}} | {{rows_IS.rows.PP@1x.sharpe:.2f}} | {{rows_IS.rows.PP@2x.sharpe:.2f}} | {{rows_IS.rows.PP@1x.max_drawdown:.2%}} | {{rows_IS.rows.PP@1x.worst_month:.2%}} | {{rows_IS.rows.PP@1x.dsr.registered_6:.2f}} |

<div class="small">Returns are monthly (zero in flat months), annualized, uncompounded on a fixed NAV. DSR = deflated Sharpe ratio at the 6 registered rows; at the logged prior-look counts (35 and 80) PG's DSR is {{rows_IS.rows.PG@1x.dsr.month_end_family_35:.2f}} and {{rows_IS.rows.PG@1x.dsr.all_logged_80:.2f}}. PE trades every P0 event at p = {{pe_participation_p:.2f}} of the size.</div>

**Does the gate help?** ΔSR (annualized, 90% month-block CI): PG − P0 {{rows_IS.delta_sharpe.PG-P0@1x.estimate:+.2f}} [{{rows_IS.delta_sharpe.PG-P0@1x.ci90.0:+.2f}}, {{rows_IS.delta_sharpe.PG-P0@1x.ci90.1:+.2f}}]; PG − PD {{rows_IS.delta_sharpe.PG-PD@1x.estimate:+.2f}} [{{rows_IS.delta_sharpe.PG-PD@1x.ci90.0:+.2f}}, {{rows_IS.delta_sharpe.PG-PD@1x.ci90.1:+.2f}}]; PG − PE {{rows_IS.delta_sharpe.PG-PE@1x.estimate:+.2f}} [{{rows_IS.delta_sharpe.PG-PE@1x.ci90.0:+.2f}}, {{rows_IS.delta_sharpe.PG-PE@1x.ci90.1:+.2f}}]. [[VERDICT: interpretation of the three contrasts]]

**Confirmatory tests.** H1 (dose slope b > 0): b̂ = {{confirmatory.H1.month_block.estimate:+.3f}} σ per unit dose, 90% CI [{{confirmatory.H1.month_block.ci90.0:+.3f}}, {{confirmatory.H1.month_block.ci90.1:+.3f}}], one-sided p = {{confirmatory.H1.month_block.p_one_sided:.3f}} (Holm {{confirmatory.holm.H1:.3f}}). H2 (month-end progress slope below mid-month, c_E < 0): ĉ_E = {{confirmatory.H2.month_block.estimate:+.3f}}, 90% CI [{{confirmatory.H2.month_block.ci90.0:+.3f}}, {{confirmatory.H2.month_block.ci90.1:+.3f}}], p = {{confirmatory.H2.month_block.p_one_sided:.3f}} (Holm {{confirmatory.holm.H2:.3f}}). Wild-bootstrap and Newey-West(3) p-values: H1 {{confirmatory.H1.wild.p_one_sided:.3f}} / {{confirmatory.H1.newey_west.p_one_sided:.3f}}; H2 {{confirmatory.H2.wild.p_one_sided:.3f}} / {{confirmatory.H2.newey_west.p_one_sided:.3f}}. [[VERDICT: what H1/H2 say, with the power caveat]]

<div class="row">
<figure><img src="reports/figures/key_y_vs_a.png"><figcaption>Figure 2. The thesis in one picture: remaining return against pre-entry progress, month-end events vs mid-month pseudo-events (IS).</figcaption></figure>
<figure><img src="reports/figures/equity_is.png"><figcaption>Figure 3. Cumulative net return of the six rows at 1× costs (IS walk-forward segment).</figcaption></figure>
</div>

<!--OOS-->
### Out of sample ({{rows_OOS.months.0}} to {{rows_OOS.months.1}}, opened once after the `freeze-final` tag)

| Row | Trades | Return/yr | Vol/yr | Sharpe 1× | Sharpe 2× | Max DD |
|---|---|---|---|---|---|---|
| PG | {{rows_OOS.rows.PG@1x.trades}} | {{rows_OOS.rows.PG@1x.ann_return:.2%}} | {{rows_OOS.rows.PG@1x.ann_vol:.2%}} | {{rows_OOS.rows.PG@1x.sharpe:.2f}} | {{rows_OOS.rows.PG@2x.sharpe:.2f}} | {{rows_OOS.rows.PG@1x.max_drawdown:.2%}} |
| P0 | {{rows_OOS.rows.P0@1x.trades}} | {{rows_OOS.rows.P0@1x.ann_return:.2%}} | {{rows_OOS.rows.P0@1x.ann_vol:.2%}} | {{rows_OOS.rows.P0@1x.sharpe:.2f}} | {{rows_OOS.rows.P0@2x.sharpe:.2f}} | {{rows_OOS.rows.P0@1x.max_drawdown:.2%}} |
| PD | {{rows_OOS.rows.PD@1x.trades}} | {{rows_OOS.rows.PD@1x.ann_return:.2%}} | {{rows_OOS.rows.PD@1x.ann_vol:.2%}} | {{rows_OOS.rows.PD@1x.sharpe:.2f}} | {{rows_OOS.rows.PD@2x.sharpe:.2f}} | {{rows_OOS.rows.PD@1x.max_drawdown:.2%}} |
| PE | {{rows_OOS.rows.PE@1x.trades}} | {{rows_OOS.rows.PE@1x.ann_return:.2%}} | {{rows_OOS.rows.PE@1x.ann_vol:.2%}} | {{rows_OOS.rows.PE@1x.sharpe:.2f}} | {{rows_OOS.rows.PE@2x.sharpe:.2f}} | {{rows_OOS.rows.PE@1x.max_drawdown:.2%}} |
| PX | {{rows_OOS.rows.PX@1x.trades}} | {{rows_OOS.rows.PX@1x.ann_return:.2%}} | {{rows_OOS.rows.PX@1x.ann_vol:.2%}} | {{rows_OOS.rows.PX@1x.sharpe:.2f}} | {{rows_OOS.rows.PX@2x.sharpe:.2f}} | {{rows_OOS.rows.PX@1x.max_drawdown:.2%}} |
| PP | {{rows_OOS.rows.PP@1x.trades}} | {{rows_OOS.rows.PP@1x.ann_return:.2%}} | {{rows_OOS.rows.PP@1x.ann_vol:.2%}} | {{rows_OOS.rows.PP@1x.sharpe:.2f}} | {{rows_OOS.rows.PP@2x.sharpe:.2f}} | {{rows_OOS.rows.PP@1x.max_drawdown:.2%}} |

Slopes with the frozen model: b_OOS = {{oos_slopes.b.OOS:+.3f}} (Δb = {{oos_slopes.b.delta:+.3f}}, 90% CI [{{oos_slopes.b.delta_ci90.0:+.3f}}, {{oos_slopes.b.delta_ci90.1:+.3f}}]); c_E,OOS = {{oos_slopes.c_E.OOS:+.3f}} (Δc = {{oos_slopes.c_E.delta:+.3f}}, [{{oos_slopes.c_E.delta_ci90.0:+.3f}}, {{oos_slopes.c_E.delta_ci90.1:+.3f}}]). [[VERDICT: OOS read, as an upper bound if null]]
<!--/OOS-->

## 5. Risk management

All rules were fixed before the backtest and apply identically to every row. Size scales with dose; a full-dose event targets five-day risk of κ = 0.87% of NAV; legs are capped at 0.75×NAV and gross at 1.5×; size is set once at entry and never cut mid-event. We disclose that choice rather than add a stop: a 2σ intra-event stop, run only as a stress row, would have stopped {{risk_IS.PG.stop_2sigma_stress.stopped_events}} PG events and changed net P&L from {{risk_IS.PG.stop_2sigma_stress.net_without_stop:,.0f}} to {{risk_IS.PG.stop_2sigma_stress.net_with_stop:,.0f}} USD.

**Both legs can lose at once.** Spread variance is h_E²σ_E² + h_B²σ_B² − 2h_E h_B Cov(r_E, r_B); long ES / short ZN loses on both legs when stocks fall while bonds rally, and the 2022 positive stock-bond correlation removes the usual hedge. Stress periods for the underlying trade (P0 on every valid IS event, since all rows are flat before the walk-forward segment; event P&L by leg, % of NAV):

| Period | Events | ES leg | ZN leg | Costs | Net |
|---|---|---|---|---|---|
| {{risk_IS.stress_P0_all.0.period}} | {{risk_IS.stress_P0_all.0.events}} | {{risk_IS.stress_P0_all.0.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.0.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.0.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.0.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.1.period}} | {{risk_IS.stress_P0_all.1.events}} | {{risk_IS.stress_P0_all.1.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.1.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.1.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.1.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.2.period}} | {{risk_IS.stress_P0_all.2.events}} | {{risk_IS.stress_P0_all.2.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.2.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.2.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.2.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.3.period}} | {{risk_IS.stress_P0_all.3.events}} | {{risk_IS.stress_P0_all.3.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.3.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.3.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.3.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.4.period}} | {{risk_IS.stress_P0_all.4.events}} | {{risk_IS.stress_P0_all.4.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.4.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.4.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.4.net_pct:+.2f}}% |
| {{risk_IS.stress_P0_all.5.period}} | {{risk_IS.stress_P0_all.5.events}} | {{risk_IS.stress_P0_all.5.es_pct:+.2f}}% | {{risk_IS.stress_P0_all.5.zn_pct:+.2f}}% | {{risk_IS.stress_P0_all.5.cost_pct:.2f}}% | {{risk_IS.stress_P0_all.5.net_pct:+.2f}}% |

**Risk diagnostics (PG, IS).** P(−7.5% drawdown within 36 months) = {{risk_IS.PG.p_drawdown_7p5_in_36m:.1%}} (month-block bootstrap). Months of data needed for t = 2 at the IS Sharpe: {{risk_IS.PG.months_to_t2:,.0f}}, which quantifies "risk capital limits arbitrage". Realized-to-target risk lies in [0.6, 1.5] in {{rows_IS.realized_to_target_PG_share_in_band:.0%}} of years. Factor regression of event returns on Mkt-RF, SMB, HML, Mom and the ZN return over each holding window: alpha {{risk_IS.PG.factor_regression.coef.alpha:+.4f}} per event (t = {{risk_IS.PG.factor_regression.t.alpha:.2f}}), market loading {{risk_IS.PG.factor_regression.coef.Mkt-RF:+.3f}} (t = {{risk_IS.PG.factor_regression.t.Mkt-RF:.2f}}), ZN loading {{risk_IS.PG.factor_regression.coef.ZN:+.3f}} (t = {{risk_IS.PG.factor_regression.t.ZN:.2f}}), R² {{risk_IS.PG.factor_regression.r2:.2f}}. Capital: at CME maintenance margins (2026-10-03: ES $26,164, ZN $1,875 per contract) margin-to-equity is {{risk_IS.PG.margin.margin_to_equity_median:.1%}} at the median event ({{risk_IS.PG.margin.margin_to_equity_max:.1%}} at the largest); the worst one-day variation-margin draw was {{risk_IS.PG.margin.worst_daily_vm_pct:+.2f}}% of NAV. **Governance (described, not backtested):** pause if 24-event net P&L falls below −2σ of its forecast or OOS slopes signal decay; resume only after documented review; never change parameters after a loss.

## 6. Liquidity and capital

**Execution.** Settlement rows assume fills at the official settlement marks (ZN 14:59–15:00 ET; ES 15:59:30–16:00 ET, 16:14:30–16:15 before 2020-10-26). PX replaces them with the 15:59 ET bid/ask from `bbo-1m`: it buys at the ask and sells at the bid, so the spread is paid in the fill. PX Sharpe is {{rows_IS.rows.PX@1x.sharpe:.2f}} vs PG's {{rows_IS.rows.PG@1x.sharpe:.2f}}.

**Capacity (scenario, no AUM forecast).** Per event we compare contracts with the volume of each leg's execution-window minute on entry and exit days. ZN is the binding leg in {{rows_IS.capacity.PG_settle_windows.binding_share_ZN:.0%}} of events (median window volume: ES {{rows_IS.capacity.PG_settle_windows.median_window_volume.ES:,.0f}}, ZN {{rows_IS.capacity.PG_settle_windows.median_window_volume.ZN:,.0f}} contracts). Maximum NAV at 1% / 5% / 10% participation of the binding leg: ${{rows_IS.capacity.PG_settle_windows.max_nav_1pct.median:,.0f}} / ${{rows_IS.capacity.PG_settle_windows.max_nav_5pct.median:,.0f}} / ${{rows_IS.capacity.PG_settle_windows.max_nav_10pct.median:,.0f}} (median event; 10th percentile at 1%: ${{rows_IS.capacity.PG_settle_windows.max_nav_1pct.p10:,.0f}}). One lot fits within 1% of the binding leg's window volume in {{rows_IS.capacity.PG_settle_windows.lot_at_1pct_share:.0%}} of events. Turnover: {{rows_IS.rows.PG@1x.turnover:.1f}}× NAV per year (both legs, in and out).

<div class="row">
<figure><img src="reports/figures/event_path.png"><figcaption>Figure 4. Signed spread path from L−12 to F1+5 by era, sign and dose frozen at L−12 (displacement shows as an earlier rise and later fall).</figcaption></figure>
<figure><img src="reports/figures/impact.png"><figcaption>Figure 5. PG net Sharpe against NAV with square-root impact (Y = 1, σ_d and traded volume of the held contracts): where the edge is gone.</figcaption></figure>
</div>

## 7. Limitations and next steps

- **Power.** With about 170 events, H1 has at most ~20% power across the predicted effect range and H2 about 58% at c_E = −0.27. A null is reported as an upper bound, not as evidence of absence.
- **Prior looks.** A private 2010–2022 event study on proxy data overlaps IS, and we logged at least 29 earlier month-end and 45 trend/vol variants; DSR is shown at those counts. The OOS period was partly visible through published replications. Before the freeze, a masked crash-test run unintentionally revealed PG's IS trade count and the signs of PG's and P0's IS Sharpe ratios (A16); nothing was changed in response.
- **Proxies and clocks.** Pre-2015 settlements and contract ranking rely on documented vendor-data fallbacks (A14). The ES settlement clock moved in 2020 and the bond benchmark clock in 2021, which confound clock-level diagnostics.
- **No causal identification.** We forecast returns conditional on prices; we do not observe who traded.
- **Next.** Depth on the side the flow needs, fixed-order execution timing within the window, and the interaction with volatility-targeting deleveraging.

<div class="small">Appendix material, the full audit (data coverage, decision-date shifts, action-conditional ledger, Backtrader reconciliation, inference calibration) and every amendment are in the repository: <code>AMENDMENTS.md</code>, <code>reports/</code>.</div>
