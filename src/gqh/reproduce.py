"""One command rebuilds every number: ``python -m gqh.reproduce``.

Steps: raw Databento files (data/raw, recorded in data/manifest.json) -> derived
panels and minute extracts (data/derived) -> ``gqh.pipeline.evaluate`` -> a JSON
file with sorted keys and floats rounded to 10 significant digits, so two runs
are byte-identical. Every run is appended to trials.jsonl.

Guards (HYPOTHESIS.md run order): a real-data run needs the ``freeze-is`` tag (no
in-sample returns are computed before the freeze), and ``--sample ALL`` needs the
``freeze-final`` tag (``gqh.panel`` also refuses OOS dates before it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gqh.config import frozen_config, repo_root
from gqh.data import build_derived, load_derived
from gqh.pipeline import evaluate, prepare


def clean(obj: Any, digits: int = 10) -> Any:
    """JSON-safe copy: numpy scalars to Python, floats to ``digits`` significant digits, NaN/inf to None."""
    if isinstance(obj, dict):
        return {str(k): clean(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v, digits) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        if not math.isfinite(x):
            return None
        return float(f"{x:.{digits}g}")
    if isinstance(obj, (pd.Timestamp, pd.Period)):
        return str(obj)
    return obj


def dumps(results: dict) -> str:
    return json.dumps(clean(results), indent=1, sort_keys=True) + "\n"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo_root(), capture_output=True, text=True).stdout.strip()


def _tag_exists(tag: str) -> bool:
    return tag in _git("tag", "-l", tag).split()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_margins(root: Path) -> dict | None:
    """CME maintenance margins per contract from config/margins.yaml (dated and sourced there)."""
    import yaml

    f = root / "config" / "margins.yaml"
    return {k: float(v) for k, v in yaml.safe_load(f.read_text())["maintenance_usd"].items()} if f.is_file() else None


def _margins_meta(root: Path) -> str:
    import yaml

    return str(yaml.safe_load((root / "config" / "margins.yaml").read_text())["as_of"])


def load_factors(root: Path) -> pd.DataFrame | None:
    """Ken French daily Mkt-RF, SMB, HML, Mom (decimal) from data/factors/daily_factors.csv, if present.

    Dates after ``is_end`` are dropped until the ``freeze-final`` tag exists (same guard as market data).
    """
    f = root / "data" / "factors" / "daily_factors.csv"
    if not f.is_file():
        return None
    cfg = frozen_config()
    df = pd.read_csv(f, index_col=0, parse_dates=True)[["Mkt-RF", "SMB", "HML", "Mom"]]
    return df if _tag_exists(cfg.oos_unlock_tag) else df[df.index <= cfg.is_end]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m gqh.reproduce")
    ap.add_argument("--sample", choices=["IS", "ALL"], default="IS")
    ap.add_argument("--draws", type=int, default=9999)
    ap.add_argument("--rebuild", action="store_true", help="rebuild data/derived from data/raw")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    cfg = frozen_config()
    root = repo_root()
    if not _tag_exists("freeze-is"):
        raise SystemExit("refusing a real-data run before the freeze-is tag (run order step 6)")
    if a.sample == "ALL" and not _tag_exists(cfg.oos_unlock_tag):
        raise SystemExit(f"refusing OOS before the {cfg.oos_unlock_tag} tag")
    raw, derived = root / "data" / "raw", root / "data" / "derived"
    if a.rebuild or not (derived / "settlements_ES.parquet").is_file():
        build_derived(raw, derived)
    panels, bbo, ohlcv = load_derived(derived)
    end = cfg.is_end if a.sample == "IS" else None
    world = prepare(panels, start=cfg.is_start, end=end, cfg=cfg)
    margins = load_margins(root)
    factors = load_factors(root)
    res = evaluate(world, bbo, ohlcv, cfg=cfg, draws=a.draws, samples=("IS",) if a.sample == "IS" else ("IS", "OOS"),
                   margins=margins, factors=factors)
    res["inputs"] = {"margins_as_of": margins and _margins_meta(root), "factors": factors is not None}
    res["provenance"] = {"commit": _git("rev-parse", "HEAD"), "manifest_sha256": _sha(root / "data" / "manifest.json"),
                         "derived_sha256": {p.name: _sha(p) for p in sorted(derived.glob("*.parquet"))}}
    out = a.out or root / ("results_is.json" if a.sample == "IS" else "results.json")
    text = dumps(res)
    out.write_text(text)
    with (root / "trials.jsonl").open("a") as f:
        f.write(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": "reproduce",
                            "sample": a.sample, "commit": res["provenance"]["commit"], "draws": a.draws,
                            "results_sha256": hashlib.sha256(text.encode()).hexdigest(), "out": out.name}) + "\n")
    print(f"wrote {out} ({hashlib.sha256(text.encode()).hexdigest()[:12]})")


if __name__ == "__main__":
    main()
