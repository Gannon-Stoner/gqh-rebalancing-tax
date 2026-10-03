"""Session calendar and the frozen month-end event schedule.

Conventions
-----------
* Every date is a tz-naive, normalized ``pd.Timestamp`` (a CME trade date /
  exchange session date, not an instant). Inputs are normalized on entry.
* A *session* is a CME trade date on which both ES and ZN publish a final
  settlement and XNYS is open (``qualifying_sessions``; HYPOTHESIS.md §2).
* ``L`` is the last session of a calendar month, ``F1`` the first session of
  the next month, and ``L-k`` counts back k sessions from L.
* A *return dated d* is the close-to-close (settle-to-settle) return from the
  session before d to d. A window "close a -> close b" contains the returns
  dated strictly after a through b inclusive.

Event windows (one event per month m)
-------------------------------------
* drift base: close of ``prev_L`` (last session of month m-1)
* progress: close L-8 -> close L-5, i.e. returns L-7, L-6, L-5 (3 returns)
* decision: at the L-5 close; ``n_since_prev_L`` = sessions in (prev_L, L-5]
* entry: L-4 close; holding returns L-3, L-2, L-1, L, F1 (5 returns); exit F1
  (the L-4 return belongs to neither window)

Pseudo-event windows (one per month, anchor M = L-14 by default)
----------------------------------------------------------------
* progress: close L-17 -> close L-14, i.e. returns L-16, L-15, L-14
* entry: L-13 close; holding returns L-12 .. L-8 (5 returns); exit L-8
* valid only if L-17 is in month m, so the pseudo returns start after the
  previous event's exit at month m's first session, and end where this
  month's event progress window begins.

Caveats (see AMENDMENTS.md)
---------------------------
* Dates are ex-post: L-k is counted back from the realised L, so a closure or
  missing settle after a decision date moves the decision (``decision_shift``).
* XNYS early closes have no regular ES/ZN settle clock and no 15:59 ET fill
  minute; the clock helpers return ``EARLY_CLOSE`` and the schedule's
  ``early_close`` column lists the affected date columns.

Nothing here touches the network; XNYS sessions come from the
``exchange_calendars`` rule set bundled with the package.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Any, Iterable

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from gqh.config import frozen_config

ES_CLOCK_SWITCH = pd.Timestamp("2020-10-26")
"""First trade date with the ES settlement at 16:00 ET (16:15 ET before)."""

ZN_BOND_STRIKE_SWITCH = pd.Timestamp("2021-01-14")
"""First date of the 16:00 ET bond-index month-end strike (15:00 ET before); diagnostic only."""

_XNYS_PAD = pd.Timedelta(days=14)


def _ts(value: Any) -> pd.Timestamp:
    """Tz-naive normalized timestamp; rejects tz-aware input."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        raise ValueError(f"expected a tz-naive date, got {value!r}")
    return ts.normalize()


def _dates(values: Iterable[Any]) -> pd.DatetimeIndex:
    """Sorted, unique, tz-naive, normalized DatetimeIndex.

    Raises ValueError on tz-aware input and on any missing date (NaT/None), on
    both input paths: a NaT would sort last, empty the span used by the audit
    and the session filter, and make a real gap look clean.
    """
    if isinstance(values, pd.DatetimeIndex):
        if values.tz is not None:
            raise ValueError("expected tz-naive dates")
        idx = values
    else:
        values = list(values)
        if any(pd.isna(v) for v in values):
            raise ValueError("dates contain NaT/None")
        idx = pd.DatetimeIndex([_ts(v) for v in values])
    if idx.hasnans:
        raise ValueError(f"dates contain {int(idx.isna().sum())} NaT value(s)")
    return pd.DatetimeIndex(idx.normalize().unique().sort_values(), freq=None)


@lru_cache(maxsize=32)
def _xnys(start: pd.Timestamp, end: pd.Timestamp) -> xcals.ExchangeCalendar:
    # exchange_calendars raises for dates outside the calendar's bounds, so the
    # calendar is built with explicit, padded bounds.
    return xcals.get_calendar("XNYS", start=start - _XNYS_PAD, end=end + _XNYS_PAD)


