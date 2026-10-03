"""Pilot data audit (Oct 2020 - Jan 2021): data quality only, no strategy returns.

Writes reports/pilot_audit.md with aggregate counts, timing and tick distances.
No raw prices are written (licensed data stays in data/raw/).

Run:  python scripts/pilot_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gqh.calendar import SessionCalendar, audit_session_gaps, trading_schedule, xnys_sessions  # noqa: E402
from gqh.contracts import ContractPanel, event_contracts, reference_returns, roll_table  # noqa: E402
from gqh.panel import SETTLEMENT_PRICE, FLAG_FINAL, load_panels, read_dbn  # noqa: E402

RAW = ROOT / "data" / "raw"
ET = "America/New_York"
START, END = pd.Timestamp("2020-10-01"), pd.Timestamp("2021-01-29")
TICK = {"ES": 0.25, "ZN": 0.015625}


def _hhmm(ts: pd.Series, q: float = 0.5) -> str:
    """Quantile of clock time of day, as HH:MM, with times before 06:00 counted as after midnight."""
    m = ts.dt.hour * 60 + ts.dt.minute
    m = m.where(m >= 360, m + 1440)
    v = int(m.quantile(q)) % 1440
    return f"{v // 60:02d}:{v % 60:02d}"


def front_by_oi(panel: pd.DataFrame) -> pd.Series:
    """Highest-OI outright per date (instrument_id)."""
    p = panel.dropna(subset=["open_interest"])
    return p.loc[p.groupby("date")["open_interest"].idxmax()].set_index("date")["instrument_id"]


def quote_state(bbo: pd.DataFrame, iid: int, when: pd.Timestamp, max_stale_min: float = 5.0) -> tuple[float, float, float]:
    """(mid, spread, minutes stale) of the last bbo-1m record for ``iid`` at or before ``when`` (ET)."""
    q = bbo[bbo["instrument_id"] == iid]
    q = q[(q.index <= when) & (q.index > when - pd.Timedelta(hours=2))]
    if q.empty:
        return np.nan, np.nan, np.nan
    last = q.iloc[-1]
    stale = (when - q.index[-1]).total_seconds() / 60
    if stale > max_stale_min:
        return np.nan, np.nan, stale
    return (last["bid_px_00"] + last["ask_px_00"]) / 2, last["ask_px_00"] - last["bid_px_00"], stale


def main() -> None:
    lines: list[str] = ["# Pilot data audit (2020-10-01 to 2021-01-29)", "",
                        "Data quality only: no strategy returns were computed. Prices appear only as tick distances.", ""]
    panels = load_panels(RAW / "pilot_statistics.dbn.zst", RAW / "pilot_definition.dbn.zst")
    stats = read_dbn(RAW / "pilot_statistics.dbn.zst")
    xnys = xnys_sessions(START, END)

    # 1. Coverage
    gaps = audit_session_gaps(panels["ES"]["date"].unique(), panels["ZN"]["date"].unique(), START, END)
    lines += ["## 1. Session coverage", "",
              f"- XNYS sessions in window: {len(xnys)}",
              f"- Dates with an ES final settlement: {panels['ES']['date'].nunique()}; ZN: {panels['ZN']['date'].nunique()}",
              f"- Gap-audit rows (missing settle on an XNYS session, or settle on a non-XNYS day): {len(gaps)}"]
    if len(gaps):
        lines += [f"  - {r.date.date()}: {r.issue}" for r in gaps.itertuples()]
    lines.append("")

    # 2. Settlement record anatomy
    st = stats[stats["stat_type"] == SETTLEMENT_PRICE].copy()
    st["final"] = (st["stat_flags"].astype(int) & FLAG_FINAL) != 0
    lines += ["## 2. Settlement records", "",
              f"- Settlement records: {len(st)}; with FINAL flag: {int(st['final'].sum())}; "
              f"flag values: {dict(sorted(st['stat_flags'].astype(int).value_counts().items()))}"]
    for root, panel in panels.items():
        fr = front_by_oi(panel)
        fin = panel.set_index(["date", "instrument_id"])
        have = [(d, i) in fin.index for d, i in fr.items()]
        pub = pd.to_datetime(panel["settle_ts_recv"]).dt.tz_convert(ET)
        same_day = (pub.dt.tz_localize(None).dt.normalize() == panel["date"]).mean()
        lines.append(f"- {root}: front contract has a final settle on {sum(have)}/{len(have)} dates; "
                     f"final published median {_hhmm(pub)} ET (latest {_hhmm(pub, 1.0)}); "
                     f"{same_day:.0%} published on the trade date itself (rest after midnight ET)")
    lines.append("")

    # 3. Settlement clock vs quotes (tick distance of settle to the quote mid at candidate minutes)
    bbo = read_dbn(RAW / "pilot_bbo_1m.dbn.zst")
    bbo.index = bbo.index.tz_convert(ET).tz_localize(None)
    on_minute = (bbo.index.second == 0).mean()
    lines += ["## 3. Settlement clock check", "",
              f"- bbo-1m records stamped exactly on a minute boundary: {on_minute:.1%} (ts_recv = interval end)", "",
              "| Root | Period | Candidate mark (ET) | Median |settle - mid| (ticks) | Dates |", "|---|---|---|---|---|"]
    candidates = {"ES": ["15:59", "16:00", "16:14", "16:15"], "ZN": ["14:59", "15:00", "16:00"]}
    switch = pd.Timestamp("2020-10-26")
    for root, panel in panels.items():
        fr = front_by_oi(panel)
        settle = panel.set_index(["date", "instrument_id"])["settle"]
        for period, mask in (("before 2020-10-26", fr.index < switch), ("from 2020-10-26", fr.index >= switch)):
            for hhmm in candidates[root]:
                dist = []
                for d, iid in fr[mask].items():
                    mid, _, _ = quote_state(bbo, iid, d + pd.Timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[3:])))
                    if np.isfinite(mid) and (d, iid) in settle.index:
                        dist.append(abs(settle[(d, iid)] - mid) / TICK[root])
                if dist:
                    lines.append(f"| {root} | {period} | {hhmm} | {np.median(dist):.2f} | {len(dist)} |")
    lines.append("")

    # 4. Executable fill minute: quote freshness and spread at 15:59 ET
    lines += ["## 4. Quotes at the 15:59 ET fill minute (front contract)", "",
              "| Root | Dates with a fresh quote (<= 5 min) | Median staleness (min) | Median spread (ticks) | 95th pct spread (ticks) |",
              "|---|---|---|---|---|"]
    for root, panel in panels.items():
        fr = front_by_oi(panel)
        rows = [quote_state(bbo, iid, d + pd.Timedelta(hours=15, minutes=59)) for d, iid in fr.items()]
        stale = np.array([r[2] for r in rows], dtype=float)
        spr = np.array([r[1] for r in rows], dtype=float) / TICK[root]
        ok = np.isfinite(spr)
        lines.append(f"| {root} | {int(ok.sum())}/{len(rows)} | {np.nanmedian(stale):.1f} | "
                     f"{np.nanmedian(spr):.2f} | {np.nanpercentile(spr, 95):.2f} |")
    lines.append("")

    # 5. Minute volume in the settlement windows (capacity input)
    ohl = read_dbn(RAW / "pilot_ohlcv_1m.dbn.zst")
    ohl.index = ohl.index.tz_convert(ET).tz_localize(None)
    lines += ["## 5. Minute volume in settlement windows (front contract)", "",
              f"- ohlcv-1m bars stamped on a minute boundary: {(ohl.index.second == 0).mean():.1%} (stamp = bar start)", "",
              "| Root | Bar (ET, start) | Median contracts | 10th pct |", "|---|---|---|---|"]
    for root, bars in (("ES", ["15:59"]), ("ZN", ["14:59", "15:59"])):
        fr = front_by_oi(panels[root])
        for hhmm in bars:
            vols = []
            for d, iid in fr.items():
                t = d + pd.Timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[3:]))
                b = ohl[(ohl["instrument_id"] == iid) & (ohl.index == t)]
                vols.append(float(b["volume"].iloc[0]) if len(b) else 0.0)
            lines.append(f"| {root} | {hhmm} | {np.median(vols):,.0f} | {np.percentile(vols, 10):,.0f} |")
    lines.append("")

    # 6. Rolls and event contract selection
    sessions = pd.DatetimeIndex(sorted(set(panels["ES"]["date"]) & set(panels["ZN"]["date"]) & set(xnys)))
    es, zn = ContractPanel.from_long(panels["ES"], "ES"), ContractPanel.from_long(panels["ZN"], "ZN")
    ref = reference_returns(es, zn, sessions)
    rt = roll_table(ref)
    sym = {**es.meta["symbol"].to_dict(), **zn.meta["symbol"].to_dict()}
    lines += ["## 6. Rolls and contract selection", "",
              "Reference-series contract switches (previous-session highest OI):"]
    lines += [f"- {r.date.date()} {r.leg}: {sym[int(r.from_id)]} -> {sym[int(r.to_id)]}" for r in rt.itertuples()]
    lines += ["", "ZN first position days (derived): " + ", ".join(
        f"{zn.meta.at[i, 'symbol']} {zn.meta.at[i, 'first_position_day'].date()}" for i in zn.meta.index)]
    sched = trading_schedule(SessionCalendar(sessions))
    ec = event_contracts(sched, es, zn, sessions, kind="event")
    lines += ["", "| Event month | L-8 | F1 | ES held | ZN held | Tradable | Data complete |", "|---|---|---|---|---|---|---|"]
    for r in ec.itertuples():
        lines.append(f"| {r.month} | {r.anchor.date() if pd.notna(r.anchor) else '-'} | {r.exit.date() if pd.notna(r.exit) else '-'} | "
                     f"{sym.get(int(r.es_id), '-') if pd.notna(r.es_id) else '-'} | {sym.get(int(r.zn_id), '-') if pd.notna(r.zn_id) else '-'} | "
                     f"{r.tradable} | {r.data_complete} |")
    out = ROOT / "reports" / "pilot_audit.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())


if __name__ == "__main__":
    main()
