"""Reporting-only audit of matched PG/PX events, requiring no licensed raw data.

Recomputes PG metrics from its committed ledger, then excludes the same
early-close events that PX cannot trade. Official results and decisions stay
unchanged. PX metrics are read from results.json, not independently recomputed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gqh.calendar import is_early_close
from gqh.config import frozen_config
from gqh.metrics import row_metrics

METRICS = ("trades", "ann_return", "ann_vol", "sharpe", "max_drawdown", "worst_month", "turnover")


def audit(ledger: pd.DataFrame, results: dict) -> dict:
    cfg = frozen_config()
    ledger = ledger.copy()
    ledger["month"] = pd.PeriodIndex(ledger["month"], freq="M")
    for col in ("entry", "exit"):
        ledger[col] = pd.to_datetime(ledger[col])
    ledger["ret"] = ledger["pnl"] / cfg.reference_nav
    entry_early = ledger["entry"].map(is_early_close)
    exit_early = ledger["exit"].map(is_early_close)
    excluded = ledger["traded"] & (entry_early | exit_early)
    matched = ledger.copy()
    matched.loc[excluded, "traded"] = False
    samples = {}
    for sample in ("IS", "OOS"):
        section = results[f"rows_{sample}"]
        months = pd.period_range(*section["months"], freq="M")
        full = row_metrics(ledger, months, cfg)
        for metric in METRICS:
            expected = section["rows"]["PG@1x"][metric]
            if not np.isclose(full[metric], expected, rtol=1e-8, atol=1e-12):
                raise ValueError(f"PG {sample} {metric} differs from the official result")
        px_info = section["px_fills"]
        unsupported = set(px_info["reasons"]) - {"", "not_selected", "px_ineligible"}
        if unsupported or px_info["exit_fallbacks"]:
            raise ValueError(f"PX {sample} exclusions need more than an early-close filter")
        metrics = row_metrics(matched, months, cfg)
        if metrics["trades"] != section["rows"]["PX@1x"]["trades"]:
            raise ValueError(f"PG/PX {sample} counts do not match after the calendar filter")
        events = []
        for i, event in ledger.loc[excluded & ledger["month"].isin(months)].iterrows():
            events.append({"month": str(event["month"]), "entry": event["entry"].strftime("%Y-%m-%d"),
                           "exit": event["exit"].strftime("%Y-%m-%d"),
                           "entry_early_close": bool(entry_early.loc[i]), "exit_early_close": bool(exit_early.loc[i])})
        if len(events) != px_info["reasons"].get("px_ineligible", 0):
            raise ValueError(f"PX {sample} calendar exclusion count differs from official results")
        samples[sample] = {
            "months": section["months"],
            "reported_PG_1x": {key: full[key] for key in METRICS},
            "matched_PG_1x": {key: metrics[key] for key in METRICS},
            "reported_PX_1x": {key: section["rows"]["PX@1x"][key] for key in METRICS},
            "excluded_early_close_events": events,
            "archived_PG_capacity_one_lot_pass_share": section["capacity"]["PG_settle_windows"]["lot_at_1pct_share"],
        }
    return {"status": "post-result reporting audit; no strategy or official-result changes",
            "scope": "PG recomputed from committed ledger at 1x costs; PX read from official results. "
                     "Calendar exclusions match PX's recorded exclusions; full monthly ranges retain flat months. "
                     "This does not recompute quotes, signals, volume or holiday capacity.",
            "samples": samples}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/final_audit.json")
    args = parser.parse_args()
    ledger_path, results_path = ROOT / "data/replay/ledger_PG.csv", ROOT / "results.json"
    report = audit(pd.read_csv(ledger_path), json.loads(results_path.read_text()))
    report["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (ledger_path, results_path, ROOT / "config/frozen.yaml")}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    for sample, values in report["samples"].items():
        pg, px = values["matched_PG_1x"], values["reported_PX_1x"]
        print(f"{sample}: {pg['trades']} matched events; PG Sharpe {pg['sharpe']:.2f}, PX {px['sharpe']:.2f}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