def xnys_sessions(start: Any, end: Any) -> pd.DatetimeIndex:
    """XNYS session dates in [start, end] (inclusive), tz-naive."""
    s, e = _ts(start), _ts(end)
    if e < s:
        return pd.DatetimeIndex([], name="session")
    sessions = _xnys(s, e).sessions
    out = sessions[(sessions >= s) & (sessions <= e)]
    return pd.DatetimeIndex(out, name="session", freq=None)


def xnys_early_closes(start: Any, end: Any) -> pd.DatetimeIndex:
    """XNYS early-close session dates in [start, end] (inclusive), tz-naive."""
    s, e = _ts(start), _ts(end)
    if e < s:
        return pd.DatetimeIndex([], name="early_close")
    closes = pd.DatetimeIndex(_xnys(s, e).early_closes).normalize()
    out = closes[(closes >= s) & (closes <= e)]
    return pd.DatetimeIndex(out, name="early_close", freq=None)


def _bounds(dates: pd.DatetimeIndex, start: Any, end: Any) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """[start, end] defaulting to the span of ``dates``; None if nothing to cover."""
    if len(dates) == 0 and (start is None or end is None):
        return None
    s = _ts(start) if start is not None else dates[0]
    e = _ts(end) if end is not None else dates[-1]
    return (s, e) if s <= e else None


def qualifying_sessions(
    es_settle_dates: Iterable[Any],
    zn_settle_dates: Iterable[Any],
    start: Any = None,
    end: Any = None,
) -> pd.DatetimeIndex:
    """Frozen session rule: ES final-settle dates ∩ ZN final-settle dates ∩ XNYS sessions.

    ``start``/``end`` (inclusive) default to the span of the ES∩ZN dates.
    """
    both = _dates(es_settle_dates).intersection(_dates(zn_settle_dates)).sort_values()
    span = _bounds(both, start, end)
    if span is None:
        return pd.DatetimeIndex([], name="session")
    s, e = span
    out = both[(both >= s) & (both <= e)].intersection(xnys_sessions(s, e)).sort_values()
    return pd.DatetimeIndex(out, name="session", freq=None)


def audit_session_gaps(
    es_settle_dates: Iterable[Any],
    zn_settle_dates: Iterable[Any],
    start: Any = None,
    end: Any = None,
) -> pd.DataFrame:
    """Dates where the three session sources disagree (for the data audit).

    One row per date in [start, end] that is an XNYS session missing an ES or ZN
    settlement, or that carries an ES or ZN settlement but is not an XNYS
    session. ``start``/``end`` default to the span of all settlement dates.

    Columns: ``date``, ``xnys`` (bool), ``has_es`` (bool), ``has_zn`` (bool),
    ``issue`` ("missing ES", "missing ZN", "missing ES+ZN" on XNYS sessions;
    "settle on non-XNYS day" otherwise).
    """
    es, zn = _dates(es_settle_dates), _dates(zn_settle_dates)
    columns = ["date", "xnys", "has_es", "has_zn", "issue"]
    span = _bounds(es.union(zn), start, end)
    if span is None:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in zip(columns, ["datetime64[ns]", bool, bool, bool, object])})
    s, e = span
    xnys = xnys_sessions(s, e)
    universe = xnys.union(es).union(zn)
    universe = universe[(universe >= s) & (universe <= e)]
    df = pd.DataFrame(
        {
            "date": universe,
            "xnys": universe.isin(xnys),
            "has_es": universe.isin(es),
            "has_zn": universe.isin(zn),
        }
    )
    df = df[~(df["xnys"] & df["has_es"] & df["has_zn"])].reset_index(drop=True)
    missing = np.select(
        [~df["has_es"] & ~df["has_zn"], ~df["has_es"], ~df["has_zn"]],
        ["missing ES+ZN", "missing ES", "missing ZN"],
        default="",
    )
    df["issue"] = np.where(df["xnys"], missing, "settle on non-XNYS day")
    return df[columns]


