"""Masked plumbing run on P0 (run order step 5): no returns, no gate decisions.

Reads the in-sample settlement panels written by scripts/is_coverage.py and runs
the real calendar, contract, signal, sizing and ledger code for P0 (every valid
event). It reports only plumbing: event counts, contract counts, notional and
gross exposure against the caps, cost per event and the cost hurdle. P&L is
computed but never printed: only its SHA-256 is recorded, so later runs can show
the same numbers were produced.

Writes reports/plumbing_p0.md and appends one line to trials.jsonl.

Run:  python scripts/plumbing_run.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gqh.calendar import SessionCalendar, qualifying_sessions, trading_schedule  # noqa: E402
from gqh.config import frozen_config  # noqa: E402
from gqh.contracts import ContractPanel, reference_returns  # noqa: E402
from gqh.engine import run_row, size_events  # noqa: E402
from gqh.signals import compute_signals  # noqa: E402

DERIVED = ROOT / "data" / "derived"


def _q(s: pd.Series, fmt: str = "{:.2f}") -> str:
    s = s.dropna()
    if s.empty:
        return "-"
    return " / ".join(fmt.format(v) for v in (s.min(), s.median(), s.quantile(0.95), s.max()))


def main() -> None:
    cfg = frozen_config()
    panels = {r: pd.read_parquet(DERIVED / f"settlements_{r}.parquet") for r in ("ES", "ZN")}
    qual = qualifying_sessions(panels["ES"]["date"].unique(), panels["ZN"]["date"].unique(), cfg.is_start, cfg.is_end)
    sched = trading_schedule(SessionCalendar(qual))
    es, zn = ContractPanel.from_long(panels["ES"], "ES"), ContractPanel.from_long(panels["ZN"], "ZN")
    ref = reference_returns(es, zn, qual)
    out = ["# Masked plumbing run: P0, in-sample (no returns, no gate decisions)", ""]
    digests = {}
    for kind in ("event", "pseudo"):
        sig = compute_signals(sched, ref, es, zn, kind=kind, cfg=cfg)
        sig = sig[sig["sample"] == "IS"].reset_index(drop=True)
        sized = size_events(sig, es, zn, cfg=cfg)
        led = run_row(sig, sized, sig["valid"].to_numpy(), row="P0" if kind == "event" else "P0-pseudo", cfg=cfg)
        t = led[led["traded"]]
        digests[kind] = hashlib.sha256(np.round(led["ret"].to_numpy(), 12).tobytes()).hexdigest()
        nav = cfg.reference_nav
        cost_bp = t["cost"] / nav * 1e4
        out += [f"## {kind}s", "",
                f"- IS rows {len(sig)}; valid {int(sig['valid'].sum())}; traded {len(t)}; "
                f"not traded: {led.loc[~led['traded'], 'reason'].value_counts().to_dict()}",
                f"- Invalid because: not tradable {int((~sig['tradable']).sum())}, data incomplete "
                f"{int((~sig['data_complete']).sum())}, signal undefined (e.g. sigma warm-up) "
                f"{int((sig['tradable'] & sig['data_complete'] & ~sig['valid']).sum())}",
                "- Min / median / 95th pct / max over traded events:",
                f"  - ES contracts {_q(t['n_es'], '{:.0f}')}; ZN contracts {_q(t['n_zn'], '{:.0f}')}",
                f"  - leg notional / NAV {_q(t['notional'] / nav)}; gross / NAV {_q(t['gross_nav'])} "
                f"(caps 0.75 per leg, 1.50 gross); cap bound on {int(t['cap_bound'].sum())} events",
                f"  - round-trip cost {_q(t['cost'], '${:,.0f}')} = {_q(cost_bp, '{:.2f}')} bp of NAV",
                f"  - cost hurdle C (risk units) {_q(sized.loc[led['traded'].to_numpy(), 'hurdle'], '{:.4f}')}",
                f"- Traded events per year: {t.groupby(pd.PeriodIndex(t['month']).year).size().to_dict()}",
                f"- P&L digest (sha256 of the event-return column, values not shown): {digests[kind][:16]}", ""]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (ROOT / "reports" / "plumbing_p0.md").write_text("\n".join(out) + "\n")
    with (ROOT / "trials.jsonl").open("a") as f:
        f.write(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": "plumbing_p0",
                            "commit": commit, "sample": "IS", "rows": ["P0"], "returns_viewed": False,
                            "digests": digests}) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
