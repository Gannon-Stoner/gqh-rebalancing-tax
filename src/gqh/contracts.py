"""Contract selection and within-contract returns (HYPOTHESIS.md section 2).

Input format
------------
A *long settlement panel* per root, one row per (trade date, outright contract),
with columns ``date, instrument_id, symbol, expiration, settle, open_interest``
and optionally ``first_position_day``. ``date`` is the CME trade date of the
final settlement; ``open_interest`` is the open interest for that trade date
(published the next morning, so it is known before the next session's close).
Spreads and options must already be filtered out. Rows are keyed on
``instrument_id``; ``symbol`` is informational only (one-digit years repeat).

Rules implemented
-----------------
* Event contracts (frozen.yaml ``contracts``):

  - ES: the highest open-interest outright at the event anchor L-8. Ties go
    to the nearer expiration. Pseudo-events (anchor L-17, amendment A6) take the
    highest-OI outright among those expiring after the pseudo exit, because at
    L-17 of a quarterly month the expiring front still holds the most OI.
  - ZN: the nearest outright whose first position day is after the exit (F1;
    for pseudo-events the pseudo exit).
  - One contract per leg per event: no mid-event roll, no cross-contract price
    ratio. A contract that expires (ES) or reaches first position day (ZN) on
    or before the exit is not tradable for the event.

* Reference daily returns (for drift D and sigma_hat): the return on session t
  is ``log(S_c,t / S_c,t-1)`` for the contract c with the highest open interest
  on session t-1, among contracts still tradable on t (ES: expiration >= t;
  ZN: first position day > t). The choice uses only information known before t,
  and both prices come from the same contract, so roll gaps never enter.

ZN first position day = the second business day before the first business day
of the delivery month (the expiration month); XNYS sessions stand in for
business days. It is derived from ``expiration`` when the panel lacks it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from gqh.calendar import xnys_sessions

PANEL_COLUMNS = ("date", "instrument_id", "symbol", "expiration", "settle", "open_interest")
ROOTS = ("ES", "ZN")


def zn_first_position_day(expiration: Any, days: pd.DatetimeIndex) -> pd.Timestamp:
    """Second business day before the first business day of the delivery month."""
    exp = pd.Timestamp(expiration).normalize()
    in_month = days[(days.year == exp.year) & (days.month == exp.month)]
    if len(in_month) == 0:
        raise ValueError(f"business days do not cover {exp:%Y-%m}")
    pos = days.get_loc(in_month[0]) - 2
    if pos < 0:
        raise ValueError(f"business days start too late for the {exp:%Y-%m} first position day")
    return days[pos]


def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in PANEL_COLUMNS if c not in panel.columns]
    if missing:
        raise ValueError(f"settlement panel lacks columns {missing}")
    df = panel.copy()
    for c in ("date", "expiration"):
        df[c] = pd.to_datetime(df[c]).dt.normalize()
        if getattr(df[c].dt, "tz", None) is not None:
            raise ValueError(f"{c} must be tz-naive")
    if df["settle"].isna().any() or (df["settle"] <= 0).any():
        raise ValueError("settlements must be positive and non-missing")
    dup = df.duplicated(["date", "instrument_id"], keep=False)
    if dup.any():
        clash = df[dup].groupby(["date", "instrument_id"])["settle"].nunique()
        if (clash > 1).any():
            raise ValueError(f"conflicting settlements for {clash[clash > 1].index[:3].tolist()}")
        df = df.drop_duplicates(["date", "instrument_id"])
    return df.sort_values(["date", "expiration"], ignore_index=True)


@dataclass(frozen=True)
class ContractPanel:
    """Wide views of one root's settlement panel.

    ``settle`` and ``oi`` are date x instrument_id frames whose columns are
    ordered by expiration (so a first-max ``argmax`` breaks ties toward the
    nearer contract). ``meta`` is indexed by instrument_id with ``symbol``,
    ``expiration`` and ``first_position_day`` (NaT for ES).
    """

    root: str
    settle: pd.DataFrame
    oi: pd.DataFrame
    meta: pd.DataFrame

    @classmethod
    def from_long(cls, panel: pd.DataFrame, root: str, days: pd.DatetimeIndex | None = None) -> "ContractPanel":
        root = root.upper()
        if root not in ROOTS:
            raise ValueError(f"root must be one of {ROOTS}")
        df = _normalize_panel(panel)
        meta = (df.groupby("instrument_id")
                  .agg(symbol=("symbol", "first"), expiration=("expiration", "first"))
                  .sort_values("expiration"))
        if root == "ZN":
            if "first_position_day" in df.columns and df["first_position_day"].notna().all():
                fpd = df.groupby("instrument_id")["first_position_day"].first()
                meta["first_position_day"] = pd.to_datetime(fpd.reindex(meta.index)).dt.normalize()
            else:
                if days is None:
                    days = xnys_sessions(meta["expiration"].min() - pd.Timedelta(days=60),
                                         meta["expiration"].max() + pd.Timedelta(days=10))
                meta["first_position_day"] = [zn_first_position_day(e, days) for e in meta["expiration"]]
        else:
            meta["first_position_day"] = pd.NaT
        meta["first_position_day"] = pd.to_datetime(meta["first_position_day"])
        order = list(meta.index)
        settle = df.pivot(index="date", columns="instrument_id", values="settle").reindex(columns=order)
        weight = "selection_weight" if "selection_weight" in df.columns else "open_interest"   # A14
        oi = df.pivot(index="date", columns="instrument_id", values=weight).reindex(columns=order)
        return cls(root=root, settle=settle, oi=oi, meta=meta)

    # -- point lookups -----------------------------------------------------
    def price(self, iid: int, date: Any) -> float:
        """Settlement of ``iid`` on ``date`` (NaN if absent)."""
        d = pd.Timestamp(date)
        if d not in self.settle.index or iid not in self.settle.columns:
            return np.nan
        return float(self.settle.at[d, iid])

    def log_return(self, iid: int, start: Any, end: Any) -> float:
        """Within-contract log return from the ``start`` settle to the ``end`` settle."""
        return float(np.log(self.price(iid, end) / self.price(iid, start)))

    def has_settles(self, iid: int, dates: pd.DatetimeIndex) -> bool:
        """True if ``iid`` has a settlement on every date in ``dates``."""
        if iid not in self.settle.columns:
            return False
        s = self.settle[iid].reindex(dates)
        return bool(s.notna().all())

    # -- selection ---------------------------------------------------------
    def tradable_through(self, iid: int, date: Any) -> bool:
        """ES: expiration after ``date``; ZN: first position day after ``date``."""
        row = self.meta.loc[iid]
        d = pd.Timestamp(date)
        return bool(row["first_position_day"] > d) if self.root == "ZN" else bool(row["expiration"] > d)

    def max_oi(self, date: Any, *, tradable_on: Any | None = None,
               expires_after: Any | None = None) -> int | None:
        """Highest-OI contract on ``date`` (ties: nearer expiration).

        ``tradable_on``: also require the contract to still trade on that date
        (ES: expiration >= it; ZN: first position day > it).
        ``expires_after``: also require expiration strictly after that date.
        """
        d = pd.Timestamp(date)
        if d not in self.oi.index:
            return None
        row = self.oi.loc[d]
        ok = row.notna() & self.settle.loc[d].notna()
        if tradable_on is not None:
            t = pd.Timestamp(tradable_on)
            if self.root == "ZN":
                ok &= (self.meta["first_position_day"] > t).reindex(row.index).to_numpy()
            else:
                ok &= (self.meta["expiration"] >= t).reindex(row.index).to_numpy()
        if expires_after is not None:
            ok &= (self.meta["expiration"] > pd.Timestamp(expires_after)).reindex(row.index).to_numpy()
        cand = row[ok]
        if cand.empty:
            return None
        return int(cand.index[int(np.argmax(cand.to_numpy()))])

    def nearest_fpd_after(self, listed_on: Any, after: Any) -> int | None:
        """Nearest-expiration ZN contract listed on ``listed_on`` whose first position day is after ``after``."""
        d, a = pd.Timestamp(listed_on), pd.Timestamp(after)
        if d not in self.settle.index:
            return None
        listed = self.settle.loc[d].notna()
        ok = listed & (self.meta["first_position_day"] > a).reindex(listed.index).to_numpy()
        cand = self.meta.loc[ok[ok].index]
        return None if cand.empty else int(cand["expiration"].idxmin())


def reference_returns(es: ContractPanel, zn: ContractPanel, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Daily within-contract log returns on ``sessions`` (first session: NaN).

    Columns ``r_es, r_zn`` (log returns) and ``es_id, zn_id`` (the contract used
    for each return). A return is NaN when the chosen contract lacks a settle
    on either session or when no contract qualifies.
    """
    sessions = pd.DatetimeIndex(sessions)
    out = {"r_es": [np.nan], "r_zn": [np.nan], "es_id": [pd.NA], "zn_id": [pd.NA]}
    for prev, t in zip(sessions[:-1], sessions[1:]):
        for leg, panel in (("es", es), ("zn", zn)):
            iid = panel.max_oi(prev, tradable_on=t)
            r = panel.log_return(iid, prev, t) if iid is not None else np.nan
            out[f"r_{leg}"].append(r)
            out[f"{leg}_id"].append(pd.NA if iid is None else iid)
    df = pd.DataFrame(out, index=sessions.rename("date"))
    for c in ("es_id", "zn_id"):
        df[c] = df[c].astype("Int64")
    return df


