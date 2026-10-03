"""Engine: sizing, costs, fills, ledger and daily P&L (gqh.engine)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import engine as E
from gqh import synth
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions
from gqh.config import frozen_config
from gqh.contracts import ContractPanel, reference_returns
from gqh.signals import compute_signals
from gqh.testing import assert_pnl_matches_window, assert_pnl_only_in_window

CFG = frozen_config()
NAV = CFG.reference_nav
SESS = xnys_sessions("2010-06-07", "2012-12-31")
SCHED = trading_schedule(SessionCalendar(SESS))


def build(legs: pd.DataFrame):
    """(signals, sized, es, zn) for events on one perpetual contract per leg."""
    es = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0), "ES")
    zn = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0), "ZN")
    ref = reference_returns(es, zn, legs.index)
    sig = compute_signals(SCHED, ref, es, zn, kind="event")
    return sig, E.size_events(sig, es, zn, cfg=CFG), es, zn


@pytest.fixture(scope="module")
def base():
    return build(synth.protocol_null_legs(SESS, "base", seed=20261003))


# --- pure helpers --------------------------------------------------------------

def test_leg_notional_targets_kappa_risk_at_full_dose_and_caps_per_leg():
    sigma = 0.012
    n = E.leg_notional(2.0, sigma, cfg=CFG)
    assert n * sigma * np.sqrt(5) == pytest.approx(CFG.kappa * NAV)          # full dose: 5-day risk = kappa NAV
    assert E.leg_notional(1.0, sigma, cfg=CFG) == pytest.approx(n / 2)
    assert E.leg_notional(2.0, 0.001, cfg=CFG) == pytest.approx(0.75 * NAV)  # per-leg cap binds
    assert E.leg_notional(1.0, sigma, cfg=CFG, scale=0.5) == pytest.approx(n / 4)
    assert np.isnan(E.leg_notional(np.nan, sigma, cfg=CFG))


def test_contracts_round_half_up_and_never_exceed_the_cap():
    assert E.contracts_for(250_000.0, 2000.0, 50.0) == (3, 2.5)                # 2.5 -> 3
    assert E.contracts_for(240_000.0, 2000.0, 50.0)[0] == 2
    assert E.contracts_for(1_000_000.0, 2000.0, 50.0, cap_usd=950_000.0)[0] == 9
    assert E.contracts_for(1_000.0, np.nan, 50.0) == (0, pytest.approx(np.nan, nan_ok=True))


def test_costs_per_side_settlement_and_executable():
    assert E.side_cost("ES", cfg=CFG) == 6.25 + 2.5
    assert E.side_cost("ZN", k=2.0, cfg=CFG) == 2 * (7.8125 + 2.5)
    assert E.side_cost("ES", executable=True, cfg=CFG) == 2.5                  # spread paid in the fill
    assert E.side_cost("ZN", k=2.0, executable=True, cfg=CFG) == 2 * 2.5 + 7.8125
    assert E.round_trip_cost(3, 5, cfg=CFG) == pytest.approx(2 * (3 * 8.75 + 5 * 10.3125))


def test_cost_hurdle_is_cost_in_position_risk_units():
    notional, sigma, cost = 1_500_000.0, 0.012, 155.625
    c = E.cost_hurdle(cost, notional, sigma)
    assert c * notional * sigma * np.sqrt(5) == pytest.approx(cost)
    assert np.isnan(E.cost_hurdle(cost, 0.0, sigma))


def test_early_execution_savings_sign_convention():
    assert E.early_execution_savings_bp(+1, 100.0, 101.0) == pytest.approx(100.0)   # bought before the rise
    assert E.early_execution_savings_bp(-1, 100.0, 101.0) == pytest.approx(-100.0)  # sold before the rise


# --- sizing and ledger -----------------------------------------------------------

def test_sizing_uses_decision_settles_and_flags_below_one_lot(base):
    sig, sized, es, zn = base
    ok = sig["valid"].to_numpy() & ~sized["below_one_lot"].to_numpy()
    assert ok.sum() >= 20
    for i in np.flatnonzero(ok)[:10]:
        r, z = sig.iloc[i], sized.iloc[i]
        assert z["es_size_px"] == es.price(int(r["es_id"]), r["dec"])
        assert z["n_es"] == int(np.floor(z["notional"] / (z["es_size_px"] * 50) + 0.5))
        assert z["hurdle"] == pytest.approx(z["cost_1x"] / (z["notional"] * r["sigma"] * np.sqrt(5)))
    tiny = sig.copy()
    tiny["dose"] = 1e-4
    assert E.size_events(tiny, es, zn, cfg=CFG)["below_one_lot"].all()


def test_ledger_signs_costs_and_rounding(base):
    sig, sized, es, zn = base
    led = E.run_row(sig, sized, np.ones(len(sig), bool), row="P0", cfg=CFG)
    t = led[led["traded"]]
    assert len(t) == int((sig["valid"] & ~sized["below_one_lot"]).sum())
    assert (np.sign(t["q_es"]) == t["s"]).all() and (np.sign(t["q_zn"]) == -t["s"]).all()
    for _, x in t.head(10).iterrows():
        pnl_es = x["q_es"] * 50 * (x["es_out"] - x["es_in"])
        pnl_zn = x["q_zn"] * 1000 * (x["zn_out"] - x["zn_in"])
        cost = E.round_trip_cost(x["n_es"], x["n_zn"], cfg=CFG)
        assert x["pnl"] == pytest.approx(pnl_es + pnl_zn - cost)
        assert x["ret"] == pytest.approx(x["pnl"] / NAV)
    led2 = E.run_row(sig, sized, np.ones(len(sig), bool), row="P0", k=2.0, cfg=CFG)
    assert (led2["cost"] == 2 * led["cost"]).all()
    assert (led.loc[~led["traded"], ["pnl", "cost", "n_es", "n_zn"]] == 0).all().all()
    assert set(led.loc[~led["traded"], "reason"]) <= {"invalid", "below_one_lot"}


def test_ledger_respects_the_decisions(base):
    sig, sized, _, _ = base
    trade = np.zeros(len(sig), bool)
    trade[::2] = True
    led = E.run_row(sig, sized, trade, row="PG", cfg=CFG)
    assert not led.loc[~trade, "traded"].any()
    assert (led.loc[~trade & sig["valid"].to_numpy(), "reason"] == "not_selected").all()


# --- timing: impulse (protocol §8 test 1) and daily marking ------------------------

def _with_prices(sig: pd.DataFrame, es: ContractPanel, zn: ContractPanel) -> pd.DataFrame:
    """Signals whose entry/exit settles are re-read from other price panels (same perpetual ids)."""
    out = sig.copy()
    for leg, panel in (("es", es), ("zn", zn)):
        for when in ("entry", "exit"):
            out[f"{leg}_{when}"] = [panel.price(int(i), d) if pd.notna(i) and pd.notna(d) else np.nan
                                    for i, d in zip(sig[f"{leg}_id"], sig[when])]
    return out


@pytest.mark.parametrize("leg", ["es", "zn"])
@pytest.mark.parametrize("where", ["decision", "entry", "first_hold", "exit", "after_exit"])
def test_an_impulse_shows_up_in_pnl_only_inside_the_holding_window(base, leg, where):
    """Windows come from the schedule (L-4, F1], not from the engine's own columns."""
    sig, sized, _, _ = base
    sched = SCHED.set_index("month")
    led0 = E.run_row(sig, sized, np.ones(len(sig), bool), row="P0", k=0.0, cfg=CFG)
    m = led0.loc[led0["traded"], "month"].iloc[5]
    L4, F1 = sched.at[m, "L_m4"], sched.at[m, "F1"]
    day = {"decision": sched.at[m, "L_m5"], "entry": L4, "first_hold": SESS[SESS.get_loc(L4) + 1],
           "exit": F1, "after_exit": SESS[SESS.get_loc(F1) + 1]}[where]
    legs = synth.impulse_returns(SESS, day, 0.01, leg=leg)
    es_i = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0), "ES")
    zn_i = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0), "ZN")
    sig_i = _with_prices(sig, es_i, zn_i)
    led = E.run_row(sig_i, sized, np.ones(len(sig), bool), row="P0", k=0.0, cfg=CFG)
    daily = E.daily_pnl(led, sig_i, es_i, zn_i, SESS, cfg=CFG)["gross"]
    t = led[led["traded"]]
    lo, hi = sched.loc[t["month"], "L_m4"].to_numpy(), sched.loc[t["month"], "F1"].to_numpy()
    col, mult, p0 = ("r_es", 50.0, 2000.0) if leg == "es" else ("r_zn", 1000.0, 120.0)
    pos_usd = ((t["q_es"] if leg == "es" else t["q_zn"]) * mult * p0).to_numpy()
    assert_pnl_only_in_window(daily, lo, hi, atol=1e-6)
    assert_pnl_matches_window(daily, np.expm1(legs[col]), lo, hi, position=pos_usd, atol=1e-6)
    inside = (lo < day) & (day <= hi)
    assert np.allclose(t["pnl"].to_numpy(), np.where(inside, pos_usd * np.expm1(0.01 if leg == "es" else -0.01), 0.0), atol=1e-6)
    assert (where in ("first_hold", "exit")) == bool(inside[list(t["month"]).index(m)])


