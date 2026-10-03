"""Row metrics (gqh.metrics)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import metrics as M
from gqh.config import frozen_config

CFG = frozen_config()


def _ledger() -> pd.DataFrame:
    months = pd.period_range("2016-01", periods=6, freq="M")
    return pd.DataFrame({"month": months, "traded": [True, False, True, True, False, True],
                         "ret": [0.01, 0.0, -0.02, 0.005, 0.0, 0.01], "pnl": [1e5, 0.0, -2e5, 5e4, 0.0, 1e5],
                         "cost": [500.0, 0.0, 400.0, 300.0, 0.0, 500.0], "gross_nav": [0.6, 0.0, 0.5, 0.4, 0.0, 0.7],
                         "dose": [1.0, np.nan, 2.0, 0.5, np.nan, 1.0]})


def test_monthly_returns_fill_flat_months_with_zero():
    months = pd.period_range("2015-12", periods=8, freq="M")
    r = M.monthly_returns(_ledger(), months)
    assert list(r.index) == list(months) and r.iloc[0] == 0.0 and r.loc[pd.Period("2016-03", "M")] == -0.02
    assert r.sum() == pytest.approx(0.005)


def test_drawdown_metrics_and_turnover():
    assert M.max_drawdown(pd.Series([0.01, -0.02, 0.005, -0.01, 0.03])) == pytest.approx(0.025)
    months = pd.period_range("2016-01", periods=6, freq="M")
    m = M.row_metrics(_ledger(), months, CFG)
    x = np.array([0.01, 0.0, -0.02, 0.005, 0.0, 0.01])
    assert m["trades"] == 4 and m["ann_return"] == pytest.approx(x.mean() * 12)
    assert m["sharpe"] == pytest.approx(x.mean() / x.std(ddof=1) * np.sqrt(12))
    assert m["worst_month"] == -0.02 and m["hit_rate"] == 0.75
    assert m["turnover"] == pytest.approx(2 * (0.6 + 0.5 + 0.4 + 0.7) / 0.5)    # 6 months = half a year


def test_realized_to_target_is_one_when_pnl_equals_the_risk_target():
    led = _ledger()
    t = led["traded"]
    target = led["dose"] / 2 * CFG.kappa * CFG.reference_nav
    led.loc[t, "pnl"] = np.where(np.arange(t.sum()) % 2, 1, -1) * target[t] - led.loc[t, "cost"]
    assert M.realized_to_target(led, CFG).to_dict() == pytest.approx({2016: 1.0})