def roll_table(ref: pd.DataFrame) -> pd.DataFrame:
    """Sessions where the reference contract changes, per leg (for the data audit)."""
    rows = []
    for leg in ("es", "zn"):
        ids = ref[f"{leg}_id"]
        changed = ids.ne(ids.shift()) & ids.shift().notna() & ids.notna()
        for d in ids.index[changed.fillna(False).to_numpy()]:
            rows.append({"date": d, "leg": leg.upper(), "from_id": ids.shift().at[d], "to_id": ids.at[d]})
    return pd.DataFrame(rows, columns=["date", "leg", "from_id", "to_id"])


def event_contracts(sched: pd.DataFrame, es: ContractPanel, zn: ContractPanel,
                    sessions: pd.DatetimeIndex, *, kind: str = "event") -> pd.DataFrame:
    """Contracts held for each schedule row.

    ``kind='event'``: anchor L-8, exit F1. ``kind='pseudo'``: anchor L-17,
    exit ``pseudo_exit``. Columns: ``month, anchor, exit, es_id, zn_id,
    es_expiration, zn_first_position_day, tradable`` (ex-ante: ES expires and
    ZN reaches first position day strictly after the exit), ``data_complete``
    (both contracts settle on every session from anchor through exit).
    """
    if kind not in ("event", "pseudo"):
        raise ValueError("kind must be 'event' or 'pseudo'")
    a_col, x_col = ("L_m8", "F1") if kind == "event" else ("L_m17", "pseudo_exit")
    sessions = pd.DatetimeIndex(sessions)
    rows = []
    for r in sched.itertuples(index=False):
        anchor, exit_ = getattr(r, a_col), getattr(r, x_col)
        out: dict[str, Any] = {"month": r.month, "anchor": anchor, "exit": exit_,
                               "es_id": pd.NA, "zn_id": pd.NA, "es_expiration": pd.NaT,
                               "zn_first_position_day": pd.NaT, "tradable": False, "data_complete": False}
        if pd.notna(anchor) and pd.notna(exit_):
            # Events: the frozen rule, verbatim (an expiring pick makes the row
            # untradable). Pseudo-events (amendment A6): the highest-OI contract
            # among those expiring after the pseudo exit, so quarterly months are
            # not lost to the mid-month ES expiry.
            es_id = es.max_oi(anchor) if kind == "event" else es.max_oi(anchor, expires_after=exit_)
            zn_id = zn.nearest_fpd_after(anchor, exit_)
            out.update(es_id=es_id if es_id is not None else pd.NA,
                       zn_id=zn_id if zn_id is not None else pd.NA)
            if es_id is not None and zn_id is not None:
                out["es_expiration"] = es.meta.at[es_id, "expiration"]
                out["zn_first_position_day"] = zn.meta.at[zn_id, "first_position_day"]
                out["tradable"] = es.tradable_through(es_id, exit_) and zn.tradable_through(zn_id, exit_)
                window = sessions[(sessions >= anchor) & (sessions <= exit_)]
                out["data_complete"] = es.has_settles(es_id, window) and zn.has_settles(zn_id, window)
        rows.append(out)
    df = pd.DataFrame(rows)
    for c in ("es_id", "zn_id"):
        df[c] = df[c].astype("Int64")
    for c in ("anchor", "exit", "es_expiration", "zn_first_position_day"):
        df[c] = pd.to_datetime(df[c])
    return df
