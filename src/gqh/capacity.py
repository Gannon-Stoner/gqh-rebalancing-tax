"""Capacity from execution-window volume (HYPOTHESIS.md §1 kill test, §8; frozen.yaml ``capacity``).

For every traded event and both fill days (entry, exit), each leg's contracts are
compared with that leg's volume in the execution window:

* ``settle`` windows (settlement rows): ZN the 14:59 ET minute (14:59-15:00); ES the
  15:59 minute from 2020-10-26 and the 16:14 minute before (the settlement VWAP
  windows end inside these one-minute bars).
* ``px`` window (PX row): the 15:59 ET minute for both legs.

The largest NAV at participation p is NAV_ref · min over legs and days of
p·V / n (NAV scales contracts linearly). The binding leg is the one attaining
that minimum. The kill test asks whether the binding leg can fill one contract at
1% of window volume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gqh.calendar import ES_CLOCK_SWITCH
from gqh.config import FrozenConfig, frozen_config

PARTICIPATION = (0.01, 0.05, 0.10)


def window_bars(leg: str, day: pd.Timestamp, mode: str) -> list[pd.Timestamp]:
    """Start times (ET) of the one-minute bars that make up a leg's execution window on ``day``."""
    day = pd.Timestamp(day).normalize()
    if mode == "px":
        return [day + pd.Timedelta(hours=15, minutes=59)]
    if mode != "settle":
        raise ValueError("mode must be 'settle' or 'px'")
    if leg == "ZN":
        return [day + pd.Timedelta(hours=14, minutes=59)]
    return [day + (pd.Timedelta(hours=16, minutes=14) if day < ES_CLOCK_SWITCH else pd.Timedelta(hours=15, minutes=59))]


def window_volume(volume: dict[int, pd.Series], iid: int, leg: str, day: pd.Timestamp, mode: str) -> float:
    """Contracts traded by ``iid`` in the window (a missing bar means no trades)."""
    v = volume.get(int(iid))
    if v is None:
        return 0.0
    return float(sum(v.get(t, 0.0) for t in window_bars(leg, day, mode)))


def capacity_table(ledger: pd.DataFrame, signals: pd.DataFrame, volume: dict[int, pd.Series], *, mode: str,
                   participation: tuple[float, ...] = PARTICIPATION, cfg: FrozenConfig | None = None) -> pd.DataFrame:
    """One row per traded event: window volumes, binding leg, max NAV per participation, 1-lot test at 1%."""
    cfg = cfg or frozen_config()
    sig = signals.set_index("month")          # align by month, never by position
    rows = []
    for _, t in ledger.iterrows():
        if not t["traded"]:
            continue
        r = sig.loc[t["month"]]
        ratios, vols = {}, {}
        for leg, iid, n in (("ES", r["es_id"], t["n_es"]), ("ZN", r["zn_id"], t["n_zn"])):
            v = min(window_volume(volume, iid, leg, d, mode) for d in (t["entry"], t["exit"]))
            vols[leg] = v
            ratios[leg] = v / n
        bind = min(ratios, key=ratios.get)
        row = {"month": t["month"], "n_es": t["n_es"], "n_zn": t["n_zn"], "vol_es": vols["ES"], "vol_zn": vols["ZN"],
               "binding_leg": bind, "lot_at_1pct": bool(0.01 * vols[bind] >= 1.0)}
        for p in participation:
            row[f"max_nav_{int(round(p * 100))}pct"] = cfg.reference_nav * p * ratios[bind]
        rows.append(row)
    return pd.DataFrame(rows)


def capacity_summary(table: pd.DataFrame, participation: tuple[float, ...] = PARTICIPATION) -> dict:
    """Median and 10th-percentile max NAV per participation rate, binding-leg shares and the 1-lot test."""
    if table.empty:
        return {"events": 0}
    share = table["binding_leg"].value_counts(normalize=True)
    out = {"events": int(len(table)), "binding_leg_share": share.to_dict(),
           "binding_share_ES": float(share.get("ES", 0.0)), "binding_share_ZN": float(share.get("ZN", 0.0)),
           "lot_at_1pct_share": float(table["lot_at_1pct"].mean()),
           "median_window_volume": {"ES": float(table["vol_es"].median()), "ZN": float(table["vol_zn"].median())}}
    for p in participation:
        col = f"max_nav_{int(round(p * 100))}pct"
        out[col] = {"median": float(table[col].median()), "p10": float(table[col].quantile(0.10))}
    return out
