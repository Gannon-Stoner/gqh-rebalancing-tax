# HMM rebalancing-pressure replication — fixed specification

Status: written 2026-10-03 **before** any return in this directory is computed. `run.py` refuses to run
unless this file's SHA-256 matches `spec_lock.json`, written at lock time. Any later change requires a dated
amendment section at the end of this file plus a new lock, and the earlier result stays on record.

## 1. Purpose and claim boundary

This is a replication of Harvey, Mazzoleni & Melone (NBER w33554, rev. Jan 2026; "HMM"), Table 1, column (1),
on our own ES/ZN settlement data. It tests whether **rebalancing pressure** exists in our data, not whether
our original gated strategy works. The original pre-registered H1/H2 results and gate failure are unchanged.

Disclosures:
- Our in-sample data (2010-06-07 → 2024-10-01) has been inspected extensively for month-end event windows.
  This test's specification is copied from the paper, not chosen from our data, but the data is not pristine.
- 2010-06 → 2023-03-17 overlaps HMM's sample. This segment is a **reproduction on different instruments and
  clocks**, not independent evidence. Only 2023-03-20 → 2024-10-01 is outside HMM's sample.
- The OOS period (from 2024-10-02) is **not** opened. The loader filters to `date <= 2024-10-01`.

## 2. Data

- Daily within-contract log returns `r_es`, `r_zn` from `gqh.pipeline.prepare` (frozen contract selection:
  max-OI reference contract, no cross-contract returns), IS sessions only.
- Simple returns: R_SP = exp(r_es) − 1, R_10Y = exp(r_zn) − 1. Futures returns are excess returns.
- Ret_t = R_SP,t − R_10Y,t.
- Clock mismatch, disclosed: ES settles at 16:00 ET (16:15 before 2020-10-26), ZN at 15:00 ET. HMM use
  Bloomberg futures closes.
- Days with a missing return for either leg: the drift recursions carry weights unchanged (zero return), and the
  day is dropped from the regression as a dependent or predictor observation.
- "Last business day of the month" = last qualifying session of the calendar month in our session calendar (L).

## 3. Signals (HMM Appendix B)

Weight drift: w' = w(1+R_SP) / (w(1+R_SP) + (1−w)(1+R_10Y)), target 0.60.

- **Threshold_δ**: start at w = 0.60 on the first session. Each day compute the drifted weight w' from the
  previous weight; signal_δ,t = w' − 0.60. If |w' − 0.60| ≥ δ, reset w to 0.60, else w = w'.
  δ ∈ {0.0%, 0.1%, …, 2.5%} (26 values). **Threshold_t** = mean over δ.
- **Calendar**: same drift, signal_t = w' − 0.60; reset w to 0.60 at the close of each month's L.
- **week4_t** = 1 if t is one of the last five sessions of its month (L−4 … L), else 0.
- **Momentum_t** = mean(Mom_medium, Mom_slow). Mom_medium = average over k = 11…20 of sign(cumulative Ret over
  the trailing k sessions ending t). Mom_slow = same over k ∈ {21, 42, 63, 126, 252}. HMM's text says "signs of
  trailing k daily excess returns"; we read this as cumulative k-day excess returns (ambiguity disclosed).
- A 252-session warm-up is excluded from the regression (momentum needs it; drift states settle within it).

## 4. Primary regression (HMM eq. 4, Table 1 col. 1)

Ret_{t+1} = β0 + β_T·Threshold_t + β_C·Calendar_t + β_W·week4_t + β_CW·Calendar_t·week4_t + ψ·Momentum_t + ζ·Ret_t + ε

OLS with HC1 standard errors (HMM: heteroskedasticity-consistent). Newey-West (5 lags) is a sensitivity.

## 5. Confirmatory tests (pass/fail fixed now)

On the **primary sample** (all IS days after warm-up through the last IS session with a next-day return):

- **R1**: β_T < 0 (one-sided).
- **R2**: β_CW < 0 (one-sided).
- Holm adjustment over {R1, R2} at α = 0.05, HC1 p-values. Each test is reported as replicated or not.

HMM benchmarks: β_T = −0.414 (se 0.115), β_CW = −0.303 (se 0.081), 6,226 days.

**Power (stated before running)**: if the true coefficients equal HMM's, our expected t-statistic scales with
√(N/6,226). For N ≈ 3,300 that is t ≈ −2.6 (R1) and −2.7 (R2), giving power of about 0.75 per test at the Holm level (critical one-sided z = 1.96 at the first step).
On the post-HMM segment alone (≈ 385 days) the expected t ≈ −0.9, power ≈ 0.2. **A null there is
uninformative.**

## 6. Secondary and descriptive (no pass/fail)

1. The same regression on the post-HMM segment (2023-03-20 → 2024-10-01), and on 2015-10 → 2024-10-01 (the
   phase-validation window).
2. Newey-West(5) standard errors for the primary regression.
3. Without momentum: shows how much the momentum control matters.
4. week4 excluding t = L (so day L → F1 returns are not predicted): separates the effect from the first-session
   behaviour found in the phase-validation work.
5. Separate legs: R_SP and −R_10Y as dependent variables.
6. HMM Section 4 front-running strategy, gross and with approximate costs: daily weight
   w_t = ½·(−Threshold_t / 1.5%) + ½·C_t, where C_t = sign(−Calendar_t) on week4 days, else 0; P&L
   w_t·Ret_{t+1}. The first-session flip in HMM is reported as a separate variant, using sign(Calendar) from the
   session four sessions before L, because our earlier work showed day-1 returns are mainly a long-equity effect.
   Approximate costs: 1.3 bp per unit of |Δw| (ES and ZN frozen half-spread plus fee as a fraction of typical
   notional). Descriptive only: this is not a capacity or fill claim.

## 7. Reporting

Every regression row is written to `results.json` and `report.md`, including failures. The two confirmatory
outcomes are stated first, then the secondary results.
