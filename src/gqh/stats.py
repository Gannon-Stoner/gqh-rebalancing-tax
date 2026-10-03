"""Inference: OLS, month-block and wild bootstraps, Holm, Newey-West, Sharpe, DSR, MDE.

Frozen choices (HYPOTHESIS.md §3 "Inference", §5; frozen.yaml ``inference``):

* The resampling unit is the calendar month. The primary test is a circular
  month-block bootstrap (block 3, 9,999 draws, seed 20261003). Each draw keeps
  every row of a drawn month (an event and its pseudo-event stay together), so a
  draw is the original rows with integer multiplicities and the bootstrap OLS
  is a weighted OLS.
* One-sided tests use the studentized (percentile-t) bootstrap: t* = (β̂* − β̂)/se*
  with heteroskedasticity-robust (HC0) standard errors in every draw, and
  p = (1 + #{t* >= t̂}) / (B + 1) for H: β > 0 (mirror for β < 0) (amendment A13).
* Fallback: a Rademacher wild bootstrap with month clusters, imposing the null.
  Sensitivity: Newey-West with a lag of 3 months on month-summed scores.
* Holm adjustment over the confirmatory family {H1, H2}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats as sps

EULER_GAMMA = 0.5772156649015329


# --- design and weighted OLS -------------------------------------------------------

def design(df: pd.DataFrame, terms: Sequence[str]) -> tuple[np.ndarray, list[str]]:
    """[1, terms...]; a term "a*b" is the product of columns a and b."""
    cols, names = [np.ones(len(df))], ["const"]
    for t in terms:
        parts = t.split("*")
        v = np.ones(len(df))
        for p in parts:
            v = v * df[p].to_numpy(dtype=float)
        cols.append(v)
        names.append(t)
    return np.column_stack(cols), names


def wols(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Batched weighted OLS. ``w`` is (B, n) row multiplicities; returns (beta (B, k), HC0 se (B, k))."""
    XtWX = np.einsum("bi,ij,ik->bjk", w, X, X)
    XtWy = np.einsum("bi,ij,i->bj", w, X, y)
    beta = np.linalg.solve(XtWX, XtWy[..., None])[..., 0]
    e = y[None, :] - beta @ X.T
    meat = np.einsum("bi,ij,ik->bjk", w * e**2, X, X)
    inv = np.linalg.inv(XtWX)
    cov = inv @ meat @ inv
    return beta, np.sqrt(np.clip(np.diagonal(cov, axis1=1, axis2=2), 0.0, None))


