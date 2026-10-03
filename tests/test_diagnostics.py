"""Descriptive diagnostics (gqh.diagnostics)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import diagnostics as G
from gqh import synth
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions
from gqh.config import frozen_config
from gqh.contracts import ContractPanel, reference_returns

CFG = frozen_config()
SESS = xnys_sessions("2010-06-07", "2013-12-31")


def test_event_path_is_zero_at_l_minus_12_and_tracks_the_signed_spread():
    legs = synth.protocol_null_legs(SESS, "base", seed=3)
    es = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0), "ES")
    zn = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0), "ZN")
    ref = reference_returns(es, zn, SESS)
    sched = trading_schedule(SessionCalendar(SESS))
    paths = G.event_paths(ref, sched, cfg=CFG)
    assert len(paths) >= 30 and (paths["k-12"] == 0).all() and paths["dose"].between(0, 2).all()
    r = paths.iloc[10]
    L = sched.set_index("month").at[r["month"], "L"]
    i = SESS.get_loc(L)
    x = (ref["r_es"] - ref["r_zn"]).to_numpy()
    sig = (ref["r_es"] - ref["r_zn"]).pipe(lambda v: __import__("gqh.signals", fromlist=["x"]).ewma_sigma(v, CFG.ewma_lambda))
    expected = r["s"] * x[i - 11: i + 2].sum() / sig.iloc[i - 12]          # through F1 = L+1
    assert r["k+1"] == pytest.approx(expected)
    prof = G.path_profile(paths)
    assert "events" in prof.columns and prof["events"].sum() == len(paths)


def test_legs_direction_and_action_ledger_add_up():
    led = pd.DataFrame({"traded": [True, True, False], "s": [1, -1, 1], "pnl": [90.0, -40.0, 0.0], "cost": [10.0, 10.0, 0.0],
                        "pnl_es": [150.0, -80.0, 0.0], "pnl_zn": [-50.0, 50.0, 0.0],
                        "month": pd.PeriodIndex(["2016-01", "2016-02", "2016-03"], freq="M"), "sample": "IS"})
    t = G.legs_direction(led)
    assert t.loc[1, "gross"] == 100.0 and t.loc[-1, "net"] == -40.0 and t["events"].sum() == 2
    gate = pd.DataFrame({"yhat": [0.05, 0.02, -0.01], "hurdle": [0.01, 0.01, 0.01], "trade": [True, True, False]})
    sig = pd.DataFrame({"Y": [0.3, -0.2, 0.1]})
    a = G.action_ledger(led, gate, sig)
    assert a["forecast_error_x_position"].tolist() == pytest.approx([0.25, -0.22, 0.0])
