# Hypothesis and pre-registered protocol (final)

*Commit and push this file before any price data is loaded for analysis or any backtest is run; the commit SHA and push time are the evidence. After that, `AMENDMENTS.md` may record only bug fixes and data facts. The constants, variants and tests below do not change. Out-of-sample data is loaded once, after the `freeze-final` tag.*

## 1. Hypothesis (edge source: structural constraint; we trade ahead of predictable flow and are paid for bearing spread risk)

**We expect the ES−ZN spread to move against the month-to-date winner over the last week of the month, scaled by the 60/40 allocation drift. We also expect this remaining move to be smaller when the spread has already moved in that direction before we enter.**

- **Why the flow exists:** balanced, pension and target-date funds restore fixed stock/bond weights on set dates and at set benchmark clocks.
- **What the trade is:** we trade in the direction of that adjustment, and only when the forecast remaining return exceeds round-trip cost.

| | |
|---|---|
| **Accounting** | With no intervening flows, stock-weight drift is D = 0.24(R_E − R_B)/(1 + 0.6R_E + 0.4R_B). The required stock purchase is 0.24·V₀(R_B − R_E). This is a hypothetical fund's demand, not observed orders. |
| **Who is on the other side** | Mechanism: calendar rebalancers and their overlay managers, who care about weights at a clock more than about price. At our fill: liquidity suppliers and earlier anticipators. |
| **Why it persists** | Not secrecy. The flow is estimated publicly every month and the effect is published (Harvey-Mazzoleni-Melone 2025, NBER w33554). Committees set the rules. Holding the trade means about 12 noisy, crash-exposed bets a year. Risk capital limits arbitrage, not knowledge. |
| **If true, we should see** | (H1) remaining return rises with dose at a tradable lag; (H2) pre-entry progress predicts less remaining return at month-end than it does at matched non-month-end pseudo-events. |
| **It fails if** | Any of the following: IS dose slope b ≤ 0; c_E ≥ 0, in which case the progress filter is ordinary reversal or nothing; the gate does not beat an exposure-matched control; net Sharpe at 2× costs ≤ 0; or the binding leg cannot fill one integer lot at 1% of execution-window volume. |

**Claim boundary.** Rebalancing pressure, anticipation, and the 2021 benchmark clock are prior art (HMM 2025; Brøgger 2021; Pegoraro-Sammon-Shim 2026; Bessembinder et al. 2016; NY Fed 2026; NISA 2021). We claim one thing: a pre-registered, executable ES/ZN test of whether conditioning on pre-entry price progress improves a known allocation-flow trade after costs. Controls separate the result from ordinary reversal and from simply taking less risk. We make no secrecy, first-ever or causal-identification claims.

## 2. Data, clocks, fills

- **Sources:** Databento GLBX.MDP3 `definition` and `statistics` (final settlements, deduplicated by reference date; open interest; cleared volume) for all ES and ZN outright contracts. ES/ZN `bbo-1m` on event and pseudo-event days only. Ken French daily factors. Raw licensed data is never committed.
- **Sessions:** CME trade dates on which both ES and ZN publish a final settlement and XNYS is open. L is the month's last such session, F1 is the next month's first, and L−k counts back over sessions.
- **Contracts:**
  - ES: the highest-open-interest outright at L−8.
  - ZN: the nearest outright whose first position day is after F1.
  - One contract per leg per event: no mid-event roll, no cross-contract price ratio.
- **A settlement is a mark, not a fill.**
  - The primary row uses settlements: ZN at 15:00 ET; ES at 16:15 ET before 2020-10-26 and 16:00 ET after.
  - Executable row: both legs at the bbo-1m bid/ask at 15:59 ET. The bar-boundary convention is verified on a known print before use.

## 3. Frozen definitions

| Item | Definition |
|---|---|
| Spread return | X = r_ES − r_ZN (1:1 notional, log, within-contract), summed over a window. |
| Drift at L−5 | D from cumulative within-contract returns since the previous L. |
| Volatility | σ̂ = EWMA(λ = 0.94) sd of daily X, using data through L−5. |
| Dose | z = D/(0.24·σ̂·√n), with n = sessions since the previous L. dose = min(|z|, 2). s = −sign(D). |
| Progress | A = s·X(L−8 → L−5)/(σ̂·√3). |
| Outcome | Y = s·X(L−4 → F1)/(σ̂·√5). |
| Position (P1) | Decide at L−5; enter at L−4; exit at F1. Direction s, 1:1 notional legs. Leg notional = (dose/2)·κ·NAV/(σ̂·√5), with κ = 0.03/√12; integer contracts; reference NAV $10M. |
| Costs per contract per side | Half-spread (ES $6.25; ZN $7.8125) + $2.50 fee. Reported at 1× and 2×, plus a square-root-impact sensitivity row (Y = 1). |
| Gate (PRIMARY) | Ŷ = â + b̂·dose + ĉ·A from OLS on completed past events only. Trade iff Ŷ > C, where C is the round-trip cost in units of position risk; otherwise flat. Never reverse. |
| Gate fitting | Expanding window, at least 60 events. Coefficients are frozen at the end of IS for OOS. |
| Pseudo-events | One per month, anchored at M = L−14: progress M−3 → M, enter M+1, exit M+6 (= L−8). Same formulas with drift since the previous L. No overlap with event windows. |
| Inference | Month-block bootstrap (block 3, 9,999 draws, seed 20261003), validated first on synthetic AR(1)-GARCH(1,1)-t5 data at nominal size. Rademacher wild bootstrap is the fallback; Newey-West(3) is a sensitivity. |
| Samples | IS = 2010-06-07 → 2024-10-01. OOS = 2024-10-02 → last settle, opened once. The loader drops OOS dates until `freeze-final`. |

