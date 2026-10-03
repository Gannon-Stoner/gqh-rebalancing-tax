"""Capacity from execution-window volume (gqh.capacity)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import capacity as K
from gqh.config import frozen_config

CFG = frozen_config()
T = pd.Timestamp


def test_window_bars_follow_the_settlement_clocks():
    assert K.window_bars("ZN", T("2019-03-01"), "settle") == [T("2019-03-01 14:59")]
    assert K.window_bars("ES", T("2019-03-01"), "settle") == [T("2019-03-01 16:14")]
    assert K.window_bars("ES", T("2021-03-01"), "settle") == [T("2021-03-01 15:59")]
    assert K.window_bars("ZN", T("2021-03-01"), "px") == [T("2021-03-01 15:59")]
    with pytest.raises(ValueError):
        K.window_bars("ES", T("2021-03-01"), "vwap")


def test_capacity_scales_with_the_binding_leg_and_the_one_lot_test():
    sig = pd.DataFrame({"es_id": [1, 1], "zn_id": [2, 2]})
    led = pd.DataFrame({"traded": [True, False], "month": pd.PeriodIndex(["2021-03", "2021-04"], freq="M"),
                        "entry": [T("2021-03-25"), T("2021-04-26")], "exit": [T("2021-04-01"), T("2021-05-03")],
                        "n_es": [10, 0], "n_zn": [20, 0]})
    vol = {1: pd.Series({T("2021-03-25 15:59"): 40_000.0, T("2021-04-01 15:59"): 30_000.0}),
           2: pd.Series({T("2021-03-25 14:59"): 9_000.0, T("2021-04-01 14:59"): 80.0})}
    tab = K.capacity_table(led, sig, vol, mode="settle", cfg=CFG)
    assert len(tab) == 1
    r = tab.iloc[0]
    assert r["vol_es"] == 30_000 and r["vol_zn"] == 80 and r["binding_leg"] == "ZN"
    assert r["max_nav_1pct"] == pytest.approx(CFG.reference_nav * 0.01 * 80 / 20)
    assert not r["lot_at_1pct"]                                   # 1% of 80 contracts < 1 lot
    px = K.capacity_table(led, sig, vol, mode="px", cfg=CFG).iloc[0]
    assert px["vol_zn"] == 0 and px["max_nav_10pct"] == 0.0       # no ZN bar at 15:59: zero capacity
    s = K.capacity_summary(tab)
    assert s["events"] == 1 and s["binding_leg_share"] == {"ZN": 1.0} and s["lot_at_1pct_share"] == 0.0
