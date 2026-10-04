# Why the remaining-return gate failed

Exploratory analysis of the already-open in-sample data, 2015-10 through 2024-09. Results are descriptive unless explicitly identified otherwise. All 108 evaluation months remain in Sharpe denominators; there are 104 baseline-tradable events and 69 selected events. No out-of-sample data was read or unlocked, and frozen files were verified unchanged.

## The main failure was selection, not implementation or fees

| Gate decision | Events | Net P&L | Gross P&L | Average dose | Mean realized Y | Mean forecast |
|---|---:|---:|---:|---:|---:|---:|
| Kept | 69 | -$36,979 | -$9,847 | 0.671 | -0.041 | +0.104 |
| Rejected | 35 | +$220,504 | +$250,909 | 1.256 | +0.144 | -0.048 |

The rejected trades explain the full $220,504 gap between PG and P0. The gate saved $30,406 of costs but gave up $250,909 of gross P&L. PG was already negative before costs. Integer rounding helped PG by $5,859 versus its fractional-contract accounting; it did not cause the loss. No evaluated trade hit the notional cap.

The gate kept 30 winners and 39 losers, and rejected 16 winners and 19 losers. Its problem is not simply an abnormally low hit rate: it missed important positive payoffs while continuing to take substantial negative payoffs.

## The gate learned an economically opposite dose slope

The dose coefficient was **negative at every one of the 104 tradable decisions**. It started at -0.355 and ended at -0.027. The hypothesis was that a larger estimated rebalancing need should increase remaining return, but the fitted rule systematically penalized larger needs. It rejected 13 of the 14 events with dose above 1.5. Rejected events carried average intended dollar risk of $54,395 versus $29,076 for kept events.

This was not a coding sign error: it follows from the unrestricted regression. The first 60 training events estimated a negative dose slope; the expanding fit retained that sign. In the later tradable evaluation segment, a descriptive regression estimates a positive dose slope of +0.096, although its uncertainty includes zero. The training relationship did not translate into useful forecast ranking.

The progress coefficient was negative in 88.5% of decisions but positive in 11.5%. Its 2018 yearly average was positive. Thus the actual adaptive model did not uniformly implement the economic premise about prior progress either.

Crucially, **the progress feature itself improved the dose-only model**. PG beat PD by $80,958: adding progress admitted three trades worth +$79,048 and removed sixteen trades worth -$1,909. The nineteen trades that both PG and PD rejected earned +$222,413. Blaming the novel progress variable alone would misdiagnose the result.

## Forecasts contain little demonstrated information

Across 104 tradable events, forecast/realized-Y correlation is -0.067; Spearman correlation is -0.020. Predictive R-squared against the expanding historical-mean forecast is -1.73%, so the two-feature regression forecast is slightly worse than predicting the past mean. Its forecast standard deviation is 0.102 versus 0.971 for realized Y.

Across **all 108 valid events**, including the four that round below one contract, correlation is -0.147. Across only the 69 selected events it is +0.014. These are different populations, not inconsistent computations.

An approximate conversion of forecasts into dollars predicted +$137,039 net on kept trades and -$150,037 on rejected trades. Actual figures were -$36,979 and +$220,504. The forecast dollar conversion uses target risk times predicted log-spread Y minus costs; actual contract-dollar accounting differs slightly.

A further diagnostic uses HAC lag-3 coefficient covariance at each historical decision. The median standard error of the forecast **mean** is 0.126, approximately ten times the median cost hurdle of 0.0128. In 103 of 104 decisions, a descriptive 90% confidence interval for that mean crosses the cost hurdle. The point-estimate gate makes hard yes/no decisions mostly where parameter uncertainty overwhelms the proposed edge. This diagnostic is not a new registered significance test or a proposed confidence-bound strategy.

## Pooling directions hides economically important asymmetry

| Direction and decision | Events | Net P&L |
|---|---:|---:|
| Long ES, kept | 24 | +$121,061 |
| Long ES, rejected | 8 | +$273,133 |
| Short ES, kept | 45 | -$158,040 |
| Short ES, rejected | 27 | -$52,629 |

Avoiding 27 short-ES events helped by $52,629, but skipping eight long-ES events cost $273,133. The original model treats both directions as draws from the same response surface. Direction conditioning is a plausible explanation to investigate, although ordinary stock exposure or reversal can explain directional performance without validating fund-flow causation.

The normalized target and final dollars also differ. Rejected short-ES events have positive mean Y (+0.131) but negative total dollars (-$52,629), because losses and wins occurred at different risk allocations. Without caps, target dollar risk is proportional to dose. Fitting unweighted normalized Y is sensible if its conditional mean is correctly specified, but it does not directly optimize portfolio-dollar performance under misspecification. This is a modeling limitation, not an accounting bug.

## Failure is persistent; positive baselines are concentrated