def test_daily_pnl_sums_to_the_ledger(base):
    sig, sized, es, zn = base
    led = E.run_row(sig, sized, np.ones(len(sig), bool), row="P0", k=1.0, cfg=CFG)
    daily = E.daily_pnl(led, sig, es, zn, SESS, cfg=CFG)
    assert daily["net"].sum() == pytest.approx(led["pnl"].sum(), rel=1e-12, abs=1e-6)
    assert daily["cost"].sum() == pytest.approx(led["cost"].sum())


# --- executable fills (PX) -----------------------------------------------------------

def _quotes(es: ContractPanel, zn: ContractPanel, half: dict[int, float], missing: set = frozenset()):
    """Quote function: bid/ask = settle -/+ half-width on each date; ``missing`` holds (iid, date) without a quote."""
    def quote(iid: int, ts: pd.Timestamp):
        day = ts.normalize()
        assert ts - day == E.FILL_MINUTE
        if (iid, day) in missing:
            return None
        s = (es if iid == 1 else zn).price(iid, day)
        return (s - half[iid], s + half[iid]) if np.isfinite(s) else None
    return quote


def test_px_buys_at_the_ask_sells_at_the_bid_and_pays_fees_only(base):
    sig, sized, es, zn = base
    half = {1: 0.125, 2: 1 / 128}
    trade = np.ones(len(sig), bool)
    settle = E.run_row(sig, sized, trade, row="PG", k=0.0, cfg=CFG)
    px = E.run_row(sig, sized, trade, row="PX", k=1.0, cfg=CFG, executable=True, quote=_quotes(es, zn, half))
    both = settle["traded"] & px["traded"]
    assert both.sum() >= 20
    for i in np.flatnonzero(both)[:10]:
        a, b = settle.iloc[i], px.iloc[i]
        crossing = abs(b["q_es"]) * 50 * 2 * half[1] + abs(b["q_zn"]) * 1000 * 2 * half[2]
        fees = 2 * 2.5 * (abs(b["q_es"]) + abs(b["q_zn"]))
        assert b["pnl"] == pytest.approx(a["pnl"] - crossing - fees)
        side = 1 if b["q_es"] > 0 else -1                                    # long pays the ask, short gets the bid
        assert b["es_in"] == pytest.approx(es.price(1, b["entry"]) + side * half[1])
        assert b["es_out"] == pytest.approx(es.price(1, b["exit"]) - side * half[1])
    daily = E.daily_pnl(px, sig, es, zn, SESS, cfg=CFG)
    assert daily["net"].sum() == pytest.approx(px["pnl"].sum(), abs=1e-6)