## 4. Strategy rows (N = 6, all reported)

| ID | Rule | What it tests |
|---|---|---|
| **PG (PRIMARY)** | P1 + remaining-return gate | Headline strategy |
| P0 | P1, always trades | Benchmark: does the gate help? |
| PD | Gate on dose only (c ≡ 0) | Does progress add information? |
| PE | P0 scaled by PG's IS participation rate | Is the gain just less risk? |
| PX | PG with executable bid/ask fills | Is it tradable at real quotes? |
| PP | PG applied to pseudo-events | Is it ordinary reversal? |

All rows are compared on the same walk-forward IS segment (first gated event through 2024-09) and on OOS.

## 5. Statistics

- **Confirmatory (IS events, one-sided, Holm-adjusted at α = 0.05):**
  - **H1:** b > 0 in Y = a + b·dose + γ·QE + e, where QE is a quarter-end dummy.
  - **H2:** c_E < 0 in the stacked regression Y = a + a_E·ME + b·dose + b_E·ME·dose + c·A + c_E·ME·A + e, over events (ME = 1) and pseudo-events (ME = 0). The bootstrap resamples months.
  - **Power:** MDE for c_E ≈ 0.27 (80% power).
- **Trading evaluation (descriptive):** ΔSR(PG − P0), ΔSR(PG − PD) and ΔSR(PG − PE), with bootstrap CIs. Deflated Sharpe at N = 6 and at the logged prior-look count.
- **OOS (opened once):** row metrics, b_OOS and c_OOS, and the slope differences Δb and Δc with CIs. No ratios. The MDE is stated before opening. A null is reported as an upper bound.
- **Placebo and pseudo-event results are diagnostics, not exact p-values.**

## 6. Descriptive diagnostics (not tests)

1. **Event-time path:** signed path of the 1:1 spread from L−12 to F1+5, with the sign and dose frozen at L−12, by era (2010–15, 2016–20, 2021–24, and OOS). Displacement shows up as an earlier rise and a later fall; decay shows up as a total collapse.
2. **Benchmark clock:** ZN 15:00 → 16:00 ET mid return on L versus ordinary days, before and after 2021-01-14. Unconditional and signal-conditional parts are shown separately; ES (confounded by its 2020-10-26 clock move) is shown as context.
3. **Legs and direction:** ES and ZN legs, s = +1 vs s = −1, against HMM's Table 3 bond-intercept benchmark.
4. **Action-conditional ledger:** per month, forecast error × position, gross vs net, and leg contributions.

## 7. Numeric predictions (scored in the note)

1. IS b ∈ [0.02, 0.12] σ-units per unit dose, i.e. about 5–30bp per event at dose 1.
2. c_E ∈ [−0.25, 0.05], with a wide CI. H2 power is about 0.3–0.5.
3. PG trades 50–85% of IS events. ΔSR(PG − P0) ∈ [−0.10, +0.20], with a CI that spans 0.
4. P0 net Sharpe is 0.1–0.4 at 1× costs and stays > 0 at 2×. PX is within ±0.15 of PG.
5. OOS CIs cover 0; OOS power is about 0.15–0.20.
6. ZN binds capacity in the execution window. The minimum integer-lot NAV is $1–10M.
7. Realized-to-target volatility lies in [0.6, 1.5] in at least 75% of years.

## 8. Reporting and disclosure

- **Reported for IS and OOS separately, net, at 1× and 2× costs:** annualized return, volatility, Sharpe, max drawdown, turnover, worst month, skew, equity curve, and factor regression.
- **Capacity:** a scenario at 1%, 5% and 10% of execution-window volume, naming the binding leg.
- **Reproducibility:** every run is logged to `trials.jsonl`, and `python -m gqh.reproduce` rebuilds every number.
- **Prior looks:**
  - A private 2010–2022 event study on proxy data overlaps IS. Logged earlier variants number at least 29 month-end and 45 trend/vol, and that inventory is incomplete.
  - The 2024-10 → 2025-12 data was partly seen through published extensions and replications.
  - Drafts V1–V3 and independent reviews shaped this design without any new return computation.
