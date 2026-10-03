"""Masked dry run of the full pipeline on real IS data, before the freeze-is tag.

Runs ``gqh.pipeline.evaluate`` end to end so that a crash or a silent accounting bug
surfaces before the one-time in-sample run, without anyone seeing results. Prints
structure only: which sections exist, how many values the note needs are missing,
whether Backtrader reproduces the engine on every trade, and fill-reason counts.
No return, Sharpe ratio, p-value, coefficient or gate decision is printed or kept;
the results object is discarded and only its SHA-256 is logged to trials.jsonl.

Run:  python scripts/masked_dry_run.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gqh.config import frozen_config  # noqa: E402
from gqh.data import load_derived  # noqa: E402
from gqh.pipeline import evaluate, prepare  # noqa: E402
from gqh.reproduce import dumps, load_factors, load_margins  # noqa: E402

REQUIRED = ["confirmatory", "oos_slopes", "rows_IS", "risk_IS", "diagnostics", "backtrader_replay", "stacked_panel"]


def _count_none(obj) -> int:
    if isinstance(obj, dict):
        return sum(_count_none(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_none(v) for v in obj)
    return int(obj is None)


def _none_paths(obj, path: str = "") -> list[str]:
    """Dotted paths of None values (keys only, never values); list positions collapsed to [i]."""
    if isinstance(obj, dict):
        return [q for k, v in obj.items() for q in _none_paths(v, f"{path}.{k}" if path else k)]
    if isinstance(obj, list):
        return sorted({q for v in obj for q in _none_paths(v, f"{path}[i]")})
    return [path] if obj is None else []


def main() -> None:
    cfg = frozen_config()
    t0 = time.time()
    panels, bbo, ohlcv = load_derived(ROOT / "data" / "derived")
    world = prepare(panels, start=cfg.is_start, end=cfg.is_end, cfg=cfg)
    res = evaluate(world, bbo, ohlcv, cfg=cfg, draws=999, margins=load_margins(ROOT), factors=load_factors(ROOT))
    text = dumps(res)
    clean = json.loads(text)
    print(f"completed in {time.time() - t0:.0f}s; sections present: {[k for k in REQUIRED if k in clean]}; "
          f"missing: {[k for k in REQUIRED if k not in clean]}")
    # No per-field empty-value report: whether a statistic is defined can encode a result's sign (A16).
    # Gate-dependent counts (PG/PD/PX trades, "not_selected", PX fill reasons) are never printed: pass/fail only.
    ok = all(s.get("matched") == s.get("events") and s.get("all_fills") for s in clean["backtrader_replay"].values())
    print(f"backtrader replay: every replayed trade matches the engine within $0.01: {ok}")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    with (ROOT / "trials.jsonl").open("a") as f:
        f.write(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": "masked_dry_run",
                            "commit": commit, "sample": "IS", "draws": 999, "returns_viewed": False,
                            "results_sha256": hashlib.sha256(text.encode()).hexdigest(),
                            "note": "structure checks only; results discarded"}) + "\n")


if __name__ == "__main__":
    main()