def test_px_missing_quotes_skip_entry_or_fall_back_at_exit(base):
    sig, sized, es, zn = base
    half = {1: 0.125, 2: 1 / 128}
    trade = np.ones(len(sig), bool)
    ok = np.flatnonzero((sig["valid"] & ~sized["below_one_lot"] & sig["px_eligible"]).to_numpy())
    i_entry, i_exit = ok[0], ok[1]
    missing = {(2, sig.iloc[i_entry]["entry"]), (1, sig.iloc[i_exit]["exit"])}
    px = E.run_row(sig, sized, trade, row="PX", cfg=CFG, executable=True, quote=_quotes(es, zn, half, missing))
    assert px.iloc[i_entry]["reason"] == "no_entry_quote" and not px.iloc[i_entry]["traded"]
    x = px.iloc[i_exit]
    assert x["traded"] and x["px_exit_fallback"]
    assert x["es_out"] == es.price(1, x["exit"])
    expected_cost = abs(x["q_es"]) * (2.5 + 8.75) + abs(x["q_zn"]) * (2.5 + 2.5)
    assert x["cost"] == pytest.approx(expected_cost)
    ineligible = sig.copy()
    ineligible["px_eligible"] = False
    px2 = E.run_row(ineligible, sized, trade, row="PX", cfg=CFG, executable=True, quote=_quotes(es, zn, half))
    assert set(px2.loc[sig["valid"].to_numpy() & ~sized["below_one_lot"].to_numpy(), "reason"]) == {"px_ineligible"}
    with pytest.raises(ValueError):
        E.run_row(sig, sized, trade, row="PX", cfg=CFG, executable=True)


def test_daily_pnl_and_replay_align_by_month_on_rolling_chains():
    """A ledger filtered to a later segment must still use each event's own contracts."""
    sess = xnys_sessions("2010-06-07", "2013-12-31")
    es = ContractPanel.from_long(synth.synthetic_contract_chain(sess, root="ES", multiplier=50.0, seed=31), "ES")
    zn = ContractPanel.from_long(synth.synthetic_contract_chain(sess, root="ZN", multiplier=1000.0, seed=32), "ZN")
    sched = trading_schedule(SessionCalendar(sess))
    sig = compute_signals(sched, reference_returns(es, zn, sess), es, zn, kind="event")
    led = E.run_row(sig, E.size_events(sig, es, zn, cfg=CFG), sig["valid"].to_numpy(), row="P0", cfg=CFG)
    assert sig.loc[led["traded"].to_numpy(), "es_id"].nunique() > 3           # several contracts are held
    later = led[led["month"] >= pd.Period("2012-01", "M")]
    daily = E.daily_pnl(later, sig, es, zn, sess, cfg=CFG)
    assert daily["net"].sum() == pytest.approx(later["pnl"].sum(), abs=1e-6)
