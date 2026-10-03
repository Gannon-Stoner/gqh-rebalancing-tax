"""Databento request plan, cost check and (later) cached downloads.

Usage:
    python data/download.py            # cost check only: free metadata calls, nothing downloaded
    python data/download.py --pull pilot   # download the pilot requests (paid; asks first)

The API key is read from DATABENTO_API_KEY (environment or the repo's .env file);
it is never printed or written anywhere. Raw data goes to data/raw/ (git-ignored).
Out-of-sample dates (>= 2024-10-02) are not requested until the freeze-final tag exists.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = "GLBX.MDP3"
SYMBOLS = ["ES.FUT", "ZN.FUT"]          # parent symbology: every ES / ZN contract (outrights and spreads)
IS_START, IS_END_EXCL = "2010-06-06", "2024-10-02"
PILOT_START, PILOT_END_EXCL = "2020-10-01", "2021-02-01"   # covers both clock changes and a ZN roll

# name -> (schema, start, end_exclusive, purpose)
PLAN = {
    "pilot_definition": ("definition", PILOT_START, PILOT_END_EXCL, "contract metadata: ids, expirations, tick, multiplier"),
    "pilot_statistics": ("statistics", PILOT_START, PILOT_END_EXCL, "final settlements, open interest, cleared volume"),
    "pilot_bbo_1m": ("bbo-1m", PILOT_START, PILOT_END_EXCL, "1-minute best bid/offer: executable fills, clock checks"),
    "pilot_ohlcv_1m": ("ohlcv-1m", PILOT_START, PILOT_END_EXCL, "1-minute volume in execution windows (capacity)"),
    "is_definition": ("definition", IS_START, IS_END_EXCL, "full in-sample contract metadata"),
    "is_statistics": ("statistics", IS_START, IS_END_EXCL, "full in-sample settlements / OI / volume"),
}


def api_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY", "")
    env = ROOT / ".env"
    if not key and env.is_file():
        for line in env.read_text().splitlines():
            if line.strip().startswith("DATABENTO_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("DATABENTO_API_KEY not set: add it to .env (see .env)")
    return key


def cost_check() -> list[dict]:
    import databento as db

    client = db.Historical(api_key())
    rows = []
    for name, (schema, start, end, purpose) in PLAN.items():
        kw = dict(dataset=DATASET, symbols=SYMBOLS, stype_in="parent", schema=schema, start=start, end=end)
        rows.append({
            "request": name, "schema": schema, "start": start, "end_exclusive": end, "purpose": purpose,
            "cost_usd": round(float(client.metadata.get_cost(**kw)), 4),
            "billable_bytes": int(client.metadata.get_billable_size(**kw)),
            "records": int(client.metadata.get_record_count(**kw)),
        })
    out = ROOT / "data" / "cost_quotes.json"
    out.write_text(json.dumps({"quoted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "dataset": DATASET, "symbols": SYMBOLS, "requests": rows}, indent=2))
    return rows


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pull(names: list[str]) -> None:
    """Download requests to data/raw/<name>.dbn.zst and record them in data/manifest.json."""
    import databento as db

    if any(PLAN[n][2] > "2024-10-02" for n in names):
        raise SystemExit("refusing to pull out-of-sample dates before freeze-final")
    client = db.Historical(api_key())
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"pulls": []}
    for name in names:
        schema, start, end, purpose = PLAN[name]
        kw = dict(dataset=DATASET, symbols=SYMBOLS, stype_in="parent", schema=schema, start=start, end=end)
        quote = float(client.metadata.get_cost(**kw))
        path = raw / f"{name}.dbn.zst"
        client.timeseries.get_range(**kw, path=str(path))
        entry = {"request": name, **{k: v for k, v in kw.items()}, "purpose": purpose, "quoted_cost_usd": round(quote, 4),
                 "file": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": _sha256(path),
                 "pulled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        manifest["pulls"] = [e for e in manifest["pulls"] if e["request"] != name] + [entry]
        print(f"{name:<18} ${quote:6.2f}  {entry['bytes'] / 1e6:8.1f} MB  sha256 {entry['sha256'][:12]}")
    manifest_path.write_text(json.dumps(manifest, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", choices=["pilot"], help="download (paid); default is cost check only")
    args = ap.parse_args()
    if args.pull:
        pull([k for k in PLAN if k.startswith(args.pull + "_")])
        return
    rows = cost_check()
    total = 0.0
    for r in rows:
        total += r["cost_usd"]
        print(f"{r['request']:<18} {r['schema']:<11} {r['start']}..{r['end_exclusive']}  "
              f"${r['cost_usd']:>9.2f}  {r['billable_bytes'] / 1e9:8.3f} GB  {r['records']:>12,d} records")
    print(f"{'TOTAL':<18} {'':<11} {'':<22}  ${total:>9.2f}")


if __name__ == "__main__":
    main()
