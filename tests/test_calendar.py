"""Session calendar and event schedule: holidays, offsets, windows, samples, no look-ahead.

All tests use the bundled XNYS rules or synthetic settlement dates; no network.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from gqh.calendar import (
    ES_CLOCK_SWITCH,
    ZN_BOND_STRIKE_SWITCH,
    SessionCalendar,
    audit_session_gaps,
    es_settle_clock,
    event_schedule,
    pseudo_offsets,
    qualifying_sessions,
    xnys_early_closes,
    xnys_sessions,
    zn_bond_strike,
)

T = pd.Timestamp

EXPECTED_COLUMNS = [
    "month", "prev_L", "L_m17", "L_m14", "L_m13", "L_m8", "L_m5", "L_m4", "L", "F1",
    "n_sessions_month", "n_since_prev_L", "n_since_prev_L_pseudo", "is_quarter_end", "is_year_end",
    "event_valid", "pseudo_valid", "sample", "es_settle_clock", "zn_bond_strike", "early_close",
]


@pytest.fixture(scope="module")
def sched(xnys_cal: SessionCalendar) -> pd.DataFrame:
    return event_schedule(xnys_cal)


def row(sched: pd.DataFrame, month: str) -> pd.Series:
    hit = sched[sched["month"] == pd.Period(month, freq="M")]
    assert len(hit) == 1, month
    return hit.iloc[0]


# --- XNYS facts ---------------------------------------------------------------

@pytest.mark.parametrize(
    "date",
    [
        "2012-10-29", "2012-10-30",  # Hurricane Sandy
        "2018-12-05",                # G.H.W. Bush national day of mourning
        "2021-04-02", "2024-03-29",  # Good Friday
        "2022-06-20", "2023-06-19", "2024-06-19",  # Juneteenth (observed)
        "2025-01-01",                # New Year
        "2025-01-09",                # Carter national day of mourning
        "2026-05-25",                # Memorial Day
    ],
)
def test_xnys_closures(xnys_2009_2028: pd.DatetimeIndex, date: str) -> None:
    assert T(date) not in xnys_2009_2028


def test_xnys_open_before_juneteenth_rule(xnys_2009_2028: pd.DatetimeIndex) -> None:
    assert T("2021-06-18") in xnys_2009_2028  # Juneteenth not yet an NYSE holiday in 2021


def test_xnys_sessions_bounds_inclusive_and_naive() -> None:
    s = xnys_sessions("2024-03-28", "2024-04-01")
    assert list(s) == [T("2024-03-28"), T("2024-04-01")]
    assert s.tz is None
    # bounds on non-sessions do not raise
    assert list(xnys_sessions("2025-01-01", "2025-01-01")) == []
    assert xnys_sessions("2009-01-01", "2009-01-05")[0] == T("2009-01-02")


def test_xnys_early_closes() -> None:
    ec = xnys_early_closes("2024-01-01", "2024-12-31")
    assert list(ec) == [T("2024-07-03"), T("2024-11-29"), T("2024-12-24")]
    assert set(ec) <= set(xnys_sessions("2024-01-01", "2024-12-31"))


# --- SessionCalendar: L, F1, offsets -------------------------------------------

@pytest.mark.parametrize(
    "year, month, last",
    [
        (2024, 3, "2024-03-28"),   # Good Friday 03-29
        (2026, 5, "2026-05-29"),   # month ends on a Sunday
        (2012, 10, "2012-10-31"),  # Sandy closed 10-29/30, reopened 10-31
        (2018, 11, "2018-11-30"),
        (2024, 12, "2024-12-31"),
        (2021, 3, "2021-03-31"),
    ],
)
def test_month_last(xnys_cal: SessionCalendar, year: int, month: int, last: str) -> None:
    assert xnys_cal.month_last(year, month) == T(last)


@pytest.mark.parametrize(
    "year, month, first",
    [
        (2025, 1, "2025-01-02"),   # New Year
        (2021, 4, "2021-04-01"),   # Good Friday is 04-02
        (2024, 4, "2024-04-01"),
        (2018, 12, "2018-12-03"),
        (2026, 6, "2026-06-01"),
    ],
)
def test_month_first(xnys_cal: SessionCalendar, year: int, month: int, first: str) -> None:
    assert xnys_cal.month_first(year, month) == T(first)


def test_f1_after_holidays(sched: pd.DataFrame) -> None:
    assert row(sched, "2024-12")["F1"] == T("2025-01-02")
    assert row(sched, "2024-03")["F1"] == T("2024-04-01")
    assert row(sched, "2021-03")["F1"] == T("2021-04-01")
    assert row(sched, "2026-05")["L"] == T("2026-05-29")
    assert row(sched, "2026-05")["F1"] == T("2026-06-01")


def test_offsets_skip_closures(xnys_cal: SessionCalendar) -> None:
    assert xnys_cal.offset("2012-10-26", 1) == T("2012-10-31")
    assert xnys_cal.offset("2012-10-31", -1) == T("2012-10-26")
    assert xnys_cal.offset("2018-12-04", 1) == T("2018-12-06")
    assert xnys_cal.offset("2021-04-01", 1) == T("2021-04-05")
    assert xnys_cal.offset("2022-06-17", 1) == T("2022-06-21")
    assert xnys_cal.offset("2025-01-08", 1) == T("2025-01-10")
    assert xnys_cal.offset("2024-06-18", 0) == T("2024-06-18")


def test_offsets_cross_month_boundaries(xnys_cal: SessionCalendar) -> None:
    # 2024-03-28 is L of March; F1 of April is 2024-04-01.
    assert xnys_cal.offset("2024-03-28", 1) == T("2024-04-01")
    assert xnys_cal.offset("2024-04-01", -1) == T("2024-03-28")
    assert xnys_cal.offset("2024-12-31", 1) == T("2025-01-02")
    # Round trips over long spans.
    for d in xnys_cal.sessions[30:-30:97]:
        for k in (-23, -5, 1, 17):
            assert xnys_cal.offset(xnys_cal.offset(d, k), -k) == d
    # Offsets count sessions, not days: October 2024 has 23 sessions.
    assert xnys_cal.offset("2024-10-31", -22) == T("2024-10-01")
    assert xnys_cal.offset("2024-10-31", -23) == T("2024-09-30")


def test_offset_errors(xnys_cal: SessionCalendar) -> None:
    with pytest.raises(ValueError):
        xnys_cal.offset("2024-03-29", 1)  # Good Friday is not a session
    with pytest.raises(ValueError):
        xnys_cal.offset("2026-05-30", 0)  # Saturday
    with pytest.raises(ValueError):
        xnys_cal.offset(xnys_cal.sessions[-1], 1)
    with pytest.raises(ValueError):
        xnys_cal.offset(xnys_cal.sessions[0], -1)
    with pytest.raises(ValueError):
        xnys_cal.month_last(2030, 1)


def test_calendar_normalizes_input() -> None:
    cal = SessionCalendar(["2024-01-03 16:00", "2024-01-02", "2024-01-02", T("2024-01-04")])
    assert list(cal.sessions) == [T("2024-01-02"), T("2024-01-03"), T("2024-01-04")]
    assert len(cal) == 3 and "2024-01-03" in cal
    assert list(cal.months()) == [pd.Period("2024-01", freq="M")]
    with pytest.raises(ValueError):
        SessionCalendar(pd.DatetimeIndex(["2024-01-02"], tz="UTC"))


# --- clocks -------------------------------------------------------------------

def test_clock_regime_switches() -> None:
    assert ES_CLOCK_SWITCH == T("2020-10-26")
    assert es_settle_clock("2020-10-23") == "16:15"
    assert es_settle_clock("2020-10-26") == "16:00"
    assert ZN_BOND_STRIKE_SWITCH == T("2021-01-14")
    assert zn_bond_strike("2021-01-13") == "15:00"
    assert zn_bond_strike("2021-01-14") == "16:00"


def test_clock_columns_by_month(sched: pd.DataFrame) -> None:
    assert row(sched, "2020-09")["es_settle_clock"] == "16:15"
    assert row(sched, "2020-10")["es_settle_clock"] == "16:00"
    assert row(sched, "2020-12")["zn_bond_strike"] == "15:00"
    assert row(sched, "2021-01")["zn_bond_strike"] == "16:00"
    # Oct 2020: entry L-4 is the first 16:00 ES settle; the progress window is all 16:15.
    oct20 = row(sched, "2020-10")
    assert oct20["L_m4"] == ES_CLOCK_SWITCH
    assert es_settle_clock(oct20["L_m5"]) == "16:15"
    regular = sched[[("L" not in ec) for ec in sched["early_close"]]]
    assert (regular["es_settle_clock"] == "16:00").tolist() == (regular["L"] >= ES_CLOCK_SWITCH).tolist()
    assert set(sched.loc[sched.index.difference(regular.index), "es_settle_clock"]) == {"early-close"}


# --- event schedule -------------------------------------------------------------

def test_schedule_columns_and_coverage(sched: pd.DataFrame) -> None:
    assert list(sched.columns) == EXPECTED_COLUMNS
    assert sched["month"].dtype == "period[M]"
    # Calendar covers 2009-12 .. 2028-01, so rows run 2010-01 .. 2027-12.
    assert sched["month"].iloc[0] == pd.Period("2010-01", freq="M")
    assert sched["month"].iloc[-1] == pd.Period("2027-12", freq="M")
    assert len(sched) == 18 * 12
    assert sched["month"].is_monotonic_increasing and sched["month"].is_unique


def test_schedule_definitions_hold_every_month(xnys_cal: SessionCalendar, sched: pd.DataFrame) -> None:
    for r in sched.itertuples(index=False):
        m = r.month
        L = xnys_cal.month_last(m.year, m.month)
        assert r.L == L
        assert r.F1 == xnys_cal.month_first((m + 1).year, (m + 1).month)
        assert r.F1 == xnys_cal.offset(L, 1)
        assert r.prev_L == xnys_cal.month_last((m - 1).year, (m - 1).month)
        for k in (17, 14, 13, 8, 5, 4):
            assert getattr(r, f"L_m{k}") == xnys_cal.offset(L, -k)
        in_month = xnys_cal.sessions[xnys_cal.sessions.to_period("M") == m]
        assert r.n_sessions_month == len(in_month)
        # n = sessions in (prev_L, L-5]
        n = int(((xnys_cal.sessions > r.prev_L) & (xnys_cal.sessions <= r.L_m5)).sum())
        assert r.n_since_prev_L == n == r.n_sessions_month - 5
        assert r.is_quarter_end == (m.month % 3 == 0)
        assert r.is_year_end == (m.month == 12)


def test_n_since_prev_l_examples(sched: pd.DataFrame) -> None:
    # Oct 2012: 23 weekdays - 2 Sandy closures = 21 sessions; n = 16.
    assert row(sched, "2012-10")["n_sessions_month"] == 21
    assert row(sched, "2012-10")["n_since_prev_L"] == 16
    # Mar 2024: 21 weekdays - Good Friday = 20 sessions; n = 15.
    assert row(sched, "2024-03")["n_sessions_month"] == 20
    assert row(sched, "2024-03")["n_since_prev_L"] == 15
    # Dec 2018: 21 weekdays - Bush funeral - Christmas = 19 sessions; n = 14.
    assert row(sched, "2018-12")["n_sessions_month"] == 19
    assert row(sched, "2018-12")["n_since_prev_L"] == 14


def test_event_dates_example(sched: pd.DataFrame) -> None:
    r = row(sched, "2024-03")
    assert r["L"] == T("2024-03-28")
    assert r["L_m4"] == T("2024-03-22")
    assert r["L_m5"] == T("2024-03-21")
    assert r["L_m8"] == T("2024-03-18")
    assert r["L_m13"] == T("2024-03-11")
    assert r["L_m14"] == T("2024-03-08")
    assert r["L_m17"] == T("2024-03-05")
    assert r["prev_L"] == T("2024-02-29")


def test_every_month_valid_on_xnys(sched: pd.DataFrame) -> None:
    assert sched["event_valid"].all()
    assert sched["pseudo_valid"].all()
    assert sched["n_sessions_month"].min() >= 18


def _returns(cal: SessionCalendar, after: pd.Timestamp, through: pd.Timestamp) -> list[pd.Timestamp]:
    """Dates of the close-to-close returns in the window close `after` -> close `through`."""
    i, j = cal.position(after), cal.position(through)
    return list(cal.sessions[i + 1 : j + 1])


def test_windows_never_overlap_2010_2027(xnys_cal: SessionCalendar, sched: pd.DataFrame) -> None:
    used: dict[pd.Timestamp, str] = {}
    for r in sched.itertuples(index=False):
        windows = {
            "pseudo_progress": _returns(xnys_cal, r.L_m17, r.L_m14),
            "pseudo_hold": _returns(xnys_cal, r.L_m13, r.L_m8),
            "event_progress": _returns(xnys_cal, r.L_m8, r.L_m5),
            "event_hold": _returns(xnys_cal, r.L_m4, r.F1),
        }
        assert [len(w) for w in windows.values()] == [3, 5, 3, 5]
        assert windows["event_hold"][-1] == r.F1
        assert windows["pseudo_hold"][-1] == r.L_m8
        for name, dates in windows.items():
            for d in dates:
                assert d not in used, f"{r.month} {name} return {d.date()} already in {used[d]}"
                used[d] = f"{r.month} {name}"
        # The pseudo progress returns start after the previous event's exit (month m's first session).
        assert windows["pseudo_progress"][0] > xnys_cal.month_first(r.month.year, r.month.month)


def test_sample_labels_on_xnys(sched: pd.DataFrame) -> None:
    assert row(sched, "2024-09")["sample"] == "IS"   # F1 = 2024-10-01 = is_end
    assert row(sched, "2024-09")["F1"] == T("2024-10-01")
    assert row(sched, "2024-10")["sample"] == "OOS"  # L-17 = 2024-10-08 >= oos_start
    assert row(sched, "2010-07")["sample"] == "IS"   # prev_L = 2010-06-30 >= is_start
    assert row(sched, "2010-06")["sample"] == "PRE"  # prev_L = 2010-05-28 < is_start
    assert set(sched["sample"]) == {"PRE", "IS", "OOS"}
    assert not (sched["sample"] == "STRADDLE").any()
    labels = sched["sample"].tolist()
    assert labels == sorted(labels, key=["PRE", "IS", "OOS"].index)


def test_straddle_is_flagged(xnys_cal: SessionCalendar) -> None:
    # Move oos_start into the middle of a month: that month's event straddles.
    with pytest.warns(UserWarning, match="2024-10"):
        s = event_schedule(xnys_cal, is_end="2024-10-01", oos_start="2024-10-15")
    assert row(s, "2024-10")["sample"] == "STRADDLE"
    assert (s["sample"] == "STRADDLE").sum() == 1


def test_no_warning_on_frozen_samples(xnys_cal: SessionCalendar) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        event_schedule(xnys_cal)


def test_pseudo_anchor_offset() -> None:
    assert pseudo_offsets() == {"progress_start": 17, "anchor": 14, "entry": 13, "exit": 8}
    assert pseudo_offsets(15) == {"progress_start": 18, "anchor": 15, "entry": 14, "exit": 9}
    with pytest.raises(ValueError):
        pseudo_offsets(13)
    cal = SessionCalendar(xnys_sessions("2015-12-01", "2016-04-30"))
    s = event_schedule(cal, pseudo_anchor_offset=15)
    assert {"L_m18", "L_m15", "L_m14", "L_m9", "L_m8"} <= set(s.columns)
    r = s.iloc[0]
    assert r["L_m18"] == cal.offset(r["L"], -18) and r["L_m9"] == cal.offset(r["L"], -9)


def test_rows_need_neighbour_months() -> None:
    cal = SessionCalendar(xnys_sessions("2024-01-15", "2024-04-02"))
    s = event_schedule(cal)
    # Jan has no previous month and Apr has no next month in the calendar.
    assert [str(p) for p in s["month"]] == ["2024-02", "2024-03"]
    # A month with no sessions removes its neighbours' rows.
    gap = cal.sessions[cal.sessions.to_period("M") != pd.Period("2024-02", freq="M")]
    assert event_schedule(SessionCalendar(gap)).empty


def test_degenerate_month_is_invalid() -> None:
    # Synthetic calendar: month 2 has only 7 sessions, so L-8 falls in month 1.
    jan = pd.bdate_range("2030-01-01", "2030-01-31")
    feb = pd.bdate_range("2030-02-01", "2030-02-28")[:7]
    mar = pd.bdate_range("2030-03-01", "2030-03-29")
    s = event_schedule(SessionCalendar(jan.append(feb).append(mar)))
    r = row(s, "2030-02")
    assert not r["event_valid"] and not r["pseudo_valid"]
    assert r["n_since_prev_L"] == 2


# --- truncation invariance (no look-ahead) ------------------------------------------

def _assert_rows_equal(a: pd.Series, b: pd.Series) -> None:
    pd.testing.assert_series_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_names=False)


def test_truncation_invariance(xnys_cal: SessionCalendar, sched: pd.DataFrame) -> None:
    sessions = xnys_cal.sessions
    rng = np.random.default_rng(20261003)
    picks = sorted(set(rng.choice(len(sched), size=60, replace=False)) | {0, len(sched) - 1})
    for i in picks:
        full = sched.iloc[i]
        # Right truncation: keep sessions through next-month F1 only.
        right = event_schedule(SessionCalendar(sessions[sessions <= full["F1"]]))
        assert right["month"].iloc[-1] == full["month"]
        _assert_rows_equal(right.iloc[-1], full)
        # Both ends: keep only prev_L .. F1.
        both = event_schedule(SessionCalendar(sessions[(sessions >= full["prev_L"]) & (sessions <= full["F1"])]))
        assert len(both) == 1
        _assert_rows_equal(both.iloc[0], full)


def test_truncation_invariance_whole_prefix(xnys_cal: SessionCalendar, sched: pd.DataFrame) -> None:
    # Every row computed on a prefix ending at some F1 matches the full schedule.
    sessions = xnys_cal.sessions
    cut = row(sched, "2019-06")["F1"]
    prefix = event_schedule(SessionCalendar(sessions[sessions <= cut]))
    full = sched[sched["month"] <= pd.Period("2019-06", freq="M")].reset_index(drop=True)
    pd.testing.assert_frame_equal(prefix, full)


# --- qualifying sessions and audit -------------------------------------------------

def test_qualifying_sessions_intersection() -> None:
    xnys = xnys_sessions("2024-03-01", "2024-04-30")
    es = xnys.drop([T("2024-03-14")]).append(pd.DatetimeIndex(["2024-03-29"]))  # ES settles Good Friday
    zn = xnys.drop([T("2024-04-10"), T("2024-04-30")])
    q = qualifying_sessions(es, zn)
    assert T("2024-03-14") not in q   # no ES settle
    assert T("2024-04-10") not in q   # no ZN settle
    assert T("2024-03-29") not in q   # not an XNYS session
    assert T("2024-04-30") not in q
    assert len(q) == len(xnys) - 3
    assert q.is_monotonic_increasing and q.tz is None
    cal = SessionCalendar(q)
    assert cal.month_last(2024, 4) == T("2024-04-29")  # L moves when the last day lacks a settle
    # start/end clip inclusively; unsorted, duplicated, timestamped input is normalized
    q2 = qualifying_sessions(list(reversed(es)) + [T("2024-03-05 15:00")], zn, start="2024-03-05", end="2024-03-08")
    assert list(q2) == list(pd.bdate_range("2024-03-05", "2024-03-08"))


def test_qualifying_sessions_empty() -> None:
    assert len(qualifying_sessions([], [])) == 0
    assert len(qualifying_sessions(["2024-01-02"], ["2024-01-03"])) == 0


def test_audit_session_gaps() -> None:
    xnys = xnys_sessions("2024-03-01", "2024-04-30")
    es = xnys.drop([T("2024-03-14"), T("2024-04-12")]).append(pd.DatetimeIndex(["2024-03-29"]))
    zn = xnys.drop([T("2024-04-10"), T("2024-04-12")])
    audit = audit_session_gaps(es, zn)
    assert list(audit.columns) == ["date", "xnys", "has_es", "has_zn", "issue"]
    got = dict(zip(audit["date"], audit["issue"]))
    assert got == {
        T("2024-03-14"): "missing ES",
        T("2024-03-29"): "settle on non-XNYS day",
        T("2024-04-10"): "missing ZN",
        T("2024-04-12"): "missing ES+ZN",
    }
    r = audit.set_index("date").loc[T("2024-03-29")]
    assert (bool(r["xnys"]), bool(r["has_es"]), bool(r["has_zn"])) == (False, True, False)
    # Clean data -> empty audit; the audit and the qualifying set partition the XNYS days.
    assert audit_session_gaps(xnys, xnys).empty
    q = qualifying_sessions(es, zn)
    flagged_xnys = audit.loc[audit["xnys"], "date"]
    assert set(q) | set(flagged_xnys) == set(xnys) and not (set(q) & set(flagged_xnys))


def test_audit_session_gaps_explicit_range_and_empty() -> None:
    es = pd.DatetimeIndex(["2024-03-04"])
    audit = audit_session_gaps(es, es, start="2024-03-04", end="2024-03-06")
    assert list(audit["date"]) == [T("2024-03-05"), T("2024-03-06")]
    assert (audit["issue"] == "missing ES+ZN").all()
    assert audit_session_gaps([], []).empty


def test_nat_input_is_rejected_on_every_path() -> None:
    # Regression: a NaT inside a DatetimeIndex sorted last, emptied the audit span
    # and turned a real gap into a clean-looking (empty) audit.
    xnys = xnys_sessions("2024-01-01", "2024-06-30")
    es = xnys.drop(T("2024-03-14"))
    assert list(audit_session_gaps(es, xnys)["issue"]) == ["missing ES"]
    es_nat = es.append(pd.DatetimeIndex([pd.NaT]))
    with pytest.raises(ValueError, match="NaT"):
        audit_session_gaps(es_nat, xnys)
    with pytest.raises(ValueError, match="NaT"):
        qualifying_sessions(xnys.append(pd.DatetimeIndex([pd.NaT])), xnys)
    with pytest.raises(ValueError, match="NaT"):
        audit_session_gaps(list(es) + [None], xnys)  # list path agrees with the index path
    with pytest.raises(ValueError, match="NaT"):
        SessionCalendar(pd.DatetimeIndex(["2024-01-02", pd.NaT]))


def test_pseudo_n_counts_sessions_to_the_pseudo_decision(xnys_cal: SessionCalendar, sched: pd.DataFrame) -> None:
    # Regression: only the event n (sessions in (prev_L, L-5]) existed, so a pseudo
    # dose z = D/(0.24 sigma sqrt(n)) at M = L-14 would have used 15 instead of 6.
    from gqh.calendar import n_since_prev_L

    r = row(sched, "2024-03")
    assert r["n_since_prev_L_pseudo"] == 6  # 03-01, 03-04 .. 03-08
    assert r["n_since_prev_L"] == 15
    s = xnys_cal.sessions
    for r in sched.itertuples(index=False):
        n_ps = int(((s > r.prev_L) & (s <= r.L_m14)).sum())
        assert r.n_since_prev_L_pseudo == n_ps == r.n_sessions_month - 14
        assert n_since_prev_L(xnys_cal, r.L_m14) == n_ps
        assert n_since_prev_L(xnys_cal, r.L_m5) == r.n_since_prev_L
    # Section 6.1 freezes the dose at L-12; the helper serves any decision date.
    assert n_since_prev_L(xnys_cal, xnys_cal.offset("2024-03-28", -12)) == 8
    # Day-one decision: n = 1 (prev_L excluded, the decision session included).
    assert n_since_prev_L(xnys_cal, "2024-03-01") == 1
    with pytest.raises(ValueError):
        n_since_prev_L(xnys_cal, "2024-03-29")  # Good Friday: not a session
    s15 = event_schedule(SessionCalendar(xnys_sessions("2015-12-01", "2016-04-30")), pseudo_anchor_offset=15)
    assert (s15["n_since_prev_L_pseudo"] == s15["n_sessions_month"] - 15).all()


# --- early closes -----------------------------------------------------------------

def test_clocks_flag_early_closes() -> None:
    # Regression: es_settle_clock('2019-11-29') returned '16:15' on a 13:00 ET XNYS
    # early close, when no 16:15 ET ES settle and no 15:59 ET bbo-1m minute exist.
    from gqh.calendar import EARLY_CLOSE, executable_fill_minute, is_early_close, zn_settle_clock

    for d in ("2019-11-29", "2018-12-24", "2023-07-03", "2024-11-29"):
        assert is_early_close(d)
        assert es_settle_clock(d) == EARLY_CLOSE
        assert zn_settle_clock(d) == EARLY_CLOSE
        assert zn_bond_strike(d) == EARLY_CLOSE
        assert executable_fill_minute(d) == EARLY_CLOSE
    for d, es in (("2019-11-27", "16:15"), ("2024-11-27", "16:00")):
        assert not is_early_close(d)
        assert es_settle_clock(d) == es
        assert zn_settle_clock(d) == "15:00"
        assert executable_fill_minute(d) == "15:59"


def test_schedule_lists_early_close_dates(sched: pd.DataFrame) -> None:
    from gqh.calendar import EARLY_CLOSE, early_close_hits

    nov19, dec18 = row(sched, "2019-11"), row(sched, "2018-12")
    assert nov19["L"] == T("2019-11-29") and nov19["early_close"] == ("L",)
    assert nov19["es_settle_clock"] == EARLY_CLOSE  # the row-level clock is at L
    assert dec18["L_m4"] == T("2018-12-24") and dec18["early_close"] == ("L_m4",)
    assert row(sched, "2018-11")["early_close"] == ("L_m5",)  # decision on Black Friday
    assert row(sched, "2023-06")["early_close"] == ("F1",)    # exit on July 3
    assert row(sched, "2024-03")["early_close"] == ()
    hits = early_close_hits(sched)
    assert list(hits.columns) == ["month", "column", "date"]
    got = set(zip(hits["month"].astype(str), hits["column"], hits["date"]))
    assert ("2019-11", "L", T("2019-11-29")) in got
    assert ("2018-12", "L_m4", T("2018-12-24")) in got
    assert ("2019-12", "prev_L", T("2019-11-29")) in got
    # Every listed date is an XNYS early close, and every early close on a schedule date is listed.
    ec = set(xnys_early_closes("2009-12-01", "2028-01-31"))
    assert set(hits["date"]) <= ec
    date_cols = [c for c in sched.columns if c == "prev_L" or c.startswith("L") or c == "F1"]
    expect = {(str(r["month"]), c) for _, r in sched.iterrows() for c in date_cols if r[c] in ec}
    assert {(m, c) for m, c, _ in got} == expect
    # IS event-critical hits named by the review: entry or exit on an early close.
    is_rows = sched[sched["sample"] == "IS"]
    entry_exit = {str(r["month"]) for _, r in is_rows.iterrows() if {"L_m4", "F1"} & set(r["early_close"])}
    assert entry_exit == {"2012-12", "2013-12", "2014-12", "2015-12", "2017-06", "2017-11",
                          "2018-12", "2019-12", "2020-12", "2023-06", "2023-11"}


# --- ex-post vs ex-ante decision dates (look-ahead disclosure) ----------------------

def test_decision_shift_flags_only_sandy_on_xnys(xnys_cal: SessionCalendar) -> None:
    # Regression: L-k is counted back from the ex-post L, so the Sandy closures
    # (announced 2012-10-28/29) moved the Oct 2012 decision from the 10-24 a live
    # trader would have used to 10-22. Nothing flagged this.
    from gqh.calendar import decision_shift

    ds = decision_shift(xnys_cal)
    assert len(ds) == 18 * 12
    shifted = ds[ds["event_shift"] | ds["pseudo_shift"]]
    assert [str(m) for m in shifted["month"]] == ["2012-10"]
    r = shifted.iloc[0]
    assert (r["as_of"], r["ex_ante_L_m5"], r["ex_ante_L_m4"], r["ex_ante_L_m8"]) == (
        T("2012-10-22"), T("2012-10-24"), T("2012-10-25"), T("2012-10-19"))
    assert r["ex_ante_n"] == 18
    assert (r["pseudo_as_of"], r["ex_ante_L_m17"], r["ex_ante_L_m14"], r["ex_ante_L_m13"]) == (
        T("2012-10-09"), T("2012-10-08"), T("2012-10-11"), T("2012-10-12"))
    assert bool(r["event_shift"]) and bool(r["pseudo_shift"])
    # Unshifted months reproduce the ex-post schedule exactly.
    sched = event_schedule(xnys_cal)
    ok = ds["month"] != pd.Period("2012-10", freq="M")
    assert (ds.loc[ok, "ex_ante_L_m5"].to_numpy() == sched.loc[ok, "L_m5"].to_numpy()).all()
    assert (ds.loc[ok, "ex_ante_n"].to_numpy() == sched.loc[ok, "n_since_prev_L"].to_numpy()).all()


def test_decision_shift_flags_a_missing_settle_after_the_decision(xnys_cal: SessionCalendar) -> None:
    from gqh.calendar import decision_shift

    s = xnys_cal.sessions
    after = SessionCalendar(s.drop(T("2019-04-26")))   # ZN settle missing 3 sessions after L-5
    r = event_schedule(after).set_index("month").loc[pd.Period("2019-04", freq="M")]
    assert r["L_m5"] == T("2019-04-22")                 # ex-post decision moved one session early
    d = decision_shift(after).set_index("month").loc[pd.Period("2019-04", freq="M")]
    assert d["event_shift"] and d["pseudo_shift"]
    assert d["ex_ante_L_m5"] == T("2019-04-23") and d["ex_ante_n"] == 16
    # A gap BEFORE the decision is known at the decision: no shift.
    before = SessionCalendar(s.drop(T("2019-04-02")))
    d2 = decision_shift(before).set_index("month").loc[pd.Period("2019-04", freq="M")]
    assert not d2["event_shift"] and not d2["pseudo_shift"]


# --- Amendments A1/A2: trading_schedule (ex-ante dates, PX eligibility) ---------

def test_trading_schedule_uses_ex_ante_dates_for_sandy():
    from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions

    cal = SessionCalendar(xnys_sessions("2010-01-01", "2026-12-31"))
    t = trading_schedule(cal).set_index("month")
    oct12 = t.loc[pd.Period("2012-10", "M")]
    assert oct12["L_m8"] == pd.Timestamp("2012-10-19")
    assert oct12["L_m5"] == pd.Timestamp("2012-10-24")
    assert oct12["L_m4"] == pd.Timestamp("2012-10-25")
    assert oct12["n_since_prev_L"] == 18
    assert bool(oct12["ex_post_shift"])
    assert oct12["pseudo_exit"] <= oct12["L_m8"]
    # Sandy is the only shifted month on the XNYS calendar.
    assert int(t["ex_post_shift"].sum()) == 1


def test_trading_schedule_unshifted_rows_match_event_schedule():
    from gqh.calendar import SessionCalendar, event_schedule, trading_schedule, xnys_sessions

    cal = SessionCalendar(xnys_sessions("2010-01-01", "2026-12-31"))
    t, e = trading_schedule(cal), event_schedule(cal)
    keep = ~t["ex_post_shift"]
    for c in ["L_m17", "L_m14", "L_m13", "L_m8", "L_m5", "L_m4", "L", "F1", "n_since_prev_L"]:
        assert (t.loc[keep, c].values == e.loc[keep, c].values).all(), c
    assert (t.loc[keep, "pseudo_exit"].values == e.loc[keep, "L_m8"].values).all()


def test_px_eligible_excludes_early_close_fill_dates():
    from gqh.calendar import SessionCalendar, is_early_close, trading_schedule, xnys_sessions

    cal = SessionCalendar(xnys_sessions("2010-01-01", "2026-12-31"))
    t = trading_schedule(cal)
    bad = t[~t["px_eligible"]]
    assert len(bad) > 0
    for _, r in bad.iterrows():
        assert is_early_close(r["L_m4"]) or is_early_close(r["F1"])
    for _, r in t[t["px_eligible"]].iterrows():
        assert not is_early_close(r["L_m4"]) and not is_early_close(r["F1"])
    is_rows = t[t["sample"] == "IS"]
    assert int((~is_rows["px_eligible"]).sum()) == 11


def test_trading_schedule_missing_settle_on_ex_ante_date_invalidates_event():
    from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions

    sess = xnys_sessions("2019-01-01", "2019-12-31")
    # Drop a settlement AFTER the April decision: ex-post dates move, ex-ante do not.
    dropped = sess.drop(pd.Timestamp("2019-04-26"))
    t = trading_schedule(SessionCalendar(dropped)).set_index("month")
    apr = t.loc[pd.Period("2019-04", "M")]
    assert bool(apr["ex_post_shift"])
    assert apr["L_m5"] == pd.Timestamp("2019-04-23")