class SessionCalendar:
    """An ordered set of session dates with session-count arithmetic.

    ``sessions`` is normalized to a sorted, unique, tz-naive DatetimeIndex.
    Offsets count sessions, never calendar days.
    """

    def __init__(self, sessions: Iterable[Any]):
        self.sessions: pd.DatetimeIndex = pd.DatetimeIndex(_dates(sessions), name="session", freq=None)
        self._months = self.sessions.to_period("M")

    def __len__(self) -> int:
        return len(self.sessions)

    def __contains__(self, date: Any) -> bool:
        return _ts(date) in self.sessions

    def position(self, date: Any) -> int:
        """Integer position of a session; ValueError if ``date`` is not a session."""
        d = _ts(date)
        i = int(self.sessions.searchsorted(d))
        if i >= len(self.sessions) or self.sessions[i] != d:
            raise ValueError(f"{d.date()} is not a session")
        return i

    def offset(self, date: Any, k: int) -> pd.Timestamp:
        """The session k sessions after ``date`` (k < 0: before).

        Raises ValueError if ``date`` is not a session or the result falls
        outside the calendar.
        """
        j = self.position(date) + int(k)
        if not 0 <= j < len(self.sessions):
            raise ValueError(f"offset {k} from {_ts(date).date()} is outside the calendar")
        return self.sessions[j]

    def _month_sessions(self, year: int, month: int) -> pd.DatetimeIndex:
        out = self.sessions[self._months == pd.Period(year=year, month=month, freq="M")]
        if len(out) == 0:
            raise ValueError(f"no sessions in {year:04d}-{month:02d}")
        return out

    def month_last(self, year: int, month: int) -> pd.Timestamp:
        """L: the last session of the calendar month (ValueError if it has none)."""
        return self._month_sessions(year, month)[-1]

    def month_first(self, year: int, month: int) -> pd.Timestamp:
        """The first session of the calendar month (ValueError if it has none)."""
        return self._month_sessions(year, month)[0]

    def months(self) -> pd.PeriodIndex:
        """Calendar months (Period 'M') that contain at least one session, ascending."""
        return pd.PeriodIndex(self._months.unique(), freq="M", name="month")


def n_since_prev_L(cal: SessionCalendar, decision_date: Any) -> int:
    """The n of z = D/(0.24 sigma sqrt(n)) for a decision at ``decision_date``.

    n = number of sessions in (prev_L, decision_date], where prev_L is the last
    session of the month before the decision's month: the event decision L-5
    gives n_sessions_month - 5, the pseudo decision L-14 gives n_sessions_month
    - 14, and the section 6.1 dose frozen at L-12 gives n_sessions_month - 12.
    ValueError if ``decision_date`` is not a session.
    """
    d = _ts(decision_date)
    first = cal.month_first(d.year, d.month)
    return cal.position(d) - cal.position(first) + 1


EARLY_CLOSE = "early-close"
"""Clock sentinel for XNYS early-close sessions (13:00 ET close).

CME equity and rates futures also close early on these days, so none of the
regular ET clocks (ES 16:15/16:00 settle, ZN 15:00 settle, the PX 15:59 bbo-1m
minute) exists. The frozen protocol does not say which mark to use instead; a
caller that receives this value must handle the date explicitly (see
AMENDMENTS.md) rather than read a stale or missing quote.
"""


@lru_cache(maxsize=None)
def _early_closes_in_year(year: int) -> frozenset:
    return frozenset(xnys_early_closes(f"{year:04d}-01-01", f"{year:04d}-12-31"))


def is_early_close(date: Any) -> bool:
    """True if ``date`` is an XNYS early-close session (bundled exchange_calendars rules)."""
    d = _ts(date)
    return d in _early_closes_in_year(d.year)


def es_settle_clock(date: Any) -> str:
    """ES daily settlement clock (ET) on ``date``.

    '16:15' before 2020-10-26, '16:00' from then on, and ``EARLY_CLOSE`` on an
    XNYS early-close session (no regular-clock settle exists that day).
    """
    d = _ts(date)
    if is_early_close(d):
        return EARLY_CLOSE
    return "16:15" if d < ES_CLOCK_SWITCH else "16:00"


def zn_settle_clock(date: Any) -> str:
    """ZN daily settlement clock (ET) on ``date``: '15:00', or ``EARLY_CLOSE``."""
    return EARLY_CLOSE if is_early_close(date) else "15:00"


