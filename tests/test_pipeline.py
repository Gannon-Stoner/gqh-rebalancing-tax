"""End to end on synthetic contract chains with rolls (gqh.pipeline, gqh.reproduce; protocol §8 test 10)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from gqh import synth
from gqh.calendar import xnys_sessions
from gqh.config import frozen_config
from gqh.contracts import roll_table
from gqh.pipeline import evaluate, prepare
from gqh.reproduce import clean, dumps

CFG = frozen_config()
SESS = xnys_sessions("2010-06-07", "2016-12-30")


def _world_inputs():
    panels = {r: synth.synthetic_contract_chain(SESS, root=r, multiplier=m, seed=s).assign(volume_1m=v)
              for r, m, s, v in (("ES", 50.0, 21, 1.5e6), ("ZN", 1000.0, 22, 8e5))}
    quotes, bars = [], []
    for root, h, vols in (("ES", 0.125, {"14:59": 30_000, "15:59": 40_000, "16:14": 25_000}),
                          ("ZN", 1 / 128, {"14:59": 9_000, "15:59": 1_500, "16:14": 300})):
        p = panels[root]
        t = p["date"] + pd.Timedelta(hours=15, minutes=59)
        quotes.append(pd.DataFrame({"ts_et": t, "instrument_id": p["instrument_id"], "bid_px_00": p["settle"] - h,
                                    "ask_px_00": p["settle"] + h, "bid_sz_00": 10, "ask_sz_00": 10}))
        for hhmm, v in vols.items():
            bars.append(pd.DataFrame({"ts_et": p["date"] + pd.Timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[3:])),
                                      "instrument_id": p["instrument_id"], "volume": float(v)}))
    return panels, pd.concat(quotes, ignore_index=True), pd.concat(bars, ignore_index=True)


@pytest.fixture(scope="module")
def outputs():
    panels, bbo, ohlcv = _world_inputs()
    world = prepare(panels, cfg=CFG)
    return world, bbo, ohlcv, evaluate(world, bbo, ohlcv, cfg=CFG, draws=199)


def test_results_cover_the_registered_outputs(outputs):
    world, _, _, res = outputs
    assert set(res["confirmatory"]) == {"H1", "H2", "holm", "mde"}
    assert set(res["confirmatory"]["H1"]) == {"month_block", "wild", "newey_west"}
    rows = res["rows_IS"]["rows"]
    assert set(rows) == {f"{r}@{k}x" for r in ("PG", "P0", "PD", "PE", "PX", "PP") for k in ("1", "2")}
    assert all(len(v) == res["rows_IS"]["n_months"] for v in res["rows_IS"]["monthly_returns_1x"].values())
    assert rows["P0@1x"]["trades"] > 0 and set(res["rows_IS"]["delta_sharpe"]) >= {"PG-P0@1x", "PG-PE@2x"}
    assert res["rows_IS"]["capacity"]["PG_settle_windows"]["binding_leg_share"]
    assert res["sample_counts"]["IS"]["valid_events"] == int(world.events["valid"].sum())
    assert res["oos_slopes"]["b"]["OOS"] is None and res["oos_slopes"]["b"]["mde_oos_at_24_months"] > 0
    risk = res["risk_IS"]
    assert {"PG", "P0", "impact_PG", "stress_P0_all"} <= set(risk) and len(risk["PG"]["stress"]) == 6
    stress = {r["period"]: r for r in risk["stress_P0_all"]}
    assert stress["2011-08"]["events"] == 1                                 # before the walk-forward segment
    assert stress["2022"]["events"] == 0                                    # outside this synthetic sample
    sharpe_by_nav = [r["sharpe"] for r in risk["impact_PG"]]
    assert all(a >= b for a, b in zip(sharpe_by_nav, sharpe_by_nav[1:]))     # impact only erodes with size
    assert set(res["diagnostics"]) == {"event_path_by_era", "legs_direction", "action_ledger_PG", "benchmark_clock"}


def test_rolls_never_leak_into_returns(outputs):
    """The chains carry a 5% basis jump between contracts; on roll dates returns stay ordinary."""
    world, *_ = outputs
    r = world.ref[["r_es", "r_zn"]].iloc[1:]
    assert r.notna().all().all()
    rolls = roll_table(world.ref)
    assert len(rolls) >= 40
    for leg in ("ES", "ZN"):
        on_roll = r.loc[rolls.loc[rolls["leg"] == leg, "date"], f"r_{leg.lower()}"].abs()
        assert on_roll.max() < 0.04


def test_two_runs_are_byte_identical(outputs):
    world, bbo, ohlcv, res = outputs
    again = evaluate(world, bbo, ohlcv, cfg=CFG, draws=199)
    assert dumps(res) == dumps(again)
    assert json.loads(dumps(res))["protocol"]["seed"] == CFG.seed


def test_clean_rounds_and_nulls():
    assert clean({"a": np.float64(1 / 3), "b": np.nan, "c": [np.int64(2), True]}) == \
        {"a": 0.3333333333, "b": None, "c": [2, True]}
