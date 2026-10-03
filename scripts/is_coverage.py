"""In-sample data coverage check (2010-06-07 to 2024-10-01): data quality only, no returns.

Writes reports/is_coverage.md (aggregate counts only). Licensed data stays in
data/raw/ and in these derived extracts in data/derived/ (both git-ignored):

* settlements_ES.parquet, settlements_ZN.parquet: settlement panels (gqh.panel)
* bbo_1m_close.parquet: bbo-1m records stamped 14:00-16:30 ET
* ohlcv_1m_close.parquet: ohlcv-1m bars starting 14:00-16:30 ET

Run:  python scripts/is_coverage.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data"))

import download  # noqa: E402
from gqh.calendar import (SessionCalendar, audit_session_gaps, decision_shift,  # noqa: E402
                          is_early_close, qualifying_sessions, trading_schedule, xnys_sessions)
from gqh.contracts import ContractPanel, event_contracts, reference_returns, roll_table  # noqa: E402
from gqh.data import _dbn, add_selection_weight, bar_volume, build_derived, daily_volume, load_derived  # noqa: E402
from gqh.panel import build_settlement_panel, outright_definitions  # noqa: E402
from gqh.quotes import QuoteBook  # noqa: E402

RAW, DERIVED = ROOT / "data" / "raw", ROOT / "data" / "derived"
ET = "America/New_York"
IS_FIRST, IS_LAST = pd.Timestamp("2010-06-07"), pd.Timestamp("2024-10-01")
FILL = pd.Timedelta(hours=15, minutes=59)   # PX fill minute (A9)
TICK = {"ES": 0.25, "ZN": 0.015625}


def purchase_section() -> list[str]:
    man = json.loads((ROOT / "data" / "manifest.json").read_text())["pulls"]
    jobs_path = ROOT / "data" / "batch_jobs.json"
    jobs = json.loads(jobs_path.read_text())["jobs"] if jobs_path.is_file() else []
    batch_start = {j["parent_request"]: pd.Timestamp(j["start"]) for j in jobs}
    expected = []
    for n in ("is_definition", "is_statistics", "is_ohlcv_1m", "is_bbo_1m"):
        for stem, start, _ in download.chunks(n):   # streamed pieces, except those a batch job replaced
            if n in batch_start and pd.Timestamp(start) >= batch_start[n]:
                continue
            expected.append(stem)
    streamed = {e["request"]: e for e in man if e["request"] in expected}
    batch = [e for e in man if e.get("job_id")]
    ok = sum(download._sha256(ROOT / e["file"]) == e["sha256"]
             for e in [*streamed.values(), *batch] if (ROOT / e["file"]).is_file())
    cost = sum(e["quoted_cost_usd"] for e in streamed.values()) + sum(j["quoted_cost_usd"] for j in jobs)
    size = sum(e["bytes"] for e in [*streamed.values(), *batch])
    return ["## 0. Purchase", "",
            f"- Streamed files expected {len(expected)}, in manifest {len(streamed)}; missing: "
            f"{sorted(set(expected) - set(streamed)) or 'none'}",
            f"- Batch jobs {len(jobs)} ({', '.join(j['job_id'] + ' ' + j['parent_request'] + ' from ' + j['start'][:10] for j in jobs) or 'none'}); "
            f"batch files in manifest {len(batch)}",
            f"- SHA-256 matches on disk: {ok} of {len(streamed) + len(batch)}; quoted cost ${cost:.2f}; "
            f"{size / 1e9:.2f} GB compressed", ""]


def settlement_section(stats: pd.DataFrame, panels: dict[str, pd.DataFrame]) -> list[str]:
    xnys = xnys_sessions(IS_FIRST, IS_LAST)
    es_d, zn_d = panels["ES"]["date"].unique(), panels["ZN"]["date"].unique()
    gaps = audit_session_gaps(es_d, zn_d, IS_FIRST, IS_LAST)
    td = pd.to_datetime(stats["ts_ref"]).dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    tail = stats.loc[(td >= pd.Timestamp("2024-10-02")).to_numpy(), "stat_type"].value_counts().sort_index()
    out = ["## 1. Settlement coverage", "",
           f"- XNYS sessions {len(xnys)}; with an ES final settle {len(set(es_d) & set(xnys))}; "
           f"with a ZN final settle {len(set(zn_d) & set(xnys))}",
           f"- Gap-audit rows: {len(gaps)}"]
    out += [f"  - {r.date.date()}: {r.issue}" for r in gaps.itertuples()]
    for root, p in panels.items():
        fb = p.loc[~p["final_flag"].astype(bool)]
        out.append(f"- {root} settlements without a FINAL-flag record (last record used, A14): {len(fb)} of {len(p)}; "
                   f"by year {fb.groupby(fb['date'].dt.year).size().to_dict()}")
    out += [f"- Last settlement date in the panels: ES {panels['ES']['date'].max().date()}, "
            f"ZN {panels['ZN']['date'].max().date()} (2024-10-01 is the Sep-2024 exit)",
            f"- Statistics records with trade date >= 2024-10-02 in the raw file (A10 tail), by stat_type: "
            f"{ {int(k): int(v) for k, v in tail.items()} or 'none'}; rows in the panels: "
            f"{int(sum((p['date'] >= pd.Timestamp('2024-10-02')).sum() for p in panels.values()))}", ""]
    return out


def _why(r, es: ContractPanel, zn: ContractPanel, qual: pd.DatetimeIndex, valid_col: str) -> str:
    """Reason an IS (pseudo-)event is unusable."""
    if not getattr(r, valid_col):
        return f"{valid_col} False"
    if pd.isna(r.es_id) or pd.isna(r.zn_id):
        return "no contract selected"
    why = []
    if not r.tradable:
        why.append(f"untradable (ES exp {r.es_expiration.date()}, ZN FPD {r.zn_first_position_day.date()}, exit {r.exit.date()})")
    if not r.data_complete:
        window = qual[(qual >= r.anchor) & (qual <= r.exit)]
        for leg, p, iid in (("ES", es, int(r.es_id)), ("ZN", zn, int(r.zn_id))):
            miss = [d.date().isoformat() for d in window if not p.has_settles(iid, pd.DatetimeIndex([d]))]
            if miss:
                why.append(f"{leg} settle missing {miss}")
    return "; ".join(why)


def schedule_section(panels, es, zn, qual, sched, degraded) -> tuple[list[str], pd.DataFrame, pd.DataFrame]:
    shift = decision_shift(SessionCalendar(qual))
    flagged = shift[shift["event_shift"] | shift["pseudo_shift"]]
    out = ["## 2. Calendar, decision dates and events", "",
           f"- Qualifying sessions (ES and ZN final settle, XNYS open): {len(qual)}",
           f"- Months whose ex-ante dates differ from ex-post (A1): {len(flagged)}"]
    for r in flagged.itertuples():
        out.append(f"  - {r.month}: event shift {r.event_shift} (ex-ante L-5 {r.ex_ante_L_m5.date() if pd.notna(r.ex_ante_L_m5) else '-'}), "
                   f"pseudo shift {r.pseudo_shift}")
    frames = {}
    for kind, valid_col in (("event", "event_valid"), ("pseudo", "pseudo_valid")):
        ec = event_contracts(sched, es, zn, qual, kind=kind)
        df = pd.concat([sched[["sample", valid_col, "px_eligible", "L_m4"]].reset_index(drop=True), ec], axis=1)
        df = df[df["sample"] == "IS"].reset_index(drop=True)
        df["usable"] = df[valid_col] & df["tradable"] & df["data_complete"]
        frames[kind] = df
        out.append(f"- {kind}s in IS: {len(df)}; usable (valid, tradable, data complete): {int(df['usable'].sum())}"
                   + (f"; usable and PX-eligible: {int((df['usable'] & df['px_eligible']).sum())}" if kind == "event" else ""))
        out += [f"  - {r.month}: {_why(r, es, zn, qual, valid_col)}" for r in df[~df["usable"]].itertuples()]
    for kind, df in frames.items():
        hits = []
        for r in df[df["usable"]].itertuples():
            days = [d for d in degraded if r.anchor <= d <= r.exit]
            if days:
                hits.append(f"{r.month} ({', '.join(d.date().isoformat() for d in days)})")
        out.append(f"- Usable IS {kind}s whose window (anchor..exit) touches a Databento-degraded day: {len(hits)}"
                   + (f": {hits}" if hits else ""))
    out.append("")
    return out, frames["event"], frames["pseudo"]


def reference_section(ref: pd.DataFrame) -> list[str]:
    rt = roll_table(ref)
    per = rt.groupby([rt["date"].dt.year, "leg"]).size().unstack(fill_value=0)
    odd = per[(per != 4).any(axis=1)]
    return ["## 3. Reference series", "",
            f"- Missing daily reference returns (after the first session): ES {int(ref['r_es'].iloc[1:].isna().sum())}, "
            f"ZN {int(ref['r_zn'].iloc[1:].isna().sum())}",
            f"- Contract switches: ES {int((rt['leg'] == 'ES').sum())}, ZN {int((rt['leg'] == 'ZN').sum())}; "
            f"years with other than 4 per leg (2010 and 2024 are partial): "
            f"{odd.to_dict(orient='index') or 'none'}", ""]


def selection_section(panels: dict[str, pd.DataFrame], sched: pd.DataFrame, qual: pd.DatetimeIndex) -> list[str]:
    """A14 check: on dates with open interest, does the volume ranking pick the same contract?"""
    out = ["## 3b. Contract selection without open interest (A14)", ""]
    for root, p in panels.items():
        src = p.groupby(p["date"].dt.year)["selection_source"].agg(lambda x: (x == "volume_1m").mean())
        out.append(f"- {root}: share of panel rows ranked by traded volume, by year: "
                   f"{ {int(k): round(float(v), 3) for k, v in src.items() if v > 0} }")
    oi_era = {r: p[p["selection_source"] == "open_interest"] for r, p in panels.items()}
    by = {w: {r: ContractPanel.from_long(p.assign(selection_weight=p[w]), r) for r, p in oi_era.items()}
          for w in ("open_interest", "volume_1m")}
    days = qual[qual >= oi_era["ES"]["date"].min()]
    for root in ("ES", "ZN"):
        same = n = 0
        for prev, t in zip(days[:-1], days[1:]):
            a = by["open_interest"][root].max_oi(prev, tradable_on=t)
            b = by["volume_1m"][root].max_oi(prev, tradable_on=t)
            if a is not None:
                n += 1
                same += int(a == b)
        out.append(f"- {root} reference contract, {days[0].date()} to {days[-1].date()}: volume ranking agrees with "
                   f"open interest on {same}/{n} sessions ({same / max(n, 1):.1%})")
    ev = sched[(sched["L_m8"] >= days[0]) & (sched["sample"] == "IS")]
    agree = [by["open_interest"]["ES"].max_oi(d) == by["volume_1m"]["ES"].max_oi(d) for d in ev["L_m8"]]
    out += [f"- ES event contract at L-8: volume ranking agrees with open interest on {sum(agree)}/{len(agree)} events", ""]
    return out


def minute_section(defs, ref, ev, ps, qual, bbo, ohl, years, on_min) -> list[str]:
    outr = pd.concat([outright_definitions(defs, r).assign(root=r) for r in ("ES", "ZN")], ignore_index=True)
    outr = outr[outr["expiration"] >= IS_FIRST]
    ids = {"bbo-1m": set(bbo["instrument_id"].unique()), "ohlcv-1m": set(ohl["instrument_id"].unique())}
    relevant = set()
    for df, cols in ((ev[ev["usable"]], ("es_id", "zn_id")), (ps[ps["usable"]], ("es_id", "zn_id")), (ref, ("es_id", "zn_id"))):
        for c in cols:
            relevant |= set(df[c].dropna().astype(int))
    out = ["## 4. Minute data (outrights requested by exchange symbol, 14:00-16:30 ET extract)", "",
           f"- Outrights alive in IS per definitions: {len(outr)} (ES {int((outr['root'] == 'ES').sum())}, "
           f"ZN {int((outr['root'] == 'ZN').sum())}); held or reference contracts: {len(relevant)}"]
    for name, seen in ids.items():
        miss = outr[~outr["instrument_id"].isin(seen)]
        out.append(f"- {name}: ids not in the outright definitions {len(seen - set(outr['instrument_id']))}; "
                   f"outrights with no 14:00-16:30 record {len(miss)}; of them held or reference: "
                   f"{sorted(miss.loc[miss['instrument_id'].isin(relevant), 'symbol'])}")
        y = years[name]
        out.append(f"  - records per year {min(y.values()):,}-{max(y.values()):,}; stamped on a minute boundary {on_min[name]:.1%}")
    reused = outr.groupby("symbol")["instrument_id"].nunique()
    reused = reused[reused > 1].index
    rel_reused = outr[outr["symbol"].isin(reused) & outr["instrument_id"].isin(relevant)]
    out.append(f"- Symbols reused across decades: {len(reused)}; their held/reference contracts present in both "
               f"files: {int(rel_reused['instrument_id'].isin(ids['bbo-1m'] & ids['ohlcv-1m']).sum())}/{len(rel_reused)}")
    out.append("")
    return out


def _spread(quotes: QuoteBook, iid: int, t: pd.Timestamp) -> tuple[bool, float]:
    qt = quotes(iid, t)
    return (False, np.nan) if qt is None else (True, qt[1] - qt[0])


def quote_section(ref, ev, qual, quotes: QuoteBook, vol: dict[int, pd.Series]) -> list[str]:
    out = ["## 5. Quotes at the 15:59 ET fill minute", "",
           "Front = reference contract of the session (A8). Regular sessions only (early closes have no 15:59 minute, A2).", "",
           "| Year | Regular sessions | ES fresh | ZN fresh | ES median spread (ticks) | ZN median spread (ticks) |",
           "|---|---|---|---|---|---|"]
    reg = [d for d in qual[1:] if not is_early_close(d)]
    rows = {}
    for d in reg:
        for leg in ("ES", "ZN"):
            iid = ref.at[d, f"{leg.lower()}_id"]
            ok, spr = _spread(quotes, int(iid), d + FILL) if pd.notna(iid) else (False, np.nan)
            rows.setdefault((d.year, leg), []).append((ok, spr / TICK[leg]))
    for y in sorted({k[0] for k in rows}):
        es, zn = np.array(rows[(y, "ES")]), np.array(rows[(y, "ZN")])
        out.append(f"| {y} | {len(es)} | {int(es[:, 0].sum())} | {int(zn[:, 0].sum())} | "
                   f"{np.nanmedian(es[:, 1]):.1f} | {np.nanmedian(zn[:, 1]):.1f} |")
    px = ev[ev["usable"] & ev["px_eligible"]]
    fails, spreads, vols = [], {"ES": [], "ZN": []}, {"ES": [], "ZN": []}
    for r in px.itertuples():
        for leg, iid in (("ES", int(r.es_id)), ("ZN", int(r.zn_id))):
            for tag, day in (("entry", r.L_m4), ("exit", r.exit)):
                ok, spr = _spread(quotes, iid, day + FILL)
                spreads[leg].append(spr / TICK[leg])
                v = vol.get(iid)
                vols[leg].append(float(v.get(day + FILL, 0.0)) if v is not None else 0.0)
                if not ok:
                    fails.append(f"{r.month} {leg} {tag} {day.date()}")
    out += ["", f"Held contracts on PX fill days: {len(px)} usable PX-eligible IS events x 2 legs x (entry L-4, exit F1).", "",
            f"- Fills without a fresh quote: {len(fails)}" + (f": {fails}" if fails else "")]
    for leg in ("ES", "ZN"):
        s, v = np.array(spreads[leg]), np.array(vols[leg])
        out.append(f"- {leg}: spread median {np.nanmedian(s):.1f}, 95th pct {np.nanpercentile(s, 95):.1f}, "
                   f"max {np.nanmax(s):.1f} ticks; 15:59 bar volume median {np.median(v):,.0f}, "
                   f"10th pct {np.percentile(v, 10):,.0f}, min {v.min():,.0f} contracts")
    out.append("")
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--settlements-only", action="store_true", help="skip the minute-data sections (4-5)")
    settle_only = ap.parse_args().settlements_only
    if settle_only:
        st_raw, df_raw = _dbn(RAW / "is_statistics.dbn.zst"), _dbn(RAW / "is_definition.dbn.zst")
        DERIVED.mkdir(parents=True, exist_ok=True)
        vol = daily_volume(sorted(RAW.glob("is_ohlcv_1m_*.dbn.zst")))
        vol.to_parquet(DERIVED / "daily_volume.parquet", index=False)
        for root in ("ES", "ZN"):
            add_selection_weight(build_settlement_panel(st_raw, df_raw, root), vol).to_parquet(
                DERIVED / f"settlements_{root}.parquet", index=False)
        panels = {r: pd.read_parquet(DERIVED / f"settlements_{r}.parquet") for r in ("ES", "ZN")}
    else:
        info = build_derived(RAW, DERIVED)
        panels, bbo, ohl = load_derived(DERIVED)
    stats, defs = (st_raw, df_raw) if settle_only else (_dbn(RAW / "is_statistics.dbn.zst"),
                                                        _dbn(RAW / "is_definition.dbn.zst"))
    qual = qualifying_sessions(panels["ES"]["date"].unique(), panels["ZN"]["date"].unique(), IS_FIRST, IS_LAST)
    sched = trading_schedule(SessionCalendar(qual))
    es, zn = ContractPanel.from_long(panels["ES"], "ES"), ContractPanel.from_long(panels["ZN"], "ZN")
    ref = reference_returns(es, zn, qual)
    cond = json.loads((ROOT / "data" / "dataset_condition.json").read_text())
    degraded = pd.DatetimeIndex([d["date"] for d in cond["not_available"]])

    lines = ["# In-sample data coverage (2010-06-07 to 2024-10-01)", "",
             "Data quality only: no strategy returns were computed. Prices appear only as spreads in ticks.", "",
             f"Databento dataset condition, {cond['start_date']} to {cond['end_date']}: {cond['n_days']} days, "
             f"not 'available' on {len(degraded)}: "
             f"{', '.join(d['date'] + ' ' + d['condition'] for d in cond['not_available']) or 'none'}.", ""]
    lines += purchase_section()
    lines += settlement_section(stats, panels)
    sec, ev, ps = schedule_section(panels, es, zn, qual, sched, degraded)
    lines += sec
    lines += reference_section(ref)
    lines += selection_section(panels, sched, qual)
    if settle_only:
        lines += ["## 4-5. Minute data", "", "Not run (--settlements-only): bbo-1m still downloading.", ""]
        out = ROOT / "reports" / "is_coverage.md"
        out.write_text("\n".join(lines) + "\n")
        print(out.read_text())
        return
    lines += minute_section(defs, ref, ev, ps, qual, bbo, ohl,
                            {"bbo-1m": info["bbo_1m_close"]["files"], "ohlcv-1m": info["ohlcv_1m_close"]["files"]},
                            {"bbo-1m": info["bbo_1m_close"]["share_on_minute"],
                             "ohlcv-1m": info["ohlcv_1m_close"]["share_on_minute"]})
    lines += quote_section(ref, ev, qual, QuoteBook(bbo), bar_volume(ohl))
    out = ROOT / "reports" / "is_coverage.md"
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())


if __name__ == "__main__":
    main()