def executable_fill_minute(date: Any) -> str:
    """PX fill minute (ET, bbo-1m bar label) on ``date``: '15:59', or ``EARLY_CLOSE``."""
    return EARLY_CLOSE if is_early_close(date) else "15:59"


def zn_bond_strike(date: Any) -> str:
    """Bond-index month-end strike (ET) on ``date``: '15:00' before 2021-01-14, else '16:00'.

    ``EARLY_CLOSE`` on an XNYS early-close session. Diagnostic only (HYPOTHESIS.md
    §6.2); the ZN settlement itself stays at 15:00 ET.
    """
    d = _ts(date)
    if is_early_close(d):
        return EARLY_CLOSE
    return "15:00" if d < ZN_BOND_STRIKE_SWITCH else "16:00"


EVENT_OFFSETS = (8, 5, 4)
"""Event offsets from L: progress start L-8, decision L-5, entry L-4."""


def pseudo_offsets(pseudo_anchor_offset: int = 14) -> dict[str, int]:
    """Offsets from L of the pseudo-event dates for anchor M = L - a.

    progress_start = M-3, anchor = M, entry = M+1, exit = M+6. With the frozen
    a = 14 these are L-17, L-14, L-13 and L-8. ``a`` must be >= 14 so the pseudo
    exit is at or before L-8, where the event progress window starts.
    """
    a = int(pseudo_anchor_offset)
    if a < 14:
        raise ValueError("pseudo_anchor_offset must be >= 14 (pseudo exit at or before L-8)")
    return {"progress_start": a + 3, "anchor": a, "entry": a - 1, "exit": a - 6}


def early_close_hits(sched: pd.DataFrame) -> pd.DataFrame:
    """Long table of schedule dates on XNYS early closes: ``month``, ``column``, ``date``.

    One row per (month, date column) listed in ``sched['early_close']``, in
    schedule order, so PX and the section 6.2 clock diagnostic can handle or
    exclude those marks explicitly.
    """
    recs = [
        {"month": r["month"], "column": c, "date": r[c]}
        for _, r in sched.iterrows()
        for c in r["early_close"]
    ]
    out = pd.DataFrame(recs, columns=["month", "column", "date"])
    out["date"] = pd.to_datetime(out["date"])
    return out


