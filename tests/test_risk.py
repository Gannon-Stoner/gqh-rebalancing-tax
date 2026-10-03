"""Risk and capital numbers (gqh.risk)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import risk as R
from gqh.config import frozen_config

CFG = frozen_config()
NAV = CFG.reference_nav


def _ledger():
    months = pd.PeriodIndex(["2020-02", "2020-03", "2022-05", "2022-06"], freq="M")
    return pd.DataFrame({"month": months, "traded": [True, True, True, False], "pnl_es": [1e4, -5e4, 2e4, 0.0],
                         "pnl_zn": [-2e3, -1e4, 1e4, 0.0], "cost": [500.0, 600.0, 400.0, 0.0],
                         "pnl": [7.5e3, -6.06e4, 2.96e4, 0.0], "n_es": [10, 12, 8, 0], "n_zn": [20, 22, 15, 0],
                         "dose": [1.0, 2.0, 0.5, 1.0], "es_in": [3000.0, 2500.0, 4000.0, np.nan],
                         "zn_in": [130.0, 138.0, 118.0, np.nan], "entry": pd.NaT, "exit": pd.NaT})


def test_stress_table_by_period():
    t = R.stress_table(_ledger(), NAV).set_index("period")
    assert t.loc["2020-03", "es_pct"] == pytest.approx(-0.5) and t.loc["2022", "events"] == 1
    assert t.loc["2011-08", "events"] == 0


def test_factor_regression_recovers_loadings():
    days = pd.bdate_range("2016-01-01", "2020-12-31")
    rng = np.random.default_rng(1)
    f = pd.DataFrame({"mkt": rng.normal(0, 0.01, len(days)), "zn": rng.normal(0, 0.004, len(days))}, index=days)
    months = pd.period_range("2016-01", "2020-11", freq="M")
    entry = [days[days.to_period("M") == m][-5] for m in months]
    exit_ = [days[days.to_period("M") == m + 1][0] for m in months]
    win = pd.DataFrame({"month": months, "entry": entry, "exit": exit_})
    fsum = np.array([f[(f.index > a) & (f.index <= b)].sum().to_numpy() for a, b in zip(entry, exit_)])
    ret = pd.Series(0.001 + 0.5 * fsum[:, 0] - 0.2 * fsum[:, 1] + rng.normal(0, 1e-5, len(months)))
    out = R.factor_regression(ret, win, f)
    assert out["coef"]["mkt"] == pytest.approx(0.5, abs=0.01) and out["coef"]["zn"] == pytest.approx(-0.2, abs=0.01)
    assert out["coef"]["alpha"] == pytest.approx(0.001, abs=1e-4)


def test_margin_drawdown_probability_and_t2():
    led = _ledger()
    m = R.margin_ledger(led, pd.Series([1e3, -2e4, 5e3]), {"ES": 12_000.0, "ZN": 2_000.0}, NAV)
    assert m["margin_to_equity_max"] == pytest.approx((12 * 12_000 + 22 * 2_000) / NAV)
    assert m["worst_daily_vm_pct"] == pytest.approx(-0.2)
    flat = pd.Series([0.001] * 24)
    assert R.drawdown_probability(flat, draws=200) == 0.0
    crash = pd.Series([-0.03] * 24)
    assert R.drawdown_probability(crash, draws=200) == 1.0
    x = pd.Series(np.tile([0.02, -0.01], 30))
    assert R.months_to_t2(x) == pytest.approx((2 / (x.mean() / x.std(ddof=1))) ** 2)


def test_stop_loss_stress_and_impact():
    led = _ledger()
    limit = 2 * 2.0 / 2 * CFG.kappa * NAV                      # 2-sigma for the dose-2 March event
    daily = pd.DataFrame({"month": pd.Period("2020-03", "M"), "date": pd.bdate_range("2020-03-24", periods=3),
                          "gross": [-0.5 * limit, -0.7 * limit, 0.9 * limit]})
    out = R.stop_loss_stress(led, daily, CFG)
    assert out["stopped_events"] == 1 and out["net_with_stop"] == pytest.approx(-1.2 * limit - 600.0)
    assert R.impact_cost(100, 4000.0, 50.0, 0.01, 1e6) == pytest.approx(0.01 * 0.01 * 4000 * 50)
    assert R.impact_cost(1, 4000.0, 50.0, 0.01, 0.0) == np.inf