PG's Sharpe disadvantage remains negative after deleting **any single trade** (range -0.264 to -0.053) or **any single calendar year** (range -0.263 to -0.039). No one bad event or year explains away the gate's underperformance. This deletion exercise holds the original decisions fixed; it does not refit a counterfactual strategy with the event removed.

But P0's gain is fragile too. November 2021 earned $176,000, leaving only $7,525 total P0 profit if removed. Deleting P0's top three winners yields -$287,414. PG's negative sign also changes if its worst event is deleted, so the sign of its absolute P&L alone is less robust than its relative underperformance.

The gate's failure was concentrated in 2015-2020: it kept -$126,671 and rejected +$243,519. In 2021-2024 it kept +$89,693 and rejected -$23,015. Therefore “the recent effect faded” does **not** by itself explain why PG lost overall.

## Six bounded model diagnostics

These six ablations were listed before inspecting their outcomes in this analysis. They reuse the original common evaluation segment, costs, signals, and position sizes, and refit only on completed historical events. All remain exploratory because their family was chosen after the original result.

| Diagnostic | Trades | Net P&L | Sharpe | Sharpe, doubled costs |
|---|---:|---:|---:|---:|
| Historical-mean forecast | 99 | +$164,784 | 0.120 | 0.081 |
| Separate historical means by direction | 33 | +$337,844 | 0.404 | 0.391 |
| Add direction to original OLS | 44 | +$288,413 | 0.357 | 0.339 |
| Fit original OLS on trailing 60 events | 52 | -$155,878 | -0.175 | -0.205 |
| Constrain dose >= 0 and progress <= 0 | 88 | +$32,152 | 0.025 | -0.013 |
| Remove progress, equivalent to PD | 82 | -$117,936 | -0.122 | -0.156 |

Changing the lookback or forcing the expected signs does not recover a strong strategy. Direction-aware models are more promising descriptively, but their original-Y forecast correlations are only +0.074 and +0.036. Their apparent improvement may largely be a directional-exposure choice and needs independent testing. The direction-mean rule requires at least twenty same-direction observations; otherwise it uses the overall historical mean.

## A bounded follow-up pattern: price still moving against the intended trade

The following partition was requested **after inspecting the attribution**. A<0 means that, during the three-session progress window, the spread was still moving against the intended rebalance trade. It does not require fitting a slope.

| Month-end group | Trades | Mean Y | Net P&L | Sharpe | P&L after removing best winner |
|---|---:|---:|---:|---:|---:|
| A<0 | 59 | +0.129 | +$444,473 | 0.405 | +$268,473 |
| A>=0 | 45 | -0.120 | -$260,948 | -0.322 | -$395,381 |
| Long ES and A<0 | 19 | +0.300 | +$347,028 | 0.445 | +$186,523 |
| Long ES and A>=0 | 13 | +0.093 | +$47,166 | 0.191 | -$9,219 |
| Short ES and A<0 | 40 | +0.047 | +$97,444 | 0.126 | -$78,556 |
| Short ES and A>=0 | 32 | -0.207 | -$308,113 | -0.400 | -$442,547 |

The month-end A<0 group is positive in both broad eras: +$127,378 through 2020 and +$317,094 in 2021-2024. Recent A>=0 events lose $250,417. The long-ES/A<0 group is positive in both eras as well, but has only nineteen observations and loses money after deleting its three largest wins. Across all A<0 events, removing the three best leaves only +$1,501.

The analogous **mid-month** A<0 condition loses $338,159 (Sharpe -0.313); long ES/A<0 loses $84,953 (Sharpe -0.122). This is a potentially informative calendar distinction. It is not a causal finding or a validated nonlinear gate: midpoint and month-end observations differ in drift lookback, distributions, and trading conditions. The original linear confirmatory tests still fail.

This partition gives a concrete research question: does a calendar-specific reversal effect exist when price is still moving against the rebalancing direction, and does a pooled negative dose coefficient suppress it? It does not justify promoting the observed winning subgroup to an established strategy.

## Reproduction and files

Run `.venv/bin/python research/2026-10-03-failure-analysis/gate_attribution/analyze.py` from the repository root. The script reads IS-filtered settlement parquet scans, reconstructs the frozen ledgers, checks the saved registered Sharpe values, and verifies hashes of results, trials, hypothesis, and frozen configuration before and after.

- `analysis.json`: complete numerical results and all ablations.
- `event_ledger.csv`: all 108 evaluated events, features, predictions, decisions, and outcomes.
- `all_is_event_features.csv`: IS training plus evaluated event features.
- `forecast_uncertainty.csv`: per-decision mean forecast uncertainty.
- `leave_one_event_out.csv`: every single-event deletion.
- `progress_sign_month_end.csv` and `progress_sign_mid_month.csv`: follow-up partition source rows.

No new test is being passed off as confirmatory, no original verdict is overwritten, and no OOS return is used.
