"""Ken French daily factors (FF3 + momentum) for the factor regression (frozen.yaml ``data.factors``).

Downloads the two public CSV zips from the Kenneth R. French Data Library into
data/factors/ (git-ignored), records each file's URL, retrieval time and SHA-256 in
data/factors/manifest.json (committed), and writes data/factors/daily_factors.csv
with decimal daily returns: Mkt-RF, SMB, HML, RF, Mom.

Run:  python data/download_factors.py
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "factors"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"ff3": "F-F_Research_Data_Factors_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}


def _daily_table(raw: bytes) -> pd.DataFrame:
    """Rows whose first field is an 8-digit date; values are percent."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    header_i = next(i for i, ln in enumerate(lines) if ln.strip().startswith(",") or ln.lower().startswith(",mkt") or
                    (ln.count(",") >= 1 and not ln.split(",")[0].strip() and i + 1 < len(lines)
                     and lines[i + 1].split(",")[0].strip().isdigit()))
    cols = [c.strip() for c in lines[header_i].split(",")[1:]]
    rows = []
    for ln in lines[header_i + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) != len(cols) + 1 or not (parts[0].isdigit() and len(parts[0]) == 8):
            if rows:
                break
            continue
        rows.append([pd.Timestamp(parts[0])] + [float(v) / 100.0 for v in parts[1:]])
    return pd.DataFrame(rows, columns=["date", *cols]).set_index("date")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, tables = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {}}, {}
    for key, name in FILES.items():
        req = urllib.request.Request(BASE + name, headers={"User-Agent": "gqh-rebalancing-tax research"})
        raw = urllib.request.urlopen(req, timeout=60).read()
        (OUT / name).write_bytes(raw)
        manifest["files"][key] = {"url": BASE + name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        tables[key] = _daily_table(raw)
    df = tables["ff3"].join(tables["mom"].rename(columns=lambda c: "Mom" if c.lower().startswith("mom") else c), how="inner")
    df.to_csv(OUT / "daily_factors.csv")
    manifest["daily_factors"] = {"rows": int(len(df)), "first": str(df.index.min().date()), "last": str(df.index.max().date()),
                                 "columns": list(df.columns)}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
