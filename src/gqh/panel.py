"""Settlement panels from Databento GLBX.MDP3 ``statistics`` + ``definition`` records.

Vendor conventions (Databento GLBX.MDP3 docs, checked 2026-10-03):

* CME publishes several records per (instrument, trading date, statistic): the
  first ones are preliminary, the last is final. ``stat_flags`` on settlement
  prices: bit 1 = final (vs preliminary), bit 2 = actual (vs theoretical),
  bit 4 = settled at the trading tick, bit 8 = intraday settlement published
  before the official end-of-day calculation.
* ``ts_ref`` is the trading session date (date precision, stored as midnight
  UTC). It must not be localized: its UTC calendar date *is* the trade date.
* ``update_action`` 1 = NEW, 2 = DELETE (removes the statistic for that key).

Rules (HYPOTHESIS.md section 2, frozen.yaml ``data.settlement``):

* Settlement = the last NEW ``SETTLEMENT_PRICE`` record per (instrument_id,
  trade date) whose flags include FINAL and exclude INTRADAY, ordered by
  ``ts_recv`` then ``sequence``. A DELETE removes every earlier record of its
  key. No final record means no settlement for that date (never a preliminary).
  A final price of 0.0 (CME's placeholder for newly listed deferred contracts
  that have not traded) is treated as no settlement.
* Open interest and cleared volume = the last NEW record per (instrument_id,
  trade date), DELETE-aware; the value is the ``quantity`` field.
* Outrights only: definition records with ``instrument_class == 'F'`` for the
  root's ``asset``; the last definition per instrument wins.
* Out-of-sample dates (>= frozen ``oos_start``) are dropped unless the
  ``freeze-final`` git tag exists.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from gqh.config import frozen_config, repo_root

SETTLEMENT_PRICE, CLEARED_VOLUME, OPEN_INTEREST = 3, 6, 9
NEW, DELETE = 1, 2
FLAG_FINAL, FLAG_ACTUAL, FLAG_TRADING_TICK, FLAG_INTRADAY = 1, 2, 4, 8


def _trade_date(ts_ref: pd.Series) -> pd.Series:
    """Trade date from ``ts_ref`` without localizing (UTC calendar date)."""
    s = pd.to_datetime(ts_ref)
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return s.dt.normalize()


def _ordered(stats: pd.DataFrame) -> pd.DataFrame:
    """Records with ``ts_recv`` as a column, in publication order."""
    df = stats.reset_index()
    if "ts_recv" not in df.columns:
        raise ValueError("statistics frame needs ts_recv (index or column)")
    df["date"] = _trade_date(df["ts_ref"])
    sort_cols = ["ts_recv", "sequence"] if "sequence" in df.columns else ["ts_recv"]
    return df.sort_values(sort_cols, kind="mergesort", ignore_index=True)


def _apply_deletes(df: pd.DataFrame) -> pd.DataFrame:
    """Drop DELETE records and every record of the same key published at or before them."""
    key = ["instrument_id", "stat_type", "date"]
    dels = df[df["update_action"] == DELETE]
    if dels.empty:
        return df[df["update_action"] == NEW]
    last_del = dels.groupby(key)["ts_recv"].max().rename("last_delete").reset_index()
    out = df.merge(last_del, on=key, how="left")
    keep = (out["update_action"] == NEW) & (out["last_delete"].isna() | (out["ts_recv"] > out["last_delete"]))
    return out.loc[keep].drop(columns="last_delete")


def final_settlements(stats: pd.DataFrame) -> pd.DataFrame:
    """Columns ``instrument_id, date, settle, settle_ts_recv, stat_flags``: one row per key."""
    df = _apply_deletes(_ordered(stats))
    df = df[(df["stat_type"] == SETTLEMENT_PRICE)
            & (df["stat_flags"].astype(int) & FLAG_FINAL != 0)
            & (df["stat_flags"].astype(int) & FLAG_INTRADAY == 0)
            & df["price"].notna() & (df["price"] > 0)]  # newly listed deferreds carry 0.0 placeholders
    last = df.groupby(["instrument_id", "date"], sort=False).tail(1)
    return (last.rename(columns={"price": "settle", "ts_recv": "settle_ts_recv"})
                [["instrument_id", "date", "settle", "settle_ts_recv", "stat_flags"]]
                .sort_values(["date", "instrument_id"], ignore_index=True))


def daily_quantity(stats: pd.DataFrame, stat_type: int, name: str) -> pd.DataFrame:
    """Columns ``instrument_id, date, <name>`` from the last NEW record per key."""
    df = _apply_deletes(_ordered(stats))
    df = df[df["stat_type"] == stat_type]
    last = df.groupby(["instrument_id", "date"], sort=False).tail(1)
    return last.rename(columns={"quantity": name})[["instrument_id", "date", name]].reset_index(drop=True)


def outright_definitions(defs: pd.DataFrame, root: str) -> pd.DataFrame:
    """Last definition per outright of ``root``: ``instrument_id, symbol, expiration, tick, unit_qty``.

    ``expiration`` is the calendar date in America/New_York.
    """
    df = defs.reset_index()
    order = ["ts_recv"] if "ts_recv" in df.columns else []
    if order:
        df = df.sort_values(order, kind="mergesort")
    df = df[(df["asset"] == root.upper()) & (df["instrument_class"] == "F")]
    last = df.groupby("instrument_id", sort=False).tail(1).copy()
    if "raw_symbol" in last.columns:  # to_df also adds a mapped 'symbol'; keep the exchange symbol
        last = last.drop(columns=[c for c in ("symbol",) if c in last.columns])
    exp = pd.to_datetime(last["expiration"])
    if getattr(exp.dt, "tz", None) is None:
        exp = exp.dt.tz_localize("UTC")
    last["expiration"] = exp.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    return (last.rename(columns={"raw_symbol": "symbol", "min_price_increment": "tick",
                                 "unit_of_measure_qty": "unit_qty"})
                [["instrument_id", "symbol", "expiration", "tick", "unit_qty"]]
                .sort_values("expiration", ignore_index=True))


def oos_unlocked(root: Path | None = None) -> bool:
    """True if the frozen ``oos_unlock_tag`` exists in the repository."""
    tag = frozen_config().oos_unlock_tag
    try:
        out = subprocess.run(["git", "tag", "-l", tag], cwd=root or repo_root(),
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return tag in out.split()


def build_settlement_panel(stats: pd.DataFrame, defs: pd.DataFrame, root: str, *,
                           allow_oos: bool | None = None) -> pd.DataFrame:
    """Long panel for ``gqh.contracts``: one row per (trade date, outright) with a final settle.

    Columns ``date, instrument_id, symbol, expiration, settle, open_interest,
    cleared_volume, settle_ts_recv, tick, unit_qty``. ``open_interest`` and
    ``cleared_volume`` are NaN where CME published none for that date.
    ``allow_oos=None`` follows the git tag; ``True`` requires the tag.
    """
    unlocked = oos_unlocked()
    if allow_oos and not unlocked:
        raise PermissionError("out-of-sample data requested before the freeze-final tag exists")
    allow = unlocked if allow_oos is None else bool(allow_oos)
    outr = outright_definitions(defs, root)
    settles = final_settlements(stats).merge(outr, on="instrument_id", how="inner")
    oi = daily_quantity(stats, OPEN_INTEREST, "open_interest")
    vol = daily_quantity(stats, CLEARED_VOLUME, "cleared_volume")
    panel = (settles.merge(oi, on=["instrument_id", "date"], how="left")
                    .merge(vol, on=["instrument_id", "date"], how="left"))
    if not allow:
        panel = panel[panel["date"] < frozen_config().oos_start]
    cols = ["date", "instrument_id", "symbol", "expiration", "settle", "open_interest",
            "cleared_volume", "settle_ts_recv", "tick", "unit_qty"]
    return panel[cols].sort_values(["date", "expiration"], ignore_index=True)


def read_dbn(paths: str | Path | Iterable[str | Path]) -> pd.DataFrame:
    """Concatenate DBN files into one DataFrame (``databento.DBNStore.to_df``)."""
    import databento as db

    paths = [paths] if isinstance(paths, (str, Path)) else list(paths)
    return pd.concat([db.DBNStore.from_file(str(p)).to_df() for p in paths])


def load_panels(stats_paths: Any, defs_paths: Any, *, allow_oos: bool | None = None) -> dict[str, pd.DataFrame]:
    """ES and ZN settlement panels from DBN files."""
    stats, defs = read_dbn(stats_paths), read_dbn(defs_paths)
    return {root: build_settlement_panel(stats, defs, root, allow_oos=allow_oos) for root in ("ES", "ZN")}
