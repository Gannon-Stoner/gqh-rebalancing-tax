"""Inference building blocks (gqh.stats)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from gqh import stats as S


def _df(n_months: int = 180, b: float = 0.0, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.period_range("2010-07", periods=n_months, freq="M")
    dose = rng.uniform(0, 2, n_months)
    qe = (months.month % 3 == 0).astype(float)
    return pd.DataFrame({"month": months, "dose": dose, "QE": qe,
                         "Y": 0.01 + b * dose + rng.standard_t(5, n_months) * 0.8})


def test_weighted_ols_equals_ols_on_repeated_rows_and_hc0_matches_statsmodels():
    df = _df()
    X, names = S.design(df, ["dose", "QE", "dose*QE"])
    assert names == ["const", "dose", "QE", "dose*QE"]
    assert np.allclose(X[:, 3], df["dose"] * df["QE"])
    y = df["Y"].to_numpy()
    w = np.random.default_rng(1).integers(0, 3, size=len(y)).astype(float)
    beta, se = S.wols(X, y, w[None, :])
    rep = np.repeat(np.arange(len(y)), w.astype(int))
    ref = sm.OLS(y[rep], X[rep]).fit(cov_type="HC0")
    assert np.allclose(beta[0], ref.params) and np.allclose(se[0], ref.bse)


def test_circular_month_blocks_keep_the_sample_length_and_contiguity():
    counts = S.block_month_counts(10, 3, 500, np.random.default_rng(2))
    assert counts.shape == (500, 10) and (counts.sum(axis=1) == 10).all()
    codes, n = S.month_codes(pd.Series(pd.PeriodIndex(["2010-07", "2010-09", "2011-01"], freq="M")))
    assert list(codes) == [0, 2, 6] and n == 7


def test_block_bootstrap_detects_a_strong_effect_and_reports_a_ci():
    t = S.block_bootstrap_test(_df(b=0.6), ["dose", "QE"], "dose", alternative="greater", seed=3, draws=999)
    assert t.p < 0.01 and t.ci[0] < t.estimate < t.ci[1] and t.ci[0] > 0
    t_less = S.block_bootstrap_test(_df(b=0.6), ["dose", "QE"], "dose", alternative="less", seed=3, draws=999)
    assert t_less.p > 0.95


def test_bootstrap_p_values_are_roughly_uniform_under_the_null():
    ps = [S.block_bootstrap_test(_df(seed=s), ["dose", "QE"], "dose", alternative="greater",
                                 seed=s, draws=399).p for s in range(60)]
    assert 0.25 < np.mean(ps) < 0.75 and np.mean(np.array(ps) < 0.05) < 0.2


def test_wild_bootstrap_and_newey_west():
    df = _df(b=0.6)
    w = S.wild_bootstrap_test(df, ["dose", "QE"], "dose", alternative="greater", seed=4, draws=999)
    assert w.p < 0.01
    nw = S.newey_west_test(df, ["dose", "QE"], "dose", alternative="greater", lag_months=3)
    X, _ = S.design(df, ["dose", "QE"])
    ref = sm.OLS(df["Y"].to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": 3, "use_correction": False})
    assert nw.se == pytest.approx(ref.bse[1], rel=1e-10)


def test_holm_adjustment():
    assert np.allclose(S.holm([0.01, 0.04]), [0.02, 0.04])
    assert np.allclose(S.holm([0.04, 0.01]), [0.04, 0.02])
    assert np.allclose(S.holm([0.03, 0.02]), [0.04, 0.04])          # step-down stays monotone


def test_h1_h2_wrappers_use_the_registered_terms_and_directions():
    df = _df(b=0.6).assign(valid=True)
    assert S.h1_test(df, seed=5, draws=199).alternative == "greater"
    st = pd.concat([df.assign(ME=1, A=np.random.default_rng(6).normal(size=len(df))),
                    df.assign(ME=0, A=np.random.default_rng(7).normal(size=len(df)))])
    t = S.h2_test(st, seed=5, draws=199)
    assert t.term == "ME*A" and t.alternative == "less"


def test_mde_sharpe_and_the_deflated_sharpe_worked_example():
    assert S.mde(0.1) == pytest.approx((1.6448536 + 0.8416212) * 0.1, rel=1e-6)
    r = np.array([0.01, -0.02, 0.03, 0.0, 0.02])
    assert S.sharpe(r) == pytest.approx(r.mean() / r.std(ddof=1) * np.sqrt(12))
    # Bailey & López de Prado (2014): SR 2.5/yr on 1,250 daily obs, skew -3, kurt 10, N = 100, V = 0.5/yr -> DSR ~ 0.90
    sr0 = S.expected_max_sharpe(100, 0.5 / 250)
    assert sr0 == pytest.approx(0.1132, abs=5e-4)
    assert S.psr_from_moments(2.5 / np.sqrt(250), 1250, -3.0, 10.0, sr0) == pytest.approx(0.9004, abs=2e-3)
    assert S.expected_max_sharpe(1, 0.1) == 0.0


def test_delta_sharpe_ci_is_paired():
    idx = pd.period_range("2015-01", periods=120, freq="M")
    rng = np.random.default_rng(8)
    a = pd.Series(rng.normal(0.01, 0.03, 120), index=idx)
    est, ci = S.delta_sharpe_ci(a, a, seed=9, draws=499)
    assert est == 0.0 and ci == (0.0, 0.0)
    est, ci = S.delta_sharpe_ci(a + 0.002, a, seed=9, draws=499)
    assert est > 0 and ci[0] > 0
