"""Backtrader replay of engine trades matches the engine to the cent (gqh.bt_replay)."""

from __future__ import annotations

import numpy as np
import pytest

bt = pytest.importorskip("backtrader")

from gqh import bt_replay as B  # noqa: E402
from gqh import engine as E  # noqa: E402
from gqh import synth  # noqa: E402
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions  # noqa: E402
from gqh.config import frozen_config  # noqa: E402
from gqh.contracts import ContractPanel, reference_returns  # noqa: E402
from gqh.signals import compute_signals  # noqa: E402

CFG = frozen_config()
SESS = xnys_sessions("2010-06-07", "2012-12-31")


@pytest.mark.parametrize("k", [1.0, 2.0])
def test_backtrader_reproduces_the_engine_pnl(k):
    legs = synth.protocol_null_legs(SESS, "base", seed=5)
    es = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0), "ES")
    zn = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0), "ZN")
    sig = compute_signals(trading_schedule(SessionCalendar(SESS)), reference_returns(es, zn, SESS), es, zn, kind="event")
    led = E.run_row(sig, E.size_events(sig, es, zn, cfg=CFG), sig["valid"].to_numpy(), row="P0", k=k, cfg=CFG)
    rep = B.replay_ledger(led, sig, es, zn, SESS, k=k, cfg=CFG)
    s = B.reconciliation_summary(rep)
    assert s["events"] >= 20 and s["all_fills"]
    assert s["matched"] == s["events"], rep.loc[rep["diff"].abs() > 0.01].head()