def ols_fit(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and HC0 standard errors."""
    beta, se = wols(X, y, np.ones((1, len(y))))
    return beta[0], se[0]


# --- month-block resampling ---------------------------------------------------------

def month_codes(months: pd.Series | pd.PeriodIndex) -> tuple[np.ndarray, int]:
    """Row -> position in the contiguous calendar-month range spanned by ``months`` (gaps included)."""
    p = pd.PeriodIndex(months, freq="M")
    ym = p.year.to_numpy() * 12 + p.month.to_numpy()
    codes = (ym - ym.min()).astype(int)
    return codes, int(codes.max()) + 1


def block_month_counts(n_months: int, block: int, draws: int, rng: np.random.Generator) -> np.ndarray:
    """(draws, n_months) multiplicities from a circular block bootstrap over calendar months."""
    n_blocks = int(np.ceil(n_months / block))
    starts = rng.integers(0, n_months, size=(draws, n_blocks))
    idx = (starts[..., None] + np.arange(block)).reshape(draws, -1)[:, :n_months] % n_months
    counts = np.zeros((draws, n_months))
    np.add.at(counts, (np.repeat(np.arange(draws), n_months), idx.ravel()), 1.0)
    return counts


# --- tests on one coefficient ---------------------------------------------------------

@dataclass(frozen=True)
class CoefTest:
    term: str
    estimate: float
    se: float
    t: float
    p: float                      # one-sided, in the direction of ``alternative``
    ci: tuple[float, float]       # two-sided at ``level``
    alternative: str              # "greater" or "less"
    method: str
    draws: int
    n: int


def _one_sided(t_star: np.ndarray, t_hat: float, alternative: str) -> float:
    t_star = t_star[np.isfinite(t_star)]
    hits = np.sum(t_star >= t_hat) if alternative == "greater" else np.sum(t_star <= t_hat)
    return float((1 + hits) / (len(t_star) + 1))


def _check(alternative: str) -> None:
    if alternative not in ("greater", "less"):
        raise ValueError("alternative must be 'greater' or 'less'")


def block_bootstrap_test(df: pd.DataFrame, terms: Sequence[str], term: str, *, alternative: str,
                         seed: int, block: int = 3, draws: int = 9999, level: float = 0.90,
                         y: str = "Y") -> CoefTest:
    """Studentized circular month-block bootstrap test of one coefficient (percentile-t CI)."""
    _check(alternative)
    X, names = design(df, terms)
    yv = df[y].to_numpy(dtype=float)
    j = names.index(term)
    beta, se = ols_fit(X, yv)
    t_hat = beta[j] / se[j]
    codes, n_months = month_codes(df["month"])
    counts = block_month_counts(n_months, block, draws, np.random.default_rng(seed))
    b_star, se_star = wols(X, yv, counts[:, codes])
    t_star = (b_star[:, j] - beta[j]) / se_star[:, j]
    lo_q, hi_q = np.nanquantile(t_star, [(1 - level) / 2, (1 + level) / 2])
    return CoefTest(term, float(beta[j]), float(se[j]), float(t_hat), _one_sided(t_star, t_hat, alternative),
                    (float(beta[j] - hi_q * se[j]), float(beta[j] - lo_q * se[j])), alternative,
                    "month_block", draws, len(yv))


def wild_bootstrap_test(df: pd.DataFrame, terms: Sequence[str], term: str, *, alternative: str,
                        seed: int, draws: int = 9999, y: str = "Y") -> CoefTest:
    """Rademacher wild bootstrap with month clusters, null imposed (the registered fallback)."""
    _check(alternative)
    X, names = design(df, terms)
    yv = df[y].to_numpy(dtype=float)
    j = names.index(term)
    beta, se = ols_fit(X, yv)
    t_hat = beta[j] / se[j]
    Xr = np.delete(X, j, axis=1)
    br, *_ = np.linalg.lstsq(Xr, yv, rcond=None)
    fit_r, e_r = Xr @ br, yv - Xr @ br
    codes, n_months = month_codes(df["month"])
    eta = np.random.default_rng(seed).choice([-1.0, 1.0], size=(draws, n_months))
    y_star = fit_r[None, :] + e_r[None, :] * eta[:, codes]
    inv = np.linalg.inv(X.T @ X)
    b_star = y_star @ X @ inv.T
    e_star = y_star - b_star @ X.T
    cov = inv[None] @ np.einsum("bi,ij,ik->bjk", e_star**2, X, X) @ inv[None]
    t_star = b_star[:, j] / np.sqrt(cov[:, j, j])
    return CoefTest(term, float(beta[j]), float(se[j]), float(t_hat), _one_sided(t_star, t_hat, alternative),
                    (np.nan, np.nan), alternative, "wild_rademacher", draws, len(yv))


def newey_west_test(df: pd.DataFrame, terms: Sequence[str], term: str, *, alternative: str,
                    lag_months: int = 3, y: str = "Y") -> CoefTest:
    """Normal-approximation test with Newey-West (Bartlett) HAC over month-summed scores."""
    _check(alternative)
    X, names = design(df, terms)
    yv = df[y].to_numpy(dtype=float)
    j = names.index(term)
    inv = np.linalg.inv(X.T @ X)
    beta = inv @ X.T @ yv
    codes, n_months = month_codes(df["month"])
    G = np.zeros((n_months, X.shape[1]))
    np.add.at(G, codes, X * (yv - X @ beta)[:, None])
    S = G.T @ G
    for lag in range(1, lag_months + 1):
        C = G[lag:].T @ G[:-lag]
        S += (1 - lag / (lag_months + 1)) * (C + C.T)
    se = float(np.sqrt((inv @ S @ inv)[j, j]))
    t_hat = float(beta[j] / se)
    p = float(sps.norm.sf(t_hat) if alternative == "greater" else sps.norm.cdf(t_hat))
    z = sps.norm.ppf(0.95)
    return CoefTest(term, float(beta[j]), se, t_hat, p, (beta[j] - z * se, beta[j] + z * se), alternative,
                    f"newey_west_{lag_months}", 0, len(yv))


def holm(pvalues: Sequence[float]) -> np.ndarray:
    """Holm step-down adjusted p-values (same order as the input)."""
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adj[i] = running
    return adj


# --- confirmatory regressions (HYPOTHESIS.md §5) -------------------------------------------

H1_TERMS = ("dose", "QE")                                          # Y = a + b·dose + γ·QE
H2_TERMS = ("ME", "dose", "ME*dose", "A", "ME*A")                  # stacked events (ME=1) + pseudo (ME=0)
H1_TERM, H2_TERM = "dose", "ME*A"                                   # b > 0; c_E < 0


def h1_test(events: pd.DataFrame, *, seed: int, draws: int = 9999, method: str = "month_block") -> CoefTest:
    """H1 on valid events: b > 0 in Y = a + b·dose + γ·QE."""
    df = events.loc[events["valid"].astype(bool), ["month", "Y", "dose", "QE"]].astype({"QE": float})
    return _run(df, H1_TERMS, H1_TERM, "greater", seed, draws, method)


def h2_test(stacked: pd.DataFrame, *, seed: int, draws: int = 9999, method: str = "month_block") -> CoefTest:
    """H2 on ``signals.stacked_panel`` rows: c_E < 0 (the ME·A interaction)."""
    df = stacked[["month", "Y", "dose", "A", "ME"]].astype({"ME": float})
    return _run(df, H2_TERMS, H2_TERM, "less", seed, draws, method)


def _run(df, terms, term, alternative, seed, draws, method) -> CoefTest:
    if method == "month_block":
        return block_bootstrap_test(df, terms, term, alternative=alternative, seed=seed, draws=draws)
    if method == "wild":
        return wild_bootstrap_test(df, terms, term, alternative=alternative, seed=seed, draws=draws)
    if method == "newey_west":
        return newey_west_test(df, terms, term, alternative=alternative)
    raise ValueError(f"unknown method {method}")


def mde(se: float, *, alpha: float = 0.05, power: float = 0.80) -> float:
    """One-sided minimum detectable effect: (z_{1-alpha} + z_power)·se."""
    return float((sps.norm.ppf(1 - alpha) + sps.norm.ppf(power)) * se)


# --- Sharpe ratios ------------------------------------------------------------------------

def sharpe(r: np.ndarray | pd.Series, periods_per_year: int = 12) -> float:
    """Annualized Sharpe ratio of per-period excess returns (ddof = 1)."""
    r = np.asarray(r, dtype=float)
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(periods_per_year)) if sd > 0 else np.nan


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max] of n_trials per-period Sharpe ratios under the null (Bailey & López de Prado), floored at 0."""
    if n_trials <= 1:
        return 0.0
    z1 = sps.norm.ppf(1 - 1 / n_trials)
    z2 = sps.norm.ppf(1 - 1 / (n_trials * np.e))
    return float(max(0.0, np.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)))


