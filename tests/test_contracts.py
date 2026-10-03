"""Contract selection and within-contract returns (gqh.contracts)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh import synth
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions
from gqh.contracts import ContractPanel, event_contracts, reference_returns, roll_table

SESS = xnys_sessions("2010-06-07", "2014-12-31")


@pytest.fixture(scope="module")
def world():
    es_long = synth.synthetic_contract_chain(SESS, root="ES", multiplier=50, seed=11, basis_noise=0.0)
    zn_long = synth.synthetic_contract_chain(SESS, root="ZN", multiplier=1000, seed=12, basis_noise=0.0)
    es, zn = ContractPanel.from_long(es_long, "ES"), ContractPanel.from_long(zn_long, "ZN")
    sched = trading_schedule(SessionCalendar(SESS))
    return {"es_long": es_long, "zn_long": zn_long, "es": es, "zn": zn, "sched": sched,
            "ref": reference_returns(es, zn, SESS)}


def _two_contract_panel(switch_day: int, n: int = 8) -> pd.DataFrame:
    """Contracts 1 (near) and 2 (far); 2 overtakes 1 in OI on ``switch_day``."""
    days = SESS[:n]
    rows = []
    for i, d in enumerate(days):
        rows.append({"date": d, "instrument_id": 1, "symbol": "ESU0", "expiration": pd.Timestamp("2010-09-17"),
                     "settle": 100.0 + i, "open_interest": 10 if i >= switch_day else 100})
        rows.append({"date": d, "instrument_id": 2, "symbol": "ESZ0", "expiration": pd.Timestamp("2010-12-17"),
                     "settle": 110.0 + 2 * i, "open_interest": 100 if i >= switch_day else 10})
    return pd.DataFrame(rows)


def test_zn_first_position_day_derived_from_expiration_matches_rule(world):
    zn_long = world["zn_long"].drop(columns=["first_position_day"])
    derived = ContractPanel.from_long(zn_long, "ZN").meta["first_position_day"]
    truth = world["zn_long"].groupby("instrument_id")["first_position_day"].first()
    inside = truth[(truth > SESS[0] + pd.Timedelta(days=10)) & (truth < SESS[-1] - pd.Timedelta(days=10))]
    assert len(inside) >= 15
    assert (derived.reindex(inside.index) == inside).all()


def test_reference_returns_are_within_contract(world):
    es, ref = world["es"], world["ref"]
    for prev, t in zip(SESS[:-1], SESS[1:]):
        iid = int(ref.at[t, "es_id"])
        assert ref.at[t, "r_es"] == pytest.approx(np.log(es.settle.at[t, iid] / es.settle.at[prev, iid]), abs=1e-15)


def test_reference_returns_have_no_roll_gap_but_naive_splice_does(world):
    es_long, ref = world["es_long"], world["ref"]
    # With basis_noise=0 every listed contract shares the common path up to a
    # tiny carry term, so any within-contract return is close to any other.
    piv = es_long.pivot(index="date", columns="instrument_id", values="settle")
    other = np.log(piv / piv.shift()).median(axis=1)
    assert (ref["r_es"] - other).abs().max() < 2e-3
    # A naive same-day highest-OI splice jumps by about the basis at each roll.
    front = es_long.loc[es_long.groupby("date")["open_interest"].idxmax()].set_index("date")["settle"]
    naive = np.log(front / front.shift())
    assert (naive - other).abs().max() > 0.03


def test_reference_contract_is_chosen_by_previous_session_oi():
    es = ContractPanel.from_long(_two_contract_panel(switch_day=3), "ES")
    zn = ContractPanel.from_long(_two_contract_panel(switch_day=3).assign(symbol="ZNU0"), "ZN",
                                 days=xnys_sessions("2010-01-01", "2011-06-30"))
    ref = reference_returns(es, zn, SESS[:8])
    assert ref["es_id"].iloc[3] == 1  # OI at day 2 still favors contract 1
    assert ref["es_id"].iloc[4] == 2
    assert ref["r_es"].iloc[3] == pytest.approx(np.log(103 / 102))
    assert ref["r_es"].iloc[4] == pytest.approx(np.log(118 / 116))


def test_zn_reference_never_holds_a_contract_at_or_after_first_position_day(world):
    zn, ref = world["zn"], world["ref"]
    fpd = zn.meta["first_position_day"]
    held = ref["zn_id"].dropna()
    assert all(fpd.at[int(i)] > d for d, i in held.items())


def test_event_contracts_follow_the_frozen_rules(world):
    es, zn, sched = world["es"], world["zn"], world["sched"]
    ec = event_contracts(sched, es, zn, SESS, kind="event")
    ok = ec[ec["tradable"] & ec["data_complete"]]
    assert len(ok) >= 0.9 * len(ec)
    for r in ok.itertuples():
        oi = es.oi.loc[r.anchor].dropna()
        assert r.es_id == oi.idxmax()                                  # ES: highest OI at L-8
        fpd = zn.meta.at[r.zn_id, "first_position_day"]
        assert fpd > r.exit                                            # ZN: FPD after F1
        listed = zn.settle.loc[r.anchor].dropna().index
        eligible = zn.meta.loc[listed]
        eligible = eligible[eligible["first_position_day"] > r.exit]
        assert r.zn_id == eligible["expiration"].idxmin()             # ...and the nearest such
    # Feb/May/Aug/Nov: the front ZN (delivery next month) has FPD before F1, so
    # the event holds the deferred contract.
    for r in ok[ok["month"].dt.month.isin([2, 5, 8, 11])].itertuples():
        delivery = zn.meta.at[r.zn_id, "expiration"]
        assert delivery.month != (r.month + 1).month


def test_pseudo_es_skips_a_contract_expiring_before_the_pseudo_exit(world):
    es, zn, sched = world["es"], world["zn"], world["sched"]
    ps = event_contracts(sched, es, zn, SESS, kind="pseudo")
    q = ps[ps["month"].dt.month.isin([3, 6, 9, 12]) & ps["es_id"].notna()]
    assert len(q) >= 10
    assert (q["es_expiration"] > q["exit"]).all() and q["tradable"].all()


def test_event_rule_is_strict_when_the_max_oi_contract_expires_before_exit():
    # Contract 1 keeps the higher OI but expires before the exit.
    panel = _two_contract_panel(switch_day=99, n=30)
    es = ContractPanel.from_long(panel.assign(expiration=panel["instrument_id"].map(
        {1: SESS[10], 2: pd.Timestamp("2010-12-17")})), "ES")
    zn = ContractPanel.from_long(panel.assign(symbol="ZN", first_position_day=pd.Timestamp("2011-01-01")), "ZN")
    sched = pd.DataFrame({"month": [pd.Period("2010-06", "M")], "L_m8": [SESS[2]], "F1": [SESS[20]],
                          "L_m17": [pd.NaT], "pseudo_exit": [pd.NaT]})
    ec = event_contracts(sched, es, zn, SESS[:30], kind="event")
    assert ec.at[0, "es_id"] == 1 and not ec.at[0, "tradable"]


def test_missing_settlement_in_window_marks_data_incomplete(world):
    sched, es = world["sched"], world["es"]
    ec = event_contracts(sched, es, world["zn"], SESS, kind="event")
    r = ec[ec["tradable"] & ec["data_complete"]].iloc[5]
    drop_day = SESS[(SESS > r.anchor) & (SESS < r.exit)][1]
    zn_long = world["zn_long"]
    zn_cut = ContractPanel.from_long(
        zn_long[~((zn_long["date"] == drop_day) & (zn_long["instrument_id"] == r.zn_id))], "ZN")
    ec2 = event_contracts(sched, es, zn_cut, SESS, kind="event").set_index("month")
    assert not ec2.at[r.month, "data_complete"]


def test_duplicate_settlements_conflicting_raise_identical_collapse():
    panel = _two_contract_panel(switch_day=3)
    dup = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    assert ContractPanel.from_long(dup, "ES").settle.shape == ContractPanel.from_long(panel, "ES").settle.shape
    bad = dup.copy()
    bad.loc[bad.index[-1], "settle"] += 1.0
    with pytest.raises(ValueError, match="conflicting"):
        ContractPanel.from_long(bad, "ES")


def test_roll_table_lists_quarterly_es_rolls(world):
    rt = roll_table(world["ref"])
    es_rolls = rt[rt["leg"] == "ES"]
    per_year = es_rolls.groupby(es_rolls["date"].dt.year).size()
    assert (per_year.loc[2011:2014] == 4).all()
