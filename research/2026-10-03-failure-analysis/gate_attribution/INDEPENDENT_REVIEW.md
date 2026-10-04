# Independent review of the model and horizon follow-up

Reviewed `model_relationships/analyze.py` and `model_relationships/horizon_followup.py` without modifying them. No blocking look-ahead, index-alignment, or accounting error was found in the current IS runs.

Features use reference returns through the decision date. Each fit uses only completed events whose exits precede that decision. Scaling statistics are fitted on the training rows. The common monthly index retains flat months. The second cost scenario subtracts exactly one additional copy of round-trip cost from original net returns.

## Independent horizon reconstruction

I independently reconstructed the held-contract settlement return from entry at L-4 to L, then used the original, unstandardized `gqh.gate.gate_decisions` implementation rather than the follow-up's standardized `walk` function.

- Evaluation months: 108.
- Baseline-tradable events: 104.
- Events passing the refitted L-exit gate: **104**.
- Minimum forecast minus cost hurdle: **+0.05076895177**, October 2023.
- Minimum eligible forecast: +0.06575330306.
- Maximum eligible hurdle: +0.03440272026.
- Net P&L: **$794,478.125**.
- Annualized Sharpe: **0.6342229689**.
- Every event's P&L matches `PG_refit_exit_L_OLS_ledger.csv`.
- Independently recomputed signed contract quantities times multipliers times price differences, less costs, match every traded event's P&L.

The first historical coefficients are intercept +0.354963, dose -0.074642, progress -0.132165. The last coefficients used are intercept +0.064756, dose +0.148286, progress -0.020815. All events passing is not an accidental reuse of the P0 decisions: it follows from positive forecast margins in the refitted model.

## Qualifications and one wording error

1. `analyze.regressions` says “clustered by month” in its docstring, but actually fits HC3 heteroskedasticity-robust covariance. Its output correctly names the standard-error field `se_hc3`. This should not be described as HAC or clustered inference.
2. `bootstrap_family` takes the maximum of signed standardized centered means, not the maximum absolute value. It is a one-sided positive-return family adjustment, consistent with its `p_positive` names. Do not describe this particular helper as max-|t|. Its standardization uses a fixed bootstrap-estimated standard error, not a newly studentized standard error inside every bootstrap draw.
3. Horizon coefficient p-values are unadjusted HC3 descriptive results across multiple periods, outcomes, and specifications. They do not establish a new confirmatory H1 result.
4. The L-exit follow-up retains the original sqrt(5) normalization, position sizes, contract choices, and original F1-completeness eligibility. It is a same-position, one-session-earlier exit experiment; it is not a newly risk-retargeted four-day strategy. This is consistent and useful for attribution.
5. Winner/year deletion checks hold the historical forecasts and decisions fixed. They are outcome-concentration diagnostics, not full strategy refits after removing training observations.
6. The horizon was inspected after the original result. Its genuine chronological fitting does not make this selection an independent holdout test.

No original or frozen source was edited during this review.
