"""The six pre-registered strategy rows (HYPOTHESIS.md §4) as trade ledgers.

| Row | Decisions | Fills |
|---|---|---|
| PG (primary) | gate Ŷ > C on events | settlements |
| P0 | every valid event | settlements |
| PD | gate with c ≡ 0 (dose only) | settlements |
| PE | every valid event, sized × p (PG's IS participation rate) | settlements |
| PX | PG's decisions | 15:59 ET bid/ask |
| PP | gate Ŷ > C on pseudo-events, fitted on pseudo-events | settlements |

All rows are compared on one walk-forward segment: months from the first month in
which both the event gate (PG/PD) and the pseudo-event gate (PP) have a forecast.
Before it every row is flat (amendment A12). p is the share of P0's traded IS
segment events that PG trades, frozen for OOS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gqh.config import FrozenConfig, frozen_config
from gqh.contracts import ContractPanel
from gqh.engine import QuoteFn, run_row, size_events
from gqh.gate import DOSE_ONLY, FULL, gate_decisions


@dataclass
class StrategyRun:
    segment_start: pd.Period
    participation: float
    gates: dict[str, pd.DataFrame]
    ledgers: dict[tuple[str, float], pd.DataFrame] = field(default_factory=dict)


def _first_gated(panel: pd.DataFrame, gate: pd.DataFrame) -> pd.Period:
    gated = panel.loc[gate["gated"].to_numpy(), "month"]
    return gated.min() if len(gated) else pd.Period("2262-01", "M")


def run_strategy(events: pd.DataFrame, pseudos: pd.DataFrame, es: ContractPanel, zn: ContractPanel, *,
                 quote: QuoteFn | None = None, cfg: FrozenConfig | None = None,
                 cost_multipliers: tuple[float, ...] | None = None) -> StrategyRun:
    """Ledgers for every row and cost multiplier (PX only when ``quote`` is given)."""
    cfg = cfg or frozen_config()
    ks = cost_multipliers or cfg.cost_multipliers
    sized_ev = size_events(events, es, zn, cfg=cfg)
    sized_ps = size_events(pseudos, es, zn, cfg=cfg)
    gates = {"PG": gate_decisions(events, sized_ev["hurdle"], features=FULL, cfg=cfg),
             "PD": gate_decisions(events, sized_ev["hurdle"], features=DOSE_ONLY, cfg=cfg),
             "PP": gate_decisions(pseudos, sized_ps["hurdle"], features=FULL, cfg=cfg)}
    start = max(_first_gated(events, gates["PG"]), _first_gated(pseudos, gates["PP"]))
    in_ev = (events["month"] >= start).to_numpy()
    in_ps = (pseudos["month"] >= start).to_numpy()
    valid = events["valid"].to_numpy(dtype=bool)
    decide = {"PG": gates["PG"]["trade"].to_numpy() & in_ev, "P0": valid & in_ev,
              "PD": gates["PD"]["trade"].to_numpy() & in_ev}

    is_seg = in_ev & (events["sample"] == "IS").to_numpy()
    base_pg = run_row(events, sized_ev, decide["PG"], row="PG", cfg=cfg)
    base_p0 = run_row(events, sized_ev, decide["P0"], row="P0", cfg=cfg)
    n0 = int((base_p0["traded"].to_numpy() & is_seg).sum())
    p = float((base_pg["traded"].to_numpy() & is_seg).sum() / n0) if n0 else np.nan
    sized_pe = size_events(events, es, zn, cfg=cfg, scale=p) if np.isfinite(p) else sized_ev.assign(below_one_lot=True)

    run = StrategyRun(segment_start=start, participation=p, gates=gates)
    for k in ks:
        run.ledgers[("PG", k)] = run_row(events, sized_ev, decide["PG"], row="PG", k=k, cfg=cfg)
        run.ledgers[("P0", k)] = run_row(events, sized_ev, decide["P0"], row="P0", k=k, cfg=cfg)
        run.ledgers[("PD", k)] = run_row(events, sized_ev, decide["PD"], row="PD", k=k, cfg=cfg)
        run.ledgers[("PE", k)] = run_row(events, sized_pe, decide["P0"], row="PE", k=k, cfg=cfg)
        run.ledgers[("PP", k)] = run_row(pseudos, sized_ps, gates["PP"]["trade"].to_numpy() & in_ps, row="PP", k=k, cfg=cfg)
        if quote is not None:
            run.ledgers[("PX", k)] = run_row(events, sized_ev, decide["PG"], row="PX", k=k, cfg=cfg,
                                             executable=True, quote=quote)
    return run
