"""Out-of-sample data coverage check (2024-10-02 to 2026-10-02): data quality only, no returns.

Run once after the OOS files land (after ``freeze-final``) and before the single OOS
evaluation, as ``scripts/is_coverage.py`` was run before the in-sample one (A17).
Writes reports/oos_coverage.md: aggregate counts only; prices appear only as spreads
in ticks. Sessions, schedule and contracts are built exactly as
``gqh.pipeline.prepare`` builds them for ``--sample ALL``, then cut to the OOS rows.

Run:  python scripts/oos_coverage.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import is_coverage as cov  # noqa: E402  (puts src/ and data/ on the path)
from gqh.calendar import (SessionCalendar, audit_session_gaps, decision_shift,  # noqa: E402
                          is_early_close, qualifying_sessions, trading_schedule, xnys_sessions)
from gqh.config import frozen_config  # noqa: E402
from gqh.contracts import ContractPanel, event_contracts, reference_returns, roll_table  # noqa: E402
from gqh.data import _dbn, bar_volume, build_derived, load_derived  # noqa: E402
from gqh.panel import oos_unlocked, outright_definitions  # noqa: E402
from gqh.quotes import QuoteBook  # noqa: E402

RAW, DERIVED = cov.RAW, cov.DERIVED
OOS_FIRST, OOS_LAST = pd.Timestamp("2024-10-02"), pd.Timestamp("2026-10-02")
DATE_COLS = {"L_m17": "pseudo progress start", "L_m14": "pseudo decision", "L_m13": "pseudo entry",
             "pseudo_exit": "pseudo exit", "L_m8": "event progress start", "L_m5": "decision",
             "L_m4": "entry", "L": "L", "F1": "exit (F1)"}


def _oos_jobs() -> list[dict]:
    return [j for j in json.loads((ROOT / "data" / "batch_jobs.json").read_text())["jobs"]
            if j["parent_request"].startswith("oos_")]


def purchase_section() -> list[str]:
    man = json.loads((ROOT / "data" / "manifest.json").read_text())["pulls"]
    jobs = _oos_jobs()
    batch_start = {j["parent_request"]: pd.Timestamp(j["start"]) for j in jobs}
    expected = []
    for n in ("oos_definition", "oos_statistics", "oos_ohlcv_1m", "oos_bbo_1m"):
        for stem, start, _ in cov.download.chunks(n):   # streamed pieces, except those a batch job replaced
            if n in batch_start and pd.Timestamp(start) >= batch_start[n]:
                continue
            expected.append(stem)
    streamed = {e["request"]: e for e in man if e["request"] in expected}
    ids = {j["job_id"] for j in jobs}
    batch = [e for e in man if e.get("job_id") in ids]
    files = [*streamed.values(), *batch]
    ok = sum(cov.download._sha256(ROOT / e["file"]) == e["sha256"] for e in files if (ROOT / e["file"]).is_file())
    cost = sum(e["quoted_cost_usd"] for e in streamed.values()) + sum(j["quoted_cost_usd"] for j in jobs)
    return ["## 0. Purchase", "",
            f"- Streamed files expected {len(expected)}, in manifest {len(streamed)}; missing: "
            f"{sorted(set(expected) - set(streamed)) or 'none'}",
            f"- Batch jobs {len(jobs)} ({', '.join(j['job_id'] + ' ' + j['parent_request'] for j in jobs) or 'none'}); "
            f"batch files in manifest {len(batch)}",
            f"- SHA-256 matches on disk: {ok} of {len(files)}; quoted cost ${cost:.2f}; "
            f"{sum(e['bytes'] for e in files) / 1e6:.0f} MB compressed", ""]


def settlement_section(panels: dict[str, pd.DataFrame]) -> list[str]:
    xnys = xnys_sessions(OOS_FIRST, OOS_LAST)
    es_d, zn_d = panels["ES"]["date"].unique(), panels["ZN"]["date"].unique()
    gaps = audit_session_gaps(es_d, zn_d, OOS_FIRST, OOS_LAST)
    out = ["## 1. Settlement coverage", "",
           f"- XNYS sessions {len(xnys)}; with an ES final settle {len(set(es_d) & set(xnys))}; "
           f"with a ZN final settle {len(set(zn_d) & set(xnys))}",
           f"- Gap-audit rows: {len(gaps)}"]
    out += [f"  - {r.date.date()}: {r.issue}" for r in gaps.itertuples()]
    for root, p in panels.items():
        q = p[(p["date"] >= OOS_FIRST) & (p["date"] <= OOS_LAST)]
        out.append(f"- {root}: OOS panel rows {len(q)}; without a FINAL-flag record (last record used, A14) "
                   f"{int((~q['final_flag'].astype(bool)).sum())}; ranked by traded volume for want of open "
                   f"interest (A14) {int((q['selection_source'] != 'open_interest').sum())}")
    out += [f"- Last settlement date in the panels: ES {panels['ES']['date'].max().date()}, "
            f"ZN {panels['ZN']['date'].max().date()} (2026-10-01 is the Sep-2026 exit)", ""]
    return out


def schedule_section(es, zn, qual, sched, degraded) -> tuple[list[str], pd.DataFrame, pd.DataFrame]:
    oos = sched[sched["sample"] == "OOS"]
    shift = decision_shift(SessionCalendar(qual))
    flagged = shift[(shift["event_shift"] | shift["pseudo_shift"]) & shift["month"].isin(list(oos["month"]))]
    out = ["## 2. Calendar, decision dates and events", "",
           f"- Qualifying sessions in the OOS window: {int(((qual >= OOS_FIRST) & (qual <= OOS_LAST)).sum())}",
           f"- Schedule rows by sample after the IS end: "
           f"{sched.loc[sched['F1'] > OOS_FIRST, 'sample'].value_counts().to_dict()}; OOS months "
           f"{oos['month'].min()} to {oos['month'].max()}",
           f"- OOS months whose ex-ante dates differ from ex-post (A1): {len(flagged)}"]
    for r in flagged.itertuples():
        out.append(f"  - {r.month}: event shift {r.event_shift}, pseudo shift {r.pseudo_shift}")
    frames = {}
    for kind, valid_col in (("event", "event_valid"), ("pseudo", "pseudo_valid")):
        ec = event_contracts(sched, es, zn, qual, kind=kind)
        df = pd.concat([sched[["sample", valid_col, "px_eligible", "L_m4"]].reset_index(drop=True), ec], axis=1)
        df = df[df["sample"] == "OOS"].reset_index(drop=True)
        df["usable"] = df[valid_col] & df["tradable"] & df["data_complete"]
        frames[kind] = df
        out.append(f"- {kind}s in OOS: {len(df)}; usable (valid, tradable, data complete): {int(df['usable'].sum())}"
                   + (f"; usable and PX-eligible: {int((df['usable'] & df['px_eligible']).sum())}" if kind == "event" else ""))
        out += [f"  - {r.month}: {cov._why(r, es, zn, qual, valid_col)}" for r in df[~df["usable"]].itertuples()]
    out.append("- Databento-degraded days that are OOS sessions, and the schedule dates they carry:")
    for d in degraded:
        if d < OOS_FIRST or d > OOS_LAST or d not in set(qual):
            continue
        roles = [f"{r.month} {name}" for r in oos.itertuples() for c, name in DATE_COLS.items()
                 if c in oos.columns and getattr(r, c) == d]
        out.append(f"  - {d.date()} ({d.day_name()[:3]}){', early close' if is_early_close(d) else ''}: "
                   f"{'; '.join(roles) or 'no schedule date'}")
    for kind, df in frames.items():
        hits = [f"{r.month} ({', '.join(d.date().isoformat() for d in degraded if r.anchor <= d <= r.exit)})"
                for r in df[df["usable"]].itertuples() if any(r.anchor <= d <= r.exit for d in degraded)]
        out.append(f"- Usable OOS {kind}s whose window (anchor..exit) touches a Databento-degraded day: {len(hits)}"
                   + (f": {hits}" if hits else ""))
    out.append("")
    return out, frames["event"], frames["pseudo"]


def reference_section(ref: pd.DataFrame) -> list[str]:
    r = ref[(ref.index >= OOS_FIRST) & (ref.index <= OOS_LAST)]
    rt = roll_table(ref)
    rt = rt[(rt["date"] >= OOS_FIRST) & (rt["date"] <= OOS_LAST)]
    dates = {leg: ", ".join(d.date().isoformat() for d in rt.loc[rt["leg"] == leg, "date"]) for leg in ("ES", "ZN")}
    return ["## 3. Reference series", "",
            f"- OOS sessions {len(r)}; missing daily reference returns: ES {int(r['r_es'].isna().sum())}, "
            f"ZN {int(r['r_zn'].isna().sum())}",
            f"- Contract switches (8 per leg expected over two years): ES {int((rt['leg'] == 'ES').sum())} ({dates['ES']}); "
            f"ZN {int((rt['leg'] == 'ZN').sum())} ({dates['ZN']})", ""]


def minute_section(defs, ref, ev, ps, bbo, ohl, info) -> list[str]:
    outr = pd.concat([outright_definitions(defs, r).assign(root=r) for r in ("ES", "ZN")], ignore_index=True)
    r = ref[(ref.index >= OOS_FIRST) & (ref.index <= OOS_LAST)]
    relevant = set()
    for df in (ev[ev["usable"]], ps[ps["usable"]], r):
        for c in ("es_id", "zn_id"):
            relevant |= set(df[c].dropna().astype(int))
    batch_files = {Path(e["file"]).name for e in json.loads((ROOT / "data" / "manifest.json").read_text())["pulls"]
                   if e.get("job_id") in {j["job_id"] for j in _oos_jobs()}}
    out = ["## 4. Minute data (outrights requested by exchange symbol, 14:00-16:30 ET extract)", "",
           f"- Held or reference contracts in OOS: {len(relevant)} "
           f"({', '.join(sorted(outr.loc[outr['instrument_id'].isin(list(relevant)), 'symbol']))})"]
    for name, frame, key in (("bbo-1m", bbo, "bbo_1m_close"), ("ohlcv-1m", ohl, "ohlcv_1m_close")):
        seen = set(frame.loc[frame["ts_et"] >= OOS_FIRST, "instrument_id"].unique())
        miss = sorted(outr.loc[outr["instrument_id"].isin(list(relevant - seen)), "symbol"])
        files = {k: v for k, v in info[key]["files"].items() if k in batch_files or k.startswith("oos_")}
        out.append(f"- {name}: OOS files {len(files)} (records per file {min(files.values()):,}-{max(files.values()):,}); "
                   f"ids not among the outright definitions {len(seen - set(outr['instrument_id']))}; "
                   f"held or reference contracts with no OOS record: {miss or 'none'}")
    out.append("")
    return out


def quote_section(ref, ev, qual, quotes: QuoteBook, vol: dict[int, pd.Series]) -> list[str]:
    out = ["## 5. Quotes at the 15:59 ET fill minute", "",
           "Front = reference contract of the session (A8). Regular sessions only (early closes have no 15:59 minute, A2).", "",
           "| Year | Regular sessions | ES fresh | ZN fresh | ES median spread (ticks) | ZN median spread (ticks) |",
           "|---|---|---|---|---|---|"]
    reg = [d for d in qual if OOS_FIRST <= d <= OOS_LAST and not is_early_close(d)]
    rows = {}
    for d in reg:
        for leg in ("ES", "ZN"):
            iid = ref.at[d, f"{leg.lower()}_id"]
            ok, spr = cov._spread(quotes, int(iid), d + cov.FILL) if pd.notna(iid) else (False, np.nan)
            rows.setdefault((d.year, leg), []).append((ok, spr / cov.TICK[leg]))
    for y in sorted({k[0] for k in rows}):
        es, zn = np.array(rows[(y, "ES")]), np.array(rows[(y, "ZN")])
        out.append(f"| {y} | {len(es)} | {int(es[:, 0].sum())} | {int(zn[:, 0].sum())} | "
                   f"{np.nanmedian(es[:, 1]):.1f} | {np.nanmedian(zn[:, 1]):.1f} |")
    px = ev[ev["usable"] & ev["px_eligible"]]
    fails, spreads, vols = [], {"ES": [], "ZN": []}, {"ES": [], "ZN": []}
    for r in px.itertuples():
        for leg, iid in (("ES", int(r.es_id)), ("ZN", int(r.zn_id))):
            for tag, day in (("entry", r.L_m4), ("exit", r.exit)):
                ok, spr = cov._spread(quotes, iid, day + cov.FILL)
                spreads[leg].append(spr / cov.TICK[leg])
                v = vol.get(iid)
                vols[leg].append(float(v.get(day + cov.FILL, 0.0)) if v is not None else 0.0)
                if not ok:
                    fails.append(f"{r.month} {leg} {tag} {day.date()}")
    out += ["", f"Held contracts on PX fill days: {len(px)} usable PX-eligible OOS events x 2 legs x (entry L-4, exit F1).", "",
            f"- Fills without a fresh quote: {len(fails)}" + (f": {fails}" if fails else "")]
    for leg in ("ES", "ZN"):
        s, v = np.array(spreads[leg]), np.array(vols[leg])
        out.append(f"- {leg}: spread median {np.nanmedian(s):.1f}, 95th pct {np.nanpercentile(s, 95):.1f}, "
                   f"max {np.nanmax(s):.1f} ticks; 15:59 bar volume median {np.median(v):,.0f}, "
                   f"10th pct {np.percentile(v, 10):,.0f}, min {v.min():,.0f} contracts")
    out.append("")
    return out


def main() -> None:
    if not oos_unlocked():
        raise SystemExit("refusing to read OOS data before the freeze-final tag")
    cfg = frozen_config()
    info = build_derived(RAW, DERIVED)
    panels, bbo, ohl = load_derived(DERIVED)
    defs = pd.concat([_dbn(RAW / f"{s}.dbn.zst") for s in ("is_definition", "oos_definition")])
    qual = qualifying_sessions(panels["ES"]["date"].unique(), panels["ZN"]["date"].unique(), cfg.is_start, None)
    sched = trading_schedule(SessionCalendar(qual))
    es, zn = ContractPanel.from_long(panels["ES"], "ES"), ContractPanel.from_long(panels["ZN"], "ZN")
    ref = reference_returns(es, zn, qual)
    cond = json.loads((ROOT / "data" / "dataset_condition_oos.json").read_text())
    degraded = pd.DatetimeIndex([d["date"] for d in cond["not_available"]])

    lines = ["# Out-of-sample data coverage (2024-10-02 to 2026-10-02)", "",
             "Data quality only, run before the single OOS evaluation: no strategy returns were computed. "
             "Prices appear only as spreads in ticks.", "",
             f"Databento dataset condition, {cond['start_date']} to {cond['end_date']}: {cond['n_days']} days, "
             f"not 'available' on {len(degraded)}: "
             f"{', '.join(d['date'] + ' ' + d['condition'] for d in cond['not_available']) or 'none'}.", ""]
    lines += purchase_section()
    lines += settlement_section(panels)
    sec, ev, ps = schedule_section(es, zn, qual, sched, degraded)
    lines += sec
    lines += reference_section(ref)
    lines += minute_section(defs, ref, ev, ps, bbo, ohl, info)
    lines += quote_section(ref, ev, qual, QuoteBook(bbo), bar_volume(ohl))
    out = ROOT / "reports" / "oos_coverage.md"
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())


if __name__ == "__main__":
    main()
