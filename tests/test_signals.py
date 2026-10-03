"""Signals: drift, sigma_hat, dose, direction, progress A and outcome Y (gqh.signals)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import synth
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions
from gqh.contracts import ContractPanel, reference_returns
from gqh.signals import compute_signals, drift, ewma_sigma, required_equity_trade, stacked_panel

SESS = xnys_sessions("2010-06-07", "2014-12-31")
SCHED = trading_schedule(SessionCalendar(SESS))
DECISION_COLS = ["D", "sigma", "z", "dose", "s", "A", "X_progress", "es_id", "zn_id"]


def build(legs: pd.DataFrame, upto: pd.Timestamp | None = None, drop_zn_settle: pd.Timestamp | None = None):
    """Signals for events and pseudo-events from daily leg returns (one perpetual contract per leg).

    ``drop_zn_settle`` removes the ZN settlement on that date (a data gap).
    """
    if upto is not None:
        legs = legs[legs.index <= upto]
    es_long = synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0)
    zn_long = synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0)
    if drop_zn_settle is not None:
        zn_long = zn_long[zn_long["date"] != drop_zn_settle]
    es = ContractPanel.from_long(es_long, "ES")
    zn = ContractPanel.from_long(zn_long, "ZN")
    ref = reference_returns(es, zn, legs.index)
    ev = compute_signals(SCHED, ref, es, zn, kind="event").set_index("month")
    ps = compute_signals(SCHED, ref, es, zn, kind="pseudo").set_index("month")
    return ev, ps


@pytest.fixture(scope="module")
def legs():
    return synth.protocol_null_legs(SESS, "base", seed=20261003)


@pytest.fixture(scope="module")
def base(legs):
    return build(legs)


def _sum(r: pd.Series, a, b) -> float:
    return float(r[(r.index > a) & (r.index <= b)].sum())


# --- accounting --------------------------------------------------------------

def test_drift_and_required_trade_match_a_brute_force_6040_portfolio():
    rng = np.random.default_rng(1)
    for R_E, R_B in rng.uniform(-0.3, 0.3, size=(200, 2)):
        E, B = 0.6 * (1 + R_E), 0.4 * (1 + R_B)
        assert drift(R_E, R_B) == pytest.approx(E / (E + B) - 0.6, abs=1e-14)
        assert required_equity_trade(1.0, R_E, R_B) == pytest.approx(0.6 * (E + B) - E, abs=1e-14)


def test_textbook_examples():
    assert required_equity_trade(100.0, 0.10, 0.0) == pytest.approx(-2.40)   # sell $2.40 of stocks
    assert required_equity_trade(100.0, -0.10, 0.0) == pytest.approx(2.40)   # buy $2.40
    assert drift(0.02, 0.05) < 0                                              # stocks lagged: buy ES, s=+1


# --- sigma_hat -----------------------------------------------------------------

def test_ewma_sigma_recursion_warmup_and_missing_values():
    x = pd.Series(np.random.default_rng(2).normal(0, 0.01, 120))
    sig = ewma_sigma(x, 0.94, seed_obs=21, min_obs=63)
    var = np.mean(x.iloc[:21] ** 2)
    for v in x.iloc[21:63]:
        var = 0.94 * var + 0.06 * v * v
    assert sig.iloc[:62].isna().all() and sig.iloc[62] == pytest.approx(np.sqrt(var))
    x2 = x.copy()
    x2.iloc[80] = np.nan
    s2 = ewma_sigma(x2, 0.94)
    assert s2.iloc[80] == pytest.approx(s2.iloc[79])          # no update, no fill
    x3 = x.copy()
    x3.iloc[100] += 0.05
    s3 = ewma_sigma(x3, 0.94)
    pd.testing.assert_series_equal(s3.iloc[:100], sig.iloc[:100])   # data through t only
    assert s3.iloc[100] != sig.iloc[100]


# --- formulas ----------------------------------------------------------------

@pytest.mark.parametrize("kind", ["event", "pseudo"])
def test_signal_columns_match_first_principles(base, legs, kind):
    df = base[0] if kind == "event" else base[1]
    x = legs["r_es"] - legs["r_zn"]
    sig = ewma_sigma(x.where(x.index > SESS[0]), 0.94)
    v = df[df["valid"]]
    assert len(v) >= 0.9 * len(df) - 3
    for m, r in v.iterrows():
        prev_L = SCHED.set_index("month").at[m, "prev_L"]
        R_E, R_B = np.expm1(_sum(legs["r_es"], prev_L, r.dec)), np.expm1(_sum(legs["r_zn"], prev_L, r.dec))
        D = 0.24 * (R_E - R_B) / (1 + 0.6 * R_E + 0.4 * R_B)
        assert r.D == pytest.approx(D, rel=1e-10)
        assert r.sigma == pytest.approx(sig[r.dec], rel=1e-10)
        z = D / (0.24 * r.sigma * np.sqrt(r.n))
        assert r.z == pytest.approx(z, rel=1e-10) and r.dose == pytest.approx(min(abs(z), 2.0))
        assert r.s == -np.sign(D)
        assert r.A == pytest.approx(r.s * _sum(x, r.progress_start, r.dec) / (r.sigma * np.sqrt(3)), rel=1e-9)
        assert r.Y == pytest.approx(r.s * _sum(x, r.entry, r.exit) / (r.sigma * np.sqrt(5)), rel=1e-9)


def test_event_and_pseudo_windows_are_the_registered_offsets(base):
    ev, ps = base
    s = SCHED.set_index("month")
    for m, r in ev[ev["valid"]].iterrows():
        assert (r.progress_start, r.dec, r.entry, r.exit) == (s.at[m, "L_m8"], s.at[m, "L_m5"], s.at[m, "L_m4"], s.at[m, "F1"])
        assert r.n == s.at[m, "n_since_prev_L"]
    for m, r in ps[ps["valid"]].iterrows():
        assert (r.progress_start, r.dec, r.entry, r.exit) == (s.at[m, "L_m17"], s.at[m, "L_m14"], s.at[m, "L_m13"], s.at[m, "pseudo_exit"])
        assert r.n == s.at[m, "n_since_prev_L_pseudo"]


# --- timing --------------------------------------------------------------------

def test_impulse_lands_only_in_its_window(legs, base):
    ev0 = base[0]
    m = ev0[ev0["valid"]].index[20]
    row = SCHED.set_index("month").loc[m]
    nxt = SESS[SESS.get_loc(row["F1"]) + 1]
    # date: (expected change in X_progress, expected change in X_hold)
    cases = {row["L_m8"]: (0, 0), SESS[SESS.get_loc(row["L_m8"]) + 1]: (1, 0), row["L_m5"]: (1, 0),
             row["L_m4"]: (0, 0), SESS[SESS.get_loc(row["L_m4"]) + 1]: (0, 1), row["F1"]: (0, 1), nxt: (0, 0)}
    for day, (dp, dh) in cases.items():
        bumped = legs.copy()
        bumped.loc[day, "r_es"] += 0.004
        ev1 = build(bumped)[0]
        assert ev1.at[m, "X_progress"] - ev0.at[m, "X_progress"] == pytest.approx(0.004 * dp, abs=1e-12), day
        assert ev1.at[m, "X_hold"] - ev0.at[m, "X_hold"] == pytest.approx(0.004 * dh, abs=1e-12), day


@pytest.mark.parametrize("kind,dec_col", [("event", "L_m5"), ("pseudo", "L_m14")])
def test_decision_inputs_use_no_data_after_the_decision(legs, base, kind, dec_col):
    full = base[0] if kind == "event" else base[1]
    months = full[full["valid"]].index[[3, 12, 25, 40]]
    for m in months:
        cut = SCHED.set_index("month").at[m, dec_col]
        trunc = build(legs, upto=cut)[0 if kind == "event" else 1]
        for c in DECISION_COLS:
            assert trunc.at[m, c] == pytest.approx(full.at[m, c], rel=1e-12, nan_ok=True), (m, c)
        assert np.isnan(trunc.at[m, "Y"]) and not trunc.at[m, "valid"]


# --- planted effects and invalid rows -----------------------------------------

def test_planted_holding_move_appears_exactly_in_X_hold(legs, base):
    ev0 = base[0]
    planted = synth.plant_event_effect(legs, SCHED, 0.01, entry_col="L_m4", exit_col="F1")
    ev1 = build(planted)[0]
    both = ev0["valid"] & ev1["valid"]
    assert both.sum() >= 40
    assert np.allclose(ev1.loc[both, "X_hold"] - ev0.loc[both, "X_hold"], 0.01, atol=1e-12)


def test_zero_drift_and_missing_returns_invalidate_only_their_month(legs, base):
    ev0 = base[0]
    m = ev0[ev0["valid"]].index[15]
    row = SCHED.set_index("month").loc[m]
    window = (legs.index > row["prev_L"]) & (legs.index <= row["L_m5"])
    flat = legs.copy()
    flat.loc[window, ["r_es", "r_zn"]] = 0.0
    ev_flat = build(flat)[0]
    assert ev_flat.at[m, "D"] == 0 and ev_flat.at[m, "s"] == 0 and not ev_flat.at[m, "valid"]
    ev_gap = build(legs, drop_zn_settle=SESS[SESS.get_loc(row["L_m5"]) - 3])[0]
    assert np.isnan(ev_gap.at[m, "D"]) and not ev_gap.at[m, "valid"]
    other = ev0[ev0["valid"]].index[25]
    assert ev_gap.at[other, "valid"]


def test_stacked_panel_flags_events_and_pseudo_events(base):
    ev, ps = base
    st = stacked_panel(ev.reset_index(), ps.reset_index())
    assert (st["ME"] == 1).sum() == ev["valid"].sum() and (st["ME"] == 0).sum() == ps["valid"].sum()
    assert list(st.columns) == ["month", "sample", "QE", "dose", "A", "Y", "ME"]
