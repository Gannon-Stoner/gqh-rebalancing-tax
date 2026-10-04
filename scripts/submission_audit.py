"""Reporting-only audit of matched PG/PX events, rebuilt from local licensed settlements.

Recomputes PG metrics from its rebuilt ledger, then excludes the same
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
            "scope": "PG recomputed from a locally rebuilt ledger at 1x costs; PX read from official results. "
                     "Calendar exclusions match PX's recorded exclusions; full monthly ranges retain flat months. "
                     "Signals and sizes are rebuilt; quotes, volume and holiday capacity are not recomputed.",
            "samples": samples}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/final_audit.json")
    args = parser.parse_args()
    from webull_backtest import load_inputs, validate_inputs
    inp = load_inputs()
    validate_inputs(inp)
    ledger = inp.ledgers["PG"]
    results_path = ROOT / "results.json"
    report = audit(ledger, json.loads(results_path.read_text()))
    traded = ledger.loc[ledger["traded"]]
    leg = sorted(traded["gross_nav"] / 2)
    report["pg_size"] = {
        "es_leg_median": leg[len(leg) // 2], "es_leg_max": leg[-1],
        "crash_loss_median": 0.20 * leg[len(leg) // 2], "crash_loss_max": 0.20 * leg[-1],
        "worst_event_usd": float(traded["pnl"].min())}
    report["input_mode"] = inp.mode
    report["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (results_path, ROOT / "config/frozen.yaml", ROOT / "data/manifest.json")}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    for sample, values in report["samples"].items():
        pg, px = values["matched_PG_1x"], values["reported_PX_1x"]
        print(f"{sample}: {pg['trades']} matched events; PG Sharpe {pg['sharpe']:.2f}, PX {px['sharpe']:.2f}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
