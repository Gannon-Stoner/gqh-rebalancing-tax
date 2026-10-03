"""Size and power of the H1/H2 tests on synthetic data (amendment A4; protocol §8 test 7).

Every panel is a full in-sample history of daily ES/ZN returns from a registered
null (gqh.synth.PROTOCOL_NULLS), run through the real schedule, contract and
signal code. No market data is read.

* Size: ``base`` and ``stress_corr`` (no effect), and ``h2_reversal`` (the same
  ordinary-reversal slope c = c_pseudo = -0.10 at events and pseudo-events, so
  c_E = 0). Each must reject at 3-7% at alpha = 0.05 over >= 500 panels.
* Power: ``h1_power`` / ``h1_power_hi`` plant b = 0.05 / 0.12 at events (the middle
  and top of the predicted range); ``h2_power`` plants c = -0.27 at events only
  (c_E = -0.27, the registered MDE).
* Under ``h2_reversal`` only H2's null holds. H1's regression omits A, and A is
  correlated with dose, so its H1 rate measures how much ordinary reversal leaks
  into H1; it is reported, not held to the size band.

Effects are planted on Y of the computed signal panel (Y += b*dose + c*A), so the
planted slope is exact and does not feed back into later drifts or sigma_hat.

Writes reports/inference_calibration.md and reports/inference_calibration.json.

Run:  python scripts/calibrate_inference.py [--panels 500] [--draws 9999] [--workers 12]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gqh import stats as S  # noqa: E402
from gqh import synth  # noqa: E402
from gqh.calendar import SessionCalendar, trading_schedule, xnys_sessions  # noqa: E402
from gqh.config import frozen_config  # noqa: E402
from gqh.contracts import ContractPanel, reference_returns  # noqa: E402
from gqh.signals import compute_signals, stacked_panel  # noqa: E402
from gqh.testing import clopper_pearson  # noqa: E402

CFG = frozen_config()
SESS = xnys_sessions(CFG.is_start, CFG.is_end)
SCHED = trading_schedule(SessionCalendar(SESS))
SCENARIOS = {  # name: (leg null, planted event (b, c), planted pseudo c)
    "base": ("base", (0.0, 0.0), 0.0),
    "stress_corr": ("stress_corr", (0.0, 0.0), 0.0),
    "h2_reversal": ("base", (0.0, synth.H2_REVERSAL_NULL["c"]), synth.H2_REVERSAL_NULL["c_pseudo"]),
    "h1_power": ("base", (0.05, 0.0), 0.0),
    "h1_power_hi": ("base", (0.12, 0.0), 0.0),
    "h2_power": ("base", (0.0, -0.27), 0.0),
}


def signals(legs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    es = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_es"], root="ES", start_price=2000.0), "ES")
    zn = ContractPanel.from_long(synth.contract_panel_from_returns(legs["r_zn"], root="ZN", start_price=120.0), "ZN")
    ref = reference_returns(es, zn, SESS)
    ev = compute_signals(SCHED, ref, es, zn, kind="event", cfg=CFG)
    ps = compute_signals(SCHED, ref, es, zn, kind="pseudo", cfg=CFG)
    return ev[ev["sample"] == "IS"], ps[ps["sample"] == "IS"]


def panel(scenario: str, seed_seq: np.random.SeedSequence) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Signals from null legs, with the scenario's linear effect added to Y (no feedback into the signals)."""
    null, (b, c), c_ps = SCENARIOS[scenario]
    legs = synth.protocol_null_legs(SESS, null, seed=np.random.default_rng(seed_seq))
    ev, ps = signals(legs)
    return (ev.assign(Y=ev["Y"] + b * ev["dose"] + c * ev["A"]),
            ps.assign(Y=ps["Y"] + c_ps * ps["A"]))


def one(args: tuple[str, int, int]) -> dict:
    scenario, i, draws = args
    gen, test = np.random.SeedSequence([CFG.seed, list(SCENARIOS).index(scenario), i]).spawn(2)
    ev, ps = panel(scenario, gen)
    st = stacked_panel(ev, ps)
    seed = int(test.generate_state(1)[0])
    out = {"scenario": scenario, "panel": i, "n_events": int(ev["valid"].sum()), "n_stacked": len(st)}
    for name, fn, data in (("H1", S.h1_test, ev), ("H2", S.h2_test, st)):
        for method in ("month_block", "wild", "newey_west"):
            t = fn(data, seed=seed, draws=draws, method=method)
            out[f"{name}_{method}_p"] = t.p
            out[f"{name}_est"] = t.estimate
    return out


def summarize(rows: list[dict], panels: int, draws: int, seconds: float) -> tuple[str, dict]:
    df = pd.DataFrame(rows)
    res: dict = {"panels": panels, "draws": draws, "alpha": 0.05, "band": [0.03, 0.07], "scenarios": {}}
    lines = ["# Inference calibration (synthetic data only)", "",
             f"{panels} panels per scenario, {draws:,} bootstrap draws per test, one-sided alpha = 0.05. "
             f"Each panel is a full IS history ({SESS[0].date()} to {SESS[-1].date()}) of daily ES/ZN returns "
             f"run through the real schedule and signal code. Runtime {seconds / 60:.1f} min.", "",
             "| Scenario | Test | Month-block | Wild | Newey-West(3) | Mean estimate |", "|---|---|---|---|---|---|"]
    for sc, g in df.groupby("scenario", sort=False):
        res["scenarios"][sc] = {}
        for h in ("H1", "H2"):
            cells = []
            for method in ("month_block", "wild", "newey_west"):
                k = int((g[f"{h}_{method}_p"] <= 0.05).sum())
                lo, hi = clopper_pearson(k, len(g))
                res["scenarios"][sc][f"{h}_{method}"] = {"rate": k / len(g), "ci95": [lo, hi], "n": len(g)}
                cells.append(f"{k / len(g):.3f} [{lo:.3f}, {hi:.3f}]")
            res["scenarios"][sc][f"{h}_mean_estimate"] = float(g[f"{h}_est"].mean())
            lines.append(f"| {sc} | {h} | {' | '.join(cells)} | {g[f'{h}_est'].mean():+.4f} |")
    lines += ["", "Rates are rejection frequencies with 95% Clopper-Pearson intervals. Size rows (H1 and H2 under base "
              "and stress_corr; H2 under h2_reversal) must lie in [0.03, 0.07] for the month-block bootstrap; "
              "otherwise the registered fallback (wild) is used. H1 under h2_reversal measures leakage of ordinary "
              "reversal into H1 (its null does not hold there). Power rows are recorded, not tested."]
    return "\n".join(lines) + "\n", res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panels", type=int, default=500)
    ap.add_argument("--draws", type=int, default=9999)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--scenarios", nargs="*", default=list(SCENARIOS))
    a = ap.parse_args()
    jobs = [(sc, i, a.draws) for sc in a.scenarios for i in range(a.panels)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        rows = []
        for n, r in enumerate(pool.map(one, jobs, chunksize=4), 1):
            rows.append(r)
            if n % 100 == 0:
                print(f"{n}/{len(jobs)} panels, {time.time() - t0:.0f}s", flush=True)
    md, res = summarize(rows, a.panels, a.draws, time.time() - t0)
    (ROOT / "reports" / "inference_calibration.md").write_text(md)
    (ROOT / "reports" / "inference_calibration.json").write_text(json.dumps(res, indent=2))
    print(md)


if __name__ == "__main__":
    main()