def event_schedule(
    cal: SessionCalendar,
    *,
    pseudo_anchor_offset: int = 14,
    is_start: Any = None,
    is_end: Any = None,
    oos_start: Any = None,
) -> pd.DataFrame:
    """One row per calendar month m with event and pseudo-event dates.

    A row exists for month m only if months m-1 and m+1 both have sessions in
    ``cal`` (so ``prev_L`` and ``F1`` exist). Every value in a row depends only
    on sessions from ``prev_L`` through ``F1``, so truncating the calendar right
    after F1 leaves the row unchanged (no dependence on sessions after F1).

    This is NOT "no look-ahead" at the decision: following the frozen rule
    "L-k counts back over sessions", L-17 .. L-4 and both n columns are counted
    back from the ex-post L, so a session missing after a decision date (an
    unscheduled closure such as Sandy, Oct 2012, or a missing settle) changes
    which day was the decision day. :func:`decision_shift` flags those months.

    Columns (dates are Timestamps, NaT if the offset falls before the calendar):

    * ``month`` (Period 'M'), ``prev_L`` (L of month m-1)
    * ``L_m17``, ``L_m14``, ``L_m13``: pseudo progress start, anchor, entry
      (named for the default pseudo_anchor_offset=14; another anchor a names
      them ``L_m{a+3}``, ``L_m{a}``, ``L_m{a-1}`` and adds the exit ``L_m{a-6}``)
    * ``L_m8``: event progress start and default pseudo exit; ``L_m5``: decision;
      ``L_m4``: entry; ``L``; ``F1``: first session of month m+1, the exit
    * ``n_sessions_month``: sessions in month m
    * ``n_since_prev_L``: EVENT-ONLY n of z = D/(0.24 sigma sqrt(n)), the sessions
      in (prev_L, L-5]; equals n_sessions_month - 5. Never use it for pseudo-events.
    * ``n_since_prev_L_pseudo``: the pseudo-event n, sessions in (prev_L, L-a] for
      anchor M = L-a (a = 14 by default); equals n_sessions_month - a. For any
      other decision date (e.g. the section 6.1 dose at L-12) use
      :func:`n_since_prev_L`.
    * ``is_quarter_end``, ``is_year_end``
    * ``event_valid``: all event dates exist and L-8 > prev_L
    * ``pseudo_valid``: all pseudo dates exist and the pseudo progress start is
      on or after month m's first session (no overlap with the previous event's
      holding window, which ends there)
    * ``sample``: 'PRE' if prev_L < is_start; 'IS' if F1 <= is_end; 'OOS' if
      L-17 (pseudo progress start) >= oos_start; else 'STRADDLE' (also warned)
    * ``es_settle_clock``, ``zn_bond_strike``: clocks evaluated at L ONLY (the
      row's other marks can sit in a different regime, e.g. 2020-10 has L at
      16:00 but prev_L .. L-5 at 16:15); use :func:`es_settle_clock` per date.
      ``EARLY_CLOSE`` when L is an XNYS early close.
    * ``early_close``: tuple of this row's date-column names (prev_L .. F1) that
      fall on XNYS early-close sessions, where no regular settle clock or 15:59
      ET fill minute exists; () if none. :func:`early_close_hits` lists them.

    ``is_start``/``is_end``/``oos_start`` default to config/frozen.yaml.
    """
    po = pseudo_offsets(pseudo_anchor_offset)
    pseudo_cols = {key: f"L_m{k}" for key, k in po.items()}
    offset_cols = sorted({*po.values(), *EVENT_OFFSETS}, reverse=True)

    if is_start is None or is_end is None or oos_start is None:
        cfg = frozen_config()
        is_start = cfg.is_start if is_start is None else is_start
        is_end = cfg.is_end if is_end is None else is_end
        oos_start = cfg.oos_start if oos_start is None else oos_start
    is_start, is_end, oos_start = _ts(is_start), _ts(is_end), _ts(oos_start)

    date_cols = ["prev_L", *[f"L_m{k}" for k in offset_cols], "L", "F1"]
    sessions = cal.sessions
    months = cal.months()
    present = set(months)
    rows = []
    for m in months:
        if (m - 1) not in present or (m + 1) not in present:
            continue
        first = cal.month_first(m.year, m.month)
        last = cal.month_last(m.year, m.month)
        i_first, i_last = cal.position(first), cal.position(last)
        i_prev = i_first - 1  # month m-1 is non-empty, so this is its last session
        row: dict[str, Any] = {"month": m, "prev_L": sessions[i_prev]}
        for k in offset_cols:
            j = i_last - k
            row[f"L_m{k}"] = sessions[j] if j >= 0 else pd.NaT
        row["L"] = last
        row["F1"] = sessions[i_last + 1]  # month m+1 is non-empty
        row["n_sessions_month"] = i_last - i_first + 1
        row["n_since_prev_L"] = (i_last - 5) - i_prev
        row["n_since_prev_L_pseudo"] = (i_last - po["anchor"]) - i_prev

        event_dates = [row["prev_L"], row["L_m8"], row["L_m5"], row["L_m4"], row["L"], row["F1"]]
        row["event_valid"] = bool(all(pd.notna(d) for d in event_dates) and row["L_m8"] > row["prev_L"])
        pseudo_dates = [row[c] for c in pseudo_cols.values()]
        row["pseudo_valid"] = bool(
            all(pd.notna(d) for d in pseudo_dates) and row[pseudo_cols["progress_start"]] >= first
        )

        p_start = row[pseudo_cols["progress_start"]]
        if row["prev_L"] < is_start:
            row["sample"] = "PRE"
        elif row["F1"] <= is_end:
            row["sample"] = "IS"
        elif pd.notna(p_start) and p_start >= oos_start:
            row["sample"] = "OOS"
        else:
            row["sample"] = "STRADDLE"
        row["is_quarter_end"] = m.month in (3, 6, 9, 12)
        row["is_year_end"] = m.month == 12
        row["es_settle_clock"] = es_settle_clock(last)
        row["zn_bond_strike"] = zn_bond_strike(last)
        row["early_close"] = tuple(c for c in date_cols if pd.notna(row[c]) and is_early_close(row[c]))
        rows.append(row)

    columns = [
        "month",
        *date_cols,
        "n_sessions_month",
        "n_since_prev_L",
        "n_since_prev_L_pseudo",
        "is_quarter_end",
        "is_year_end",
        "event_valid",
        "pseudo_valid",
        "sample",
        "es_settle_clock",
        "zn_bond_strike",
        "early_close",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df["month"] = pd.PeriodIndex(df["month"], freq="M") if len(df) else pd.Series(dtype="period[M]")
    for c in date_cols:
        df[c] = pd.to_datetime(df[c])
    for c in ["n_sessions_month", "n_since_prev_L", "n_since_prev_L_pseudo"]:
        df[c] = df[c].astype("int64")
    for c in ["is_quarter_end", "is_year_end", "event_valid", "pseudo_valid"]:
        df[c] = df[c].astype(bool)

    straddle = df.loc[df["sample"] == "STRADDLE", "month"]
    if len(straddle):
        warnings.warn(
            f"event months straddle the IS/OOS boundary: {[str(p) for p in straddle]}",
            stacklevel=2,
        )
    return df


XNYS_UNSCHEDULED_CLOSURES: dict[pd.Timestamp, pd.Timestamp] = {
    pd.Timestamp("2012-10-29"): pd.Timestamp("2012-10-28"),  # Hurricane Sandy, announced Sun 10-28
    pd.Timestamp("2012-10-30"): pd.Timestamp("2012-10-29"),  # Hurricane Sandy, extended on 10-29
    pd.Timestamp("2018-12-05"): pd.Timestamp("2018-12-01"),  # G.H.W. Bush day of mourning
    pd.Timestamp("2025-01-09"): pd.Timestamp("2024-12-31"),  # Carter day of mourning (public by then)
}
"""Ad hoc XNYS closures since 2010 -> the date they became public.

``exchange_calendars`` lists these as ordinary holidays, i.e. as if they had
always been scheduled. A decision taken at the close of date t knew of closure c
iff the announcement date is <= t. Only Sandy was announced after a decision
date it moves; the Bush and Carter dates only need to precede the first
affected decision (Dec 2018 / Jan 2025 rows), which they do.
"""


def _offsets_from_L(sess: pd.DatetimeIndex, month: pd.Period, offsets: Iterable[int]) -> dict[int, pd.Timestamp]:
    """L-k for each k, with L the last session of ``month`` in ``sess`` (NaT before the start)."""
    i_last = int(np.flatnonzero(sess.to_period("M") == month)[-1])
    return {k: (sess[i_last - k] if i_last - k >= 0 else pd.NaT) for k in offsets}


def decision_shift(
    cal: SessionCalendar,
    *,
    pseudo_anchor_offset: int = 14,
    closures: dict[pd.Timestamp, pd.Timestamp] | None = None,
    **schedule_kwargs: Any,
) -> pd.DataFrame:
    """Ex-ante check of the schedule's decision dates (look-ahead disclosure).

    ``event_schedule`` counts L-k back from the ex-post L, so a session that is
    missing AFTER a decision date (an unscheduled closure, or a missing ES/ZN
    settle in the data) moves which day was the decision day. This recomputes
    the dates on the calendar a live trader knew at the close of the ex-post
    decision date ``as_of``: ``cal`` sessions through ``as_of``, then XNYS
    sessions (bundled rules) plus every closure in ``closures`` (default
    ``XNYS_UNSCHEDULED_CLOSURES``) not yet announced at ``as_of``, assuming every
    later settle arrives.

    One row per schedule month. Event part (as of the ex-post L-5): ``as_of``,
    ``ex_ante_L_m8``, ``ex_ante_L_m5``, ``ex_ante_L_m4``, ``ex_ante_n`` (sessions
    in (prev_L, ex-ante L-5]) and ``event_shift`` (any of the three dates
    differs). Pseudo part (as of the ex-post anchor L-a): ``pseudo_as_of``,
    ``ex_ante_L_m{a+3}``, ``ex_ante_L_m{a}``, ``ex_ante_L_m{a-1}``,
    ``ex_ante_pseudo_exit`` (L-(a-6)) and ``pseudo_shift``. Rows whose as-of
    date is NaT carry NaT and False. The frozen (ex-post) schedule is left
    unchanged; flagged months are disclosed in AMENDMENTS.md.
    """
    closures = XNYS_UNSCHEDULED_CLOSURES if closures is None else closures
    po = pseudo_offsets(pseudo_anchor_offset)
    sched = event_schedule(cal, pseudo_anchor_offset=pseudo_anchor_offset, **schedule_kwargs)
    ps_keys = {"progress_start": po["progress_start"], "anchor": po["anchor"], "entry": po["entry"]}
    ps_cols = [f"ex_ante_L_m{k}" for k in ps_keys.values()]
    columns = ["month", "as_of", "ex_ante_L_m8", "ex_ante_L_m5", "ex_ante_L_m4", "ex_ante_n",
               "event_shift", "pseudo_as_of", *ps_cols, "ex_ante_pseudo_exit", "pseudo_shift"]
    if sched.empty:
        return pd.DataFrame(columns=columns)

    sessions = cal.sessions
    horizon = sched["F1"].max()
    xnys = xnys_sessions(sessions[0], horizon)
    closed = pd.DatetimeIndex(sorted(closures))

    def known(as_of: pd.Timestamp, month: pd.Period) -> pd.DatetimeIndex:
        """Sessions through month end as a trader saw them at the close of ``as_of``."""
        end = month.end_time.normalize()
        later = xnys[(xnys > as_of) & (xnys <= end)]
        unknown = pd.DatetimeIndex([c for c in closed if as_of < c <= end and closures[c] > as_of])
        return sessions[sessions <= as_of].union(later).union(unknown)

    rows = []
    for r in sched.itertuples(index=False):
        out: dict[str, Any] = {"month": r.month, "as_of": r.L_m5}
        if pd.notna(r.L_m5):
            k_ev = known(r.L_m5, r.month)
            ev = _offsets_from_L(k_ev, r.month, (8, 5, 4))
            out.update({f"ex_ante_L_m{k}": d for k, d in ev.items()})
            out["ex_ante_n"] = int(((k_ev > r.prev_L) & (k_ev <= ev[5])).sum())
            out["event_shift"] = any(ev[k] != getattr(r, f"L_m{k}") for k in (8, 5, 4))
        else:
            out.update({"ex_ante_L_m8": pd.NaT, "ex_ante_L_m5": pd.NaT, "ex_ante_L_m4": pd.NaT,
                        "ex_ante_n": -1, "event_shift": False})
        p_as_of = getattr(r, f"L_m{po['anchor']}")
        out["pseudo_as_of"] = p_as_of
        if pd.notna(p_as_of):
            ps = _offsets_from_L(known(p_as_of, r.month), r.month, [*ps_keys.values(), po["exit"]])
            out.update({f"ex_ante_L_m{k}": ps[k] for k in ps_keys.values()})
            out["ex_ante_pseudo_exit"] = ps[po["exit"]]
            out["pseudo_shift"] = any(ps[k] != getattr(r, f"L_m{k}") for k in [*ps_keys.values(), po["exit"]])
        else:
            out.update({c: pd.NaT for c in ps_cols})
            out.update({"ex_ante_pseudo_exit": pd.NaT, "pseudo_shift": False})
        rows.append(out)
    df = pd.DataFrame(rows, columns=columns)
    df["month"] = pd.PeriodIndex(df["month"], freq="M")
    for c in ["as_of", "ex_ante_L_m8", "ex_ante_L_m5", "ex_ante_L_m4", "pseudo_as_of", *ps_cols,
              "ex_ante_pseudo_exit"]:
        df[c] = pd.to_datetime(df[c])
    df["ex_ante_n"] = df["ex_ante_n"].astype("int64")
    for c in ["event_shift", "pseudo_shift"]:
        df[c] = df[c].astype(bool)
    return df


def trading_schedule(
    cal: SessionCalendar,
    *,
    closures: dict[pd.Timestamp, pd.Timestamp] | None = None,
    **schedule_kwargs: Any,
) -> pd.DataFrame:
    """The schedule the strategy trades on: ``event_schedule`` with ex-ante dates.

    Amendment A1 (bug fix): the decision, entry and progress dates are the ones a
    live trader could know at the close of the decision date (``decision_shift``),
    not the ex-post L-k counts. Only rows that ``decision_shift`` flags change.

    Changes vs ``event_schedule``:

    * ``L_m8``, ``L_m5``, ``L_m4`` and ``n_since_prev_L`` are ex-ante; ``L_m17``,
      ``L_m14``, ``L_m13`` and ``n_since_prev_L_pseudo`` are ex-ante for the pseudo
      decision.
    * ``pseudo_exit`` is new: the ex-ante pseudo exit (equal to ``L_m8`` unless a
      shift separates them). It is always <= the event progress start.
    * ``ex_post_shift``: True if any date moved.
    * ``event_valid`` / ``pseudo_valid`` additionally require every ex-ante date
      to be a session in ``cal`` (a missing settle on it invalidates the event).
    * ``px_eligible`` (amendment A2): False when the PX fill dates (entry ``L_m4``
      or exit ``F1``) are XNYS early closes, where no 15:59 ET fill minute exists.
      PX drops those events; PG is also reported on the PX-eligible subset.

    Pseudo-event signals (sigma_hat, drift) are computed through the pseudo
    decision date ``L_m14`` only (amendment A5).
    """
    sched = event_schedule(cal, **schedule_kwargs).copy()
    shift = decision_shift(cal, closures=closures, **schedule_kwargs)
    sessions = cal.sessions

    sched["pseudo_exit"] = sched["L_m8"]
    sched["ex_post_shift"] = False
    for i, s in shift.iterrows():
        if s["event_shift"]:
            for k in (8, 5, 4):
                sched.at[i, f"L_m{k}"] = s[f"ex_ante_L_m{k}"]
            sched.at[i, "n_since_prev_L"] = int(s["ex_ante_n"])
            sched.at[i, "ex_post_shift"] = True
        if s["pseudo_shift"]:
            for k in (17, 14, 13):
                sched.at[i, f"L_m{k}"] = s[f"ex_ante_L_m{k}"]
            sched.at[i, "pseudo_exit"] = s["ex_ante_pseudo_exit"]
            prev_L = sched.at[i, "prev_L"]
            anchor = s["ex_ante_L_m14"]
            sched.at[i, "n_since_prev_L_pseudo"] = int(((sessions > prev_L) & (sessions <= anchor)).sum())
            sched.at[i, "ex_post_shift"] = True

    def all_sessions(row: pd.Series, cols: list[str]) -> bool:
        return all(pd.notna(row[c]) and row[c] in cal for c in cols)

    ev_cols = ["prev_L", "L_m8", "L_m5", "L_m4", "L", "F1"]
    ps_cols = ["L_m17", "L_m14", "L_m13", "pseudo_exit"]
    sched["event_valid"] = [
        bool(v and all_sessions(r, ev_cols) and r["L_m8"] > r["prev_L"]) for v, (_, r) in zip(sched["event_valid"], sched.iterrows())
    ]
    sched["pseudo_valid"] = [
        bool(v and all_sessions(r, ps_cols) and r["pseudo_exit"] <= r["L_m8"])
        for v, (_, r) in zip(sched["pseudo_valid"], sched.iterrows())
    ]
    sched["px_eligible"] = [
        bool(pd.notna(r["L_m4"]) and pd.notna(r["F1"]) and not is_early_close(r["L_m4"]) and not is_early_close(r["F1"]))
        for _, r in sched.iterrows()
    ]
    sched["early_close"] = [
        tuple(c for c in ["prev_L", "L_m17", "L_m14", "L_m13", "L_m8", "L_m5", "L_m4", "L", "F1"]
              if pd.notna(r[c]) and is_early_close(r[c]))
        for _, r in sched.iterrows()
    ]
    for c in ["L_m17", "L_m14", "L_m13", "L_m8", "L_m5", "L_m4", "pseudo_exit"]:
        sched[c] = pd.to_datetime(sched[c])
    for c in ["n_since_prev_L", "n_since_prev_L_pseudo"]:
        sched[c] = sched[c].astype("int64")
    return sched