def psr_from_moments(sr: float, T: int, skew: float, kurt: float, sr_benchmark: float = 0.0) -> float:
    """PSR from the per-period SR, sample length, skewness and raw (non-excess) kurtosis."""
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)
    return float(sps.norm.cdf((sr - sr_benchmark) * np.sqrt(T - 1) / denom))


def probabilistic_sharpe(r: np.ndarray | pd.Series, sr_benchmark: float = 0.0) -> float:
    """PSR: P(true per-period SR > benchmark) with skewness and raw kurtosis (ddof = 1)."""
    r = np.asarray(r, dtype=float)
    return psr_from_moments(r.mean() / r.std(ddof=1), len(r), sps.skew(r, bias=False),
                            sps.kurtosis(r, fisher=False, bias=False), sr_benchmark)


def deflated_sharpe(r: np.ndarray | pd.Series, n_trials: int, var_sr: float | None = None) -> float:
    """DSR = PSR against the expected maximum of ``n_trials`` null Sharpe ratios.

    ``var_sr`` is the variance of the per-period SR across trials; the default is
    the null value 1/T.
    """
    r = np.asarray(r, dtype=float)
    v = 1.0 / len(r) if var_sr is None else var_sr
    return probabilistic_sharpe(r, expected_max_sharpe(n_trials, v))


def delta_sharpe_ci(r1: pd.Series, r2: pd.Series, *, seed: int, block: int = 3, draws: int = 9999,
                    level: float = 0.90, periods_per_year: int = 12) -> tuple[float, tuple[float, float]]:
    """Annualized SR(r1) − SR(r2) and its paired circular month-block bootstrap percentile CI.

    ``r1`` and ``r2`` are monthly returns on the same contiguous PeriodIndex (0 in flat months).
    """
    if not r1.index.equals(r2.index):
        raise ValueError("both series need the same monthly index")
    a, b = r1.to_numpy(dtype=float), r2.to_numpy(dtype=float)
    est = sharpe(a, periods_per_year) - sharpe(b, periods_per_year)
    w = block_month_counts(len(a), block, draws, np.random.default_rng(seed))

    def wsr(x: np.ndarray) -> np.ndarray:
        n = w.sum(axis=1)
        m = (w @ x) / n
        var = (w @ x**2 - n * m**2) / (n - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return m / np.sqrt(var) * np.sqrt(periods_per_year)

    d = wsr(a) - wsr(b)
    if not np.isfinite(d).any():
        return float(est), (np.nan, np.nan)
    lo, hi = np.nanquantile(d, [(1 - level) / 2, (1 + level) / 2])
    return float(est), (float(lo), float(hi))


def coef_draws(df: pd.DataFrame, terms: Sequence[str], term: str, *, seed: int, block: int = 3,
               draws: int = 9999, y: str = "Y") -> tuple[float, np.ndarray]:
    """Point estimate and circular month-block bootstrap draws of one OLS coefficient (for differences)."""
    X, names = design(df, terms)
    yv = df[y].to_numpy(dtype=float)
    j = names.index(term)
    beta, _ = ols_fit(X, yv)
    codes, n_months = month_codes(df["month"])
    b_star, _ = wols(X, yv, block_month_counts(n_months, block, draws, np.random.default_rng(seed))[:, codes])
    return float(beta[j]), b_star[:, j]
