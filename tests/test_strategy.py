"""The six strategy rows on synthetic data (gqh.strategy)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import synth
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions
from gqh.config import frozen_config
from gqh.contracts import ContractPanel, reference_returns
from gqh.signals import compute_signals
from gqh.strategy import run_strategy

CFG = frozen_config()
SESS = xnys_sessions("2010-06-07", "2019-12-31")


@pytest.fixture(scope="module")
def world():
    legs = synth.protocol_null_legs(SESS, "base", seed=11)
    es = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0), "ES")
    zn = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0), "ZN")
    sched = trading_schedule(SessionCalendar(SESS))
    ref = reference_returns(es, zn, SESS)
    ev = compute_signals(sched, ref, es, zn, kind="event")
    ps = compute_signals(sched, ref, es, zn, kind="pseudo")

    def quote(iid, ts):
        s = (es if iid == 1 else zn).price(iid, ts.normalize())
        h = 0.125 if iid == 1 else 1 / 128
        return (s - h, s + h) if np.isfinite(s) else None

    return ev, ps, es, zn, run_strategy(ev, ps, es, zn, quote=quote, cfg=CFG)


def test_every_row_and_cost_multiplier_has_a_ledger(world):
    ev, ps, _, _, run = world
    assert set(run.ledgers) == {(r, k) for r in ("PG", "P0", "PD", "PE", "PX", "PP") for k in (1.0, 2.0)}
    for (row, _), led in run.ledgers.items():
        assert len(led) == len(ps if row == "PP" else ev)


def test_nothing_trades_before_the_common_walk_forward_segment(world):
    ev, ps, _, _, run = world
    assert run.gates["PG"].loc[(ev["month"] >= run.segment_start).to_numpy(), "n_train"].min() >= CFG.min_events
    assert run.gates["PP"].loc[(ps["month"] >= run.segment_start).to_numpy(), "n_train"].min() >= CFG.min_events
    for led in run.ledgers.values():
        assert not led.loc[led["month"] < run.segment_start, "traded"].any()
    assert run.ledgers[("P0", 1.0)]["traded"].sum() >= 30


def test_row_relationships(world):
    ev, _, _, _, run = world
    pg, p0, px, pe = (run.ledgers[(r, 1.0)] for r in ("PG", "P0", "PX", "PE"))
    assert not (pg["traded"] & ~p0["traded"]).any()                   # PG trades a subset of P0
    assert not (px["traded"] & ~pg["traded"]).any()                   # PX takes PG's decisions
    seg = (p0["month"] >= run.segment_start) & (p0["sample"] == "IS")
    assert run.participation == pytest.approx((pg["traded"] & seg).sum() / (p0["traded"] & seg).sum())
    both = pe["traded"] & p0["traded"]
    assert np.allclose(pe.loc[both, "notional"], run.participation * p0.loc[both, "notional"])
    for row in ("PG", "P0", "PD", "PE", "PP"):
        a, b = run.ledgers[(row, 1.0)], run.ledgers[(row, 2.0)]
        assert (a["traded"] == b["traded"]).all() and np.allclose(b["cost"], 2 * a["cost"])
