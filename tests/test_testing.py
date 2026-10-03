"""Tests for gqh.testing: each helper must pass good code and catch bad code."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from gqh import synth, testing

IDX = pd.bdate_range("2021-01-04", periods=120)


# ------------------------------------------------------------ truncation

def _series_data():
    rng = np.random.default_rng(0)
    return pd.Series(rng.standard_normal(len(IDX)), index=IDX, name="x")


def trailing_mean(s):
    return s.rolling(5).mean()


def centered_mean(s):                      # uses 2 future rows: look-ahead
    return s.rolling(5, center=True).mean()


def test_truncation_passes_causal_trailing_mean():
    testing.assert_truncation_invariant(trailing_mean, _series_data(),
                                        IDX[[10, 50, 119]])


def test_truncation_catches_centered_moving_average():
    with pytest.raises(AssertionError, match="look-ahead"):
        testing.assert_truncation_invariant(centered_mean, _series_data(),
                                            IDX[[10, 50]])


def test_truncation_catches_full_sample_normalisation():
    def zscore(s):                         # full-sample mean/sd leak the future
        return (s - s.mean()) / s.std()
    with pytest.raises(AssertionError):
        testing.assert_truncation_invariant(zscore, _series_data(), IDX[[60]])


def test_truncation_with_key_column_and_frame_output():
    data = pd.DataFrame({"date": IDX, "x": _series_data().to_numpy()})

    def causal(df):
        return pd.DataFrame({"date": df.date, "m": df.x.expanding().mean()})

    def leaky(df):
        return pd.DataFrame({"date": df.date, "m": df.x.shift(-1)})

    testing.assert_truncation_invariant(causal, data, IDX[[5, 70]], key="date")
    with pytest.raises(AssertionError):
        testing.assert_truncation_invariant(leaky, data, IDX[[70]], key="date")


def test_truncation_catches_rows_that_vanish():
    def drops_last(s):                     # needs a later row to emit a row
        return s.iloc[:-1]
    with pytest.raises(AssertionError):
        testing.assert_truncation_invariant(drops_last, _series_data(), IDX[[30]])


# ------------------------------------------------------------ P&L window

def test_pnl_only_in_window_pass_and_fail():
    pnl = pd.Series(0.0, index=IDX)
    pnl.iloc[11:16] = 1.0                  # window (IDX[10], IDX[15]]
    pnl.iloc[3] = np.nan                   # NaN = flat
    testing.assert_pnl_only_in_window(pnl, IDX[10], IDX[15])
    with pytest.raises(AssertionError, match="outside"):
        testing.assert_pnl_only_in_window(pnl, IDX[11], IDX[15])  # entry day P&L
    with pytest.raises(AssertionError):
        testing.assert_pnl_only_in_window(pnl, IDX[10], IDX[14])  # exit day P&L


def test_pnl_only_in_window_multiple_windows_and_tolerance():
    pnl = pd.Series(0.0, index=IDX)
    pnl.iloc[[5, 6, 40]] = 2.0
    pnl.iloc[80] = 1e-14
    testing.assert_pnl_only_in_window(pnl, [IDX[4], IDX[39]], [IDX[6], IDX[40]])
    with pytest.raises(AssertionError):
        testing.assert_pnl_only_in_window(pnl, [IDX[4]], [IDX[6]])
    with pytest.raises(ValueError):
        testing.assert_pnl_only_in_window(pnl, [IDX[4]], [IDX[6], IDX[40]])


def test_pnl_window_on_planted_returns():
    rets = synth.impulse_returns(IDX, IDX[20], 0.03, leg="spread")
    pnl = rets.r_es - rets.r_zn            # a held 1:1 spread position
    testing.assert_pnl_only_in_window(pnl, IDX[19], IDX[24])
    with pytest.raises(AssertionError):
        testing.assert_pnl_only_in_window(pnl, IDX[20], IDX[24])


# ------------------------------------------------------------ size helpers

def _uniform(rng):
    return rng.uniform()


def _identity(p):
    return p


def test_rejection_rate_uniform_null_hits_alpha():
    rate, (lo, hi) = testing.rejection_rate(_identity, _uniform, 4000, 0.05,
                                            seed=20261003)
    assert abs(rate - 0.05) < 0.01
    assert lo <= 0.05 <= hi
    assert lo <= rate <= hi
    testing.assert_size_ok((rate, (lo, hi)), 0.05)


def test_rejection_rate_deterministic_and_prefix_stable():
    seen_a, seen_b, seen_c = [], [], []

    def gen(store):
        def g(rng):
            store.append(rng.uniform())
            return store[-1]
        return g

    r1 = testing.rejection_rate(_identity, gen(seen_a), 50, 0.1, seed=1)
    r2 = testing.rejection_rate(_identity, gen(seen_b), 80, 0.1, seed=1)
    testing.rejection_rate(_identity, gen(seen_c), 50, 0.1, seed=2)
    assert seen_a == seen_b[:50]           # panel i does not depend on n_panels
    assert seen_a != seen_c
    assert r1 == testing.rejection_rate(_identity, _uniform, 50, 0.1, seed=1)
    assert isinstance(r2[0], float)


def test_rejection_rate_passes_independent_test_rng():
    def test_fn(panel, rng):
        return rng.uniform()               # ignores the panel entirely
    rate, _ = testing.rejection_rate(test_fn, lambda rng: 0.0, 4000, 0.05,
                                     seed=3, pass_rng=True)
    assert abs(rate - 0.05) < 0.01


def test_clopper_pearson_matches_scipy_exact():
    for k, n in [(0, 10), (3, 10), (10, 10), (25, 500), (499, 500)]:
        ci = stats.binomtest(k, n).proportion_ci(confidence_level=0.95,
                                                method="exact")
        assert testing.clopper_pearson(k, n) == pytest.approx(
            (ci.low, ci.high), abs=1e-10)
    assert testing.clopper_pearson(0, 10)[1] == pytest.approx(1 - 0.025 ** 0.1)


def test_assert_size_ok_flags_oversized_and_undersized_tests():
    over = testing.rejection_rate(lambda p: p / 2, _uniform, 2000, 0.05, seed=5)
    under = testing.rejection_rate(lambda p: min(1.0, 3 * p), _uniform, 2000,
                                   0.05, seed=5)
    with pytest.raises(AssertionError, match="outside the size band"):
        testing.assert_size_ok(over, 0.05)
    with pytest.raises(AssertionError):
        testing.assert_size_ok(under, 0.05)
    with pytest.raises(ValueError):
        testing.assert_size_ok((0.05, (0.04, 0.06)), 0.10)


def test_t_test_on_synthetic_garch_null_is_sized():
    """End-to-end use: a one-sided t-test of zero mean on AR(0)-GARCH-t5
    returns should hold nominal size; the generator takes the panel rng as
    its seed."""
    def gen(rng):
        return synth.ar1_garch_t(250, phi=0.0, seed=rng, burn=250)

    def t_test(x):
        return stats.ttest_1samp(x, 0.0, alternative="greater").pvalue

    rate_ci = testing.rejection_rate(t_test, gen, 2000, 0.05, seed=20261003)
    testing.assert_size_ok(rate_ci, 0.05)


# ------------------------------------------------------------ P&L matches window

def _may_2014_event():
    from gqh import calendar as gcal
    idx = gcal.xnys_sessions("2013-12-01", "2015-01-31")
    sched = gcal.event_schedule(gcal.SessionCalendar(idx))
    r = sched[sched["month"] == pd.Period("2014-05", freq="M")].iloc[0]
    return idx, r, gcal.SessionCalendar(idx)


def test_pnl_matches_window_catches_all_four_boundary_bugs():
    # Regression: assert_pnl_only_in_window is one-sided, so exiting one session
    # early (dropping the F1 month-turn return), entering late, or never trading
    # all passed.
    idx, r, cal = _may_2014_event()
    legs = synth.correlated_leg_returns(idx, seed=1)
    x = legs.r_es - legs.r_zn

    def held(entry, exit_, pos=1.0):
        return (pos * x).where((idx > entry) & (idx <= exit_), 0.0)

    entry, exit_ = r["L_m4"], r["F1"]
    testing.assert_pnl_matches_window(held(entry, exit_), x, entry, exit_)
    testing.assert_pnl_matches_window(held(entry, exit_, -2.0), x, entry, exit_, position=-2.0)
    bugs = {
        "exit early": held(entry, r["L"]),
        "exit late": held(entry, cal.offset(exit_, 1)),
        "enter early": held(cal.offset(entry, -1), exit_),
        "enter late": held(cal.offset(entry, 1), exit_),
        "never trades": x * 0.0,
        "wrong sign": held(entry, exit_, -1.0),
    }
    for name, pnl in bugs.items():
        with pytest.raises(AssertionError):
            testing.assert_pnl_matches_window(pnl, x, entry, exit_)
    # The one-sided helper misses two of these (the review's evidence).
    testing.assert_pnl_only_in_window(bugs["exit early"], entry, exit_)
    testing.assert_pnl_only_in_window(bugs["never trades"], entry, exit_)


def test_pnl_matches_window_with_planted_effect_sums_to_m():
    idx, r, _ = _may_2014_event()
    zero = pd.DataFrame(0.0, index=idx, columns=["r_es", "r_zn"])
    ev = pd.DataFrame([r])
    planted = synth.plant_event_effect(zero, ev, 0.012)
    x = planted.r_es - planted.r_zn
    pnl = x.where((idx > r["L_m4"]) & (idx <= r["F1"]), 0.0)
    testing.assert_pnl_matches_window(pnl, x, r["L_m4"], r["F1"])
    assert pnl.sum() == pytest.approx(0.012, abs=1e-15)
    early_exit = x.where((idx > r["L_m4"]) & (idx <= r["L"]), 0.0)
    assert early_exit.sum() == pytest.approx(0.012 * 4 / 5)
    with pytest.raises(AssertionError):
        testing.assert_pnl_matches_window(early_exit, x, r["L_m4"], r["F1"])


def test_pnl_matches_window_multiple_windows_and_bad_input():
    x = pd.Series(1.0, index=IDX)
    pnl = pd.Series(0.0, index=IDX)
    pnl.iloc[5:8] = 2.0                       # (IDX[4], IDX[7]] at +2
    pnl.iloc[40] = -1.0                       # (IDX[39], IDX[40]] at -1
    testing.assert_pnl_matches_window(pnl, x, [IDX[4], IDX[39]], [IDX[7], IDX[40]],
                                      position=[2.0, -1.0])
    with pytest.raises(AssertionError):
        testing.assert_pnl_matches_window(pnl, x, [IDX[4]], [IDX[7]], position=2.0)
    with pytest.raises(ValueError):
        testing.assert_pnl_matches_window(pnl, x, [IDX[4]], [IDX[7], IDX[40]])
    with pytest.raises(ValueError):
        testing.assert_pnl_matches_window(pnl, x.iloc[:-1], IDX[4], IDX[7])
