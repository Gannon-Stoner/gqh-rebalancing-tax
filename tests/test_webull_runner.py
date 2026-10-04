"""Judge runner rejects corrupt inputs and cannot conceal event-level mismatches."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("backtrader")
pytest.importorskip("webull")
pytest.importorskip("dotenv")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gqh_webull_runner", ROOT / "scripts" / "webull_backtest.py")
W = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = W
spec.loader.exec_module(W)


@pytest.fixture
def inputs():
    sessions = pd.bdate_range("2020-01-27", periods=3)
    ledger = pd.DataFrame([dict(month=pd.Period("2020-01", "M"), sample="IS", entry=sessions[0],
                                exit=sessions[-1], traded=True, es_id=1, zn_id=2, q_es=1, q_zn=-1,
                                gross_nav=0.03, cost=10.0, pnl=90.0)])
    prices = pd.DataFrame([dict(root=root, instrument_id=iid, date=day, settle=price)
                           for root, iid, price in (("ES", 1, 3000.0), ("ZN", 2, 130.0)) for day in sessions])
    return W.Inputs({"PG": ledger.copy(), "P0": ledger.copy()}, prices, sessions, "test")


def test_complete_holding_prices_are_required_even_for_interior_days(inputs):
    W.validate_inputs(inputs)
    inputs.prices = inputs.prices.drop(1)  # an interior held date, not entry or exit
    with pytest.raises(ValueError, match="missing holding-day settlement"):
        W.validate_inputs(inputs)


@pytest.mark.parametrize("price", [float("nan"), float("inf"), 0.0])
def test_nonfinite_or_nonpositive_settlement_is_rejected(inputs, price):
    inputs.prices.loc[0, "settle"] = price
    with pytest.raises(ValueError, match="finite and positive"):
        W.validate_inputs(inputs)


def test_no_trade_row_cannot_smuggle_pnl_into_replay(inputs):
    inputs.ledgers["PG"].loc[0, "traded"] = False
    with pytest.raises(ValueError, match="non-traded event"):
        W.validate_inputs(inputs)


def test_offsetting_event_errors_fail_even_when_total_pnl_matches():
    months = pd.period_range("2020-01", periods=2, freq="M")
    engine = pd.Series([1000.0, 2000.0], index=months)
    replay = pd.Series([1000.05, 1999.95], index=months)
    assert engine.sum() == replay.sum()
    failures = []
    W.reconcile_events("PG", engine, replay, failures)
    assert failures == ["PG: 2/2 event P&Ls differ by more than $0.01 or are missing"]


def test_missing_zero_pnl_event_is_still_a_failure():
    engine = pd.Series([0.0], index=pd.period_range("2020-01", periods=1, freq="M"))
    failures = []
    W.reconcile_events("PG", engine, engine.iloc[:0], failures)
    assert len(failures) == 1


def test_cli_default_is_replay_and_write_requires_data():
    assert not W.parse_args([]).data
    assert W.parse_args(["--replay"]).replay
    assert W.parse_args(["--data", "--write-replay"]).write_replay
    for argv in (["--replay", "--data"], ["--write-replay"], ["--repaly"]):
        with pytest.raises(SystemExit) as exc:
            W.parse_args(argv)
        assert exc.value.code == 2


def test_data_mode_does_not_silently_fall_back_to_replay(monkeypatch):
    monkeypatch.setattr(W, "_settlement_panels", lambda: None)
    with pytest.raises(SystemExit, match="DATA MISSING"):
        W.main(["--data"])
