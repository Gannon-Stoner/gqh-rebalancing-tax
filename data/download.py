"""Databento request plan, cost check and cached downloads.

Usage:
    python data/download.py               # cost check only: free metadata calls, nothing downloaded
    python data/download.py --pull pilot  # download the pilot requests (paid)
    python data/download.py --pull is     # download the full in-sample requests (paid; resumable)

The API key is read from DATABENTO_API_KEY (environment or the repo's .env file);
it is never printed or written anywhere. Raw data goes to data/raw/ (git-ignored);
every downloaded file is recorded in data/manifest.json with its request and SHA-256.

Out-of-sample guard: before the freeze-final tag exists, no request may end after
2024-10-02 06:00 UTC. That tail (amendment A10) only exists so the statistics pull
captures the final settlement of the last in-sample trade date (2024-10-01), which
CME can publish after midnight UTC; records referring to later trade dates are
dropped by gqh.panel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATASET = "GLBX.MDP3"
PARENTS = ["ES.FUT", "ZN.FUT"]   # parent symbology: every ES / ZN contract, outrights and spreads
# Outright quarterly contracts by exchange symbol. One-digit years repeat each decade;
# Databento resolves each raw symbol to the contract listed on each date.
OUTRIGHTS = [f"{root}{month}{year}" for root in ("ES", "ZN") for month in "HMUZ" for year in range(10)]
IS_START, IS_END_EXCL, STATS_END_EXCL = "2010-06-06", "2024-10-02", "2024-10-02T06:00:00Z"
PILOT_START, PILOT_END_EXCL = "2020-10-01", "2021-02-01"   # covers both clock changes and a ZN roll
PRE_FREEZE_LIMIT = pd.Timestamp("2024-10-02T06:00:00Z")


@dataclass(frozen=True)
class Request:
    schema: str
    start: str
    end: str                      # exclusive
    purpose: str
    symbols: tuple[str, ...] = tuple(PARENTS)
    stype_in: str = "parent"
    yearly: bool = False          # split into calendar-year files (large minute schemas)


PLAN: dict[str, Request] = {
    "pilot_definition": Request("definition", PILOT_START, PILOT_END_EXCL, "contract metadata: ids, expirations, tick, multiplier"),
    "pilot_statistics": Request("statistics", PILOT_START, PILOT_END_EXCL, "final settlements, open interest, cleared volume"),
    "pilot_bbo_1m": Request("bbo-1m", PILOT_START, PILOT_END_EXCL, "1-minute best bid/offer: executable fills, clock checks"),
    "pilot_ohlcv_1m": Request("ohlcv-1m", PILOT_START, PILOT_END_EXCL, "1-minute volume in execution windows (capacity)"),
    "is_definition": Request("definition", IS_START, IS_END_EXCL, "in-sample contract metadata"),
    "is_statistics": Request("statistics", IS_START, STATS_END_EXCL, "in-sample settlements / OI / volume (tail: A10)"),
    "is_ohlcv_1m": Request("ohlcv-1m", IS_START, IS_END_EXCL, "in-sample 1-minute volume, outrights only",
                           tuple(OUTRIGHTS), "raw_symbol", yearly=True),
    "is_bbo_1m": Request("bbo-1m", IS_START, IS_END_EXCL, "in-sample 1-minute best bid/offer, outrights only",
                         tuple(OUTRIGHTS), "raw_symbol", yearly=True),
}


def api_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY", "")
    env = ROOT / ".env"
    if not key and env.is_file():
        for line in env.read_text().splitlines():
            if line.strip().startswith("DATABENTO_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("DATABENTO_API_KEY not set: add it to .env (see .env.example)")
    return key


def _utc(ts: str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def chunks(name: str) -> list[tuple[str, str, str]]:
    """(file stem, start, end) pieces of a request: one per calendar year if ``yearly``."""
    r = PLAN[name]
    if not r.yearly:
        return [(name, r.start, r.end)]
    start, end = _utc(r.start), _utc(r.end)
    out = []
    for year in range(start.year, end.year + 1):
        lo = max(start, pd.Timestamp(f"{year}-01-01", tz="UTC"))
        hi = min(end, pd.Timestamp(f"{year + 1}-01-01", tz="UTC"))
        if lo < hi:
            out.append((f"{name}_{year}", lo.isoformat(), hi.isoformat()))
    return out


def _kwargs(r: Request, start: str, end: str) -> dict:
    return dict(dataset=DATASET, symbols=list(r.symbols), stype_in=r.stype_in, schema=r.schema, start=start, end=end)


def _oos_unlocked() -> bool:
    try:
        out = subprocess.run(["git", "tag", "-l", "freeze-final"], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return "freeze-final" in out.stdout.split()


def cost_check(names: list[str] | None = None) -> list[dict]:
    import databento as db

    client = db.Historical(api_key())
    rows = []
    for name in names or list(PLAN):
        r = PLAN[name]
        kw = _kwargs(r, r.start, r.end)
        rows.append({
            "request": name, "schema": r.schema, "start": r.start, "end_exclusive": r.end, "purpose": r.purpose,
            "stype_in": r.stype_in, "n_symbols": len(r.symbols),
            "cost_usd": round(float(client.metadata.get_cost(**kw)), 4),
            "billable_bytes": int(client.metadata.get_billable_size(**kw)),
            "records": int(client.metadata.get_record_count(**kw)),
        })
    (ROOT / "data" / "cost_quotes.json").write_text(json.dumps(
        {"quoted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dataset": DATASET,
         "requests": rows}, indent=2))
    return rows


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pull(names: list[str]) -> None:
    """Download requests to data/raw/<stem>.dbn.zst; skip pieces already in the manifest."""
    import databento as db

    if not _oos_unlocked() and any(_utc(PLAN[n].end) > PRE_FREEZE_LIMIT for n in names):
        raise SystemExit("refusing to pull out-of-sample dates before freeze-final")
    client = db.Historical(api_key())
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"pulls": []}
    done = {e["request"]: e for e in manifest["pulls"]}
    total = 0.0
    for name in names:
        r = PLAN[name]
        for stem, start, end in chunks(name):
            path = raw / f"{stem}.dbn.zst"
            if stem in done and path.is_file() and _sha256(path) == done[stem]["sha256"]:
                print(f"{stem:<22} already downloaded, skipped")
                continue
            if path.is_file():   # a partial file from an interrupted run (not in the manifest): start it over
                print(f"{stem:<22} removing incomplete file ({path.stat().st_size / 1e6:.1f} MB)", flush=True)
                path.unlink()
            kw = _kwargs(r, start, end)
            quote = float(client.metadata.get_cost(**kw))
            client.timeseries.get_range(**kw, path=str(path))
            entry = {"request": stem, "parent_request": name, **kw, "purpose": r.purpose,
                     "quoted_cost_usd": round(quote, 4), "file": str(path.relative_to(ROOT)),
                     "bytes": path.stat().st_size, "sha256": _sha256(path),
                     "pulled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            manifest["pulls"] = [e for e in manifest["pulls"] if e["request"] != stem] + [entry]
            manifest_path.write_text(json.dumps(manifest, indent=2))   # after every piece: resumable
            total += quote
            print(f"{stem:<22} ${quote:7.2f}  {entry['bytes'] / 1e6:9.1f} MB  sha256 {entry['sha256'][:12]}", flush=True)
    print(f"{'TOTAL quoted this run':<22} ${total:7.2f}")


def submit_batch(name: str, start: str) -> dict:
    """Submit the rest of a request (from ``start`` to its end) as one Databento batch job (paid).

    Streaming is throttled on Databento's side for long minute-data requests; a batch
    job prepares monthly files server-side for a fast download. Recorded in
    data/batch_jobs.json; files are fetched and hashed by :func:`fetch_batch`.
    """
    import databento as db

    r = PLAN[name]
    if not _oos_unlocked() and _utc(r.end) > PRE_FREEZE_LIMIT:
        raise SystemExit("refusing to pull out-of-sample dates before freeze-final")
    client = db.Historical(api_key())
    kw = _kwargs(r, _utc(start).isoformat(), r.end)
    quote = float(client.metadata.get_cost(**kw))
    job = client.batch.submit_job(**kw, encoding="dbn", compression="zstd", split_duration="month")
    jobs_path = ROOT / "data" / "batch_jobs.json"
    jobs = json.loads(jobs_path.read_text()) if jobs_path.is_file() else {"jobs": []}
    jobs["jobs"].append({"job_id": job["id"], "parent_request": name, "start": kw["start"], "end": kw["end"],
                         "schema": r.schema, "stype_in": r.stype_in, "n_symbols": len(r.symbols),
                         "quoted_cost_usd": round(quote, 4), "split_duration": "month",
                         "submitted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    jobs_path.write_text(json.dumps(jobs, indent=2))
    print(f"submitted {job['id']} for {name} {kw['start']}..{kw['end']}: quoted ${quote:.2f}")
    return job


def fetch_batch(job_id: str) -> list[Path]:
    """Download a finished batch job to data/raw/batch/<job_id>/ and record every data file in the manifest."""
    import databento as db

    client = db.Historical(api_key())
    out = ROOT / "data" / "raw" / "batch"
    files = client.batch.download(job_id=job_id, output_dir=out)
    jobs = json.loads((ROOT / "data" / "batch_jobs.json").read_text())["jobs"]
    job = next(j for j in jobs if j["job_id"] == job_id)
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for f in sorted(Path(x) for x in files):
        if not f.name.endswith(".dbn.zst"):
            continue
        stem = f"{job['parent_request']}_batch_{f.name.split('.')[0]}"
        entry = {"request": stem, "parent_request": job["parent_request"], "job_id": job_id, "dataset": DATASET,
                 "schema": job["schema"], "stype_in": job["stype_in"], "file": str(f.relative_to(ROOT)),
                 "bytes": f.stat().st_size, "sha256": _sha256(f),
                 "pulled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        manifest["pulls"] = [e for e in manifest["pulls"] if e["request"] != stem] + [entry]
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"fetched {len(files)} files for {job_id}")
    return [Path(x) for x in files]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", choices=["pilot", "is"], help="download (paid); default is cost check only")
    ap.add_argument("--batch-submit", metavar="REQUEST", help="submit REQUEST from --start to its end as a batch job (paid)")
    ap.add_argument("--start", help="batch start (UTC date)")
    ap.add_argument("--batch-fetch", metavar="JOB_ID", help="download a finished batch job")
    args = ap.parse_args()
    if args.batch_submit:
        submit_batch(args.batch_submit, args.start)
        return
    if args.batch_fetch:
        fetch_batch(args.batch_fetch)
        return
    if args.pull:
        pull([k for k in PLAN if k.startswith(args.pull + "_")])
        return
    rows = cost_check()
    total = 0.0
    for r in rows:
        total += r["cost_usd"]
        print(f"{r['request']:<18} {r['schema']:<11} {r['start']}..{r['end_exclusive']:<22} "
              f"${r['cost_usd']:>9.2f}  {r['billable_bytes'] / 1e9:8.3f} GB  {r['records']:>12,d} records")
    print(f"{'TOTAL':<18} ${total:>9.2f}")


if __name__ == "__main__":
    main()
