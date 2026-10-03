"""Remaining-return gate: walk-forward OLS, leakage, freezing and decisions (gqh.gate)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import gate as G
from gqh.config import frozen_config

CFG = frozen_config()


def panel(n_months: int = 260, start: str = "2006-01", seed: int = 7) -> pd.DataFrame:
    """Monthly rows: decide on the 24th, exit on the 2nd of next month; Y = 0.05 dose - 0.1 A + noise."""
    rng = np.random.default_rng(seed)
    months = pd.period_range(start, periods=n_months, freq="M")
    dose = rng.uniform(0, 2, n_months)
    A = rng.normal(0, 1, n_months)
    df = pd.DataFrame({
        "month": months, "dec": months.to_timestamp() + pd.Timedelta(days=23),
        "exit": (months + 1).to_timestamp() + pd.Timedelta(days=1),
        "dose": dose, "A": A, "Y": 0.05 * dose - 0.1 * A + rng.normal(0, 1, n_months), "valid": True,
    })
    df.loc[[3, 50, 51], "valid"] = False
    return df


def test_ols_matches_the_normal_equations():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 2))
    y = 0.3 + X @ np.array([0.5, -0.2]) + rng.normal(size=200)
    Z = np.column_stack([np.ones(200), X])
    assert np.allclose(G.ols(X, y), np.linalg.solve(Z.T @ Z, Z.T @ y))


def test_first_forecast_needs_min_events_completed_valid_rows():
    p = panel()
    wf = G.walk_forward(p, cfg=CFG)
    first = wf["yhat"].first_valid_index()
    assert wf.loc[first, "n_train"] == CFG.min_events
    assert wf.loc[:first - 1, "yhat"].isna().all()
    assert (wf["n_train"].diff().dropna() >= 0).all()


def test_no_leakage_future_and_current_outcomes_do_not_move_a_forecast():
    p = panel()
    wf = G.walk_forward(p, cfg=CFG)
    for i in range(70, 200, 13):
        q = p.copy()
        unknown = q["exit"] >= q.loc[i, "dec"]            # includes row i itself
        q.loc[unknown, "Y"] = 1e6
        assert G.walk_forward(q, cfg=CFG).loc[i, "yhat"] == pytest.approx(wf.loc[i, "yhat"], abs=1e-12)
    q = p.copy()
    q.loc[q.index > 150, ["dose", "A"]] = 9.0                # later features do not matter either
    assert np.allclose(G.walk_forward(q, cfg=CFG).loc[:150, "yhat"], wf.loc[:150, "yhat"], equal_nan=True)


def test_coefficients_freeze_at_the_end_of_is():
    p = panel()
    oos = p["dec"] > CFG.is_end
    assert oos.sum() >= 20
    wf = G.walk_forward(p, cfg=CFG)
    coef = wf.loc[oos, ["coef_const", "coef_dose", "coef_A"]]
    assert (coef.nunique() == 1).all()                      # one frozen model for all OOS rows
    q = p.copy()
    q.loc[oos, "Y"] = -1e6
    assert np.allclose(G.walk_forward(q, cfg=CFG).loc[oos, "yhat"], wf.loc[oos, "yhat"])
    is_rows = p["valid"] & (p["exit"] <= CFG.is_end)
    expected = G.ols(p.loc[is_rows, ["dose", "A"]].to_numpy(), p.loc[is_rows, "Y"].to_numpy())
    assert np.allclose(coef.iloc[0].to_numpy(), expected)


def test_decisions_trade_only_above_the_hurdle_and_never_reverse():
    p = panel()
    hurdle = np.full(len(p), 0.02)
    hurdle[100] = np.nan                                     # below one lot: no hurdle, no trade
    d = G.gate_decisions(p, hurdle, cfg=CFG)
    assert (d["trade"] == (p["valid"] & d["gated"] & (d["yhat"] > d["hurdle"]))).all()
    assert not d.loc[100, "trade"] and not d.loc[~d["gated"], "trade"].any()
    assert not d.loc[~p["valid"], "trade"].any()
    pd_ = G.gate_decisions(p, hurdle, features=G.DOSE_ONLY, cfg=CFG)
    assert "coef_A" not in pd_.columns and pd_["yhat"].notna().sum() == d["yhat"].notna().sum()
