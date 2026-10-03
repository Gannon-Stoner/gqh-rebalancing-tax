"""Signals for month-end events and pseudo-events (HYPOTHESIS.md section 3).

All returns are daily log returns; the 1:1 spread return is X = r_ES - r_ZN.

Per schedule row (``trading_schedule``), with decision date ``dec``:

* Drift: R_E, R_B are simple cumulative returns of the *reference* legs
  (``contracts.reference_returns``) over sessions (prev_L, dec]; then
  ``D = w(1-w)(R_E - R_B) / (1 + w R_E + (1-w) R_B)`` with w = 0.6.
* sigma_hat: zero-mean EWMA(lambda) standard deviation of the daily reference X,
  using data through ``dec`` inclusive (:func:`ewma_sigma`).
* ``z = D / (w(1-w) * sigma_hat * sqrt(n))``, n = sessions in (prev_L, dec];
  ``dose = min(|z|, 2)``; ``s = -sign(D)`` (+1 = long ES / short ZN).
* Progress and outcome use the *event contracts* (``contracts.event_contracts``):
  ``A = s * X(progress start -> dec) / (sigma_hat sqrt(3))`` and
  ``Y = s * X(entry -> exit) / (sigma_hat sqrt(5))``.

Events: dec = L-5, progress L-8 -> L-5, entry L-4, exit F1.
Pseudo-events: dec = L-14, progress L-17 -> L-14, entry L-13, exit
``pseudo_exit`` (L-8); every pseudo input uses data through L-14 only
(amendment A5).

Nothing is filled: a missing return inside a drift window, an unseasoned
sigma_hat, D = 0, untradable or incomplete contracts, or an invalid schedule
row make the row invalid (``valid = False``) rather than imputed.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from gqh.config import FrozenConfig, frozen_config
from gqh.contracts import ContractPanel, event_contracts

EWMA_SEED_OBS = 21
EWMA_MIN_OBS = 63

_WINDOWS = {
    # kind: (decision, progress start, entry, exit, n column, schedule-valid column)
    "event": ("L_m5", "L_m8", "L_m4", "F1", "n_since_prev_L", "event_valid"),
    "pseudo": ("L_m14", "L_m17", "L_m13", "pseudo_exit", "n_since_prev_L_pseudo", "pseudo_valid"),
}


def drift(R_E: Any, R_B: Any, w: float = 0.6) -> Any:
    """Equity overweight of a w/(1-w) portfolio after returns R_E, R_B (simple)."""
    return w * (1 - w) * (np.asarray(R_E) - np.asarray(R_B)) / (1 + w * np.asarray(R_E) + (1 - w) * np.asarray(R_B))


def required_equity_trade(V0: float, R_E: float, R_B: float, w: float = 0.6) -> float:
    """Dollar equity purchase (+ = buy) that restores weight w; equals w(1-w)V0(R_B - R_E)."""
    return w * (1 - w) * V0 * (R_B - R_E)


def ewma_sigma(x: pd.Series, lam: float, *, seed_obs: int = EWMA_SEED_OBS,
               min_obs: int = EWMA_MIN_OBS) -> pd.Series:
    """Zero-mean EWMA standard deviation of ``x``, using data through each date.

    var_t = lam * var_{t-1} + (1 - lam) * x_t**2. The recursion starts at the
    ``seed_obs``-th valid observation with var = mean of the first ``seed_obs``
    squares; values are NaN until ``min_obs`` valid observations have been seen.
    A NaN observation leaves the variance unchanged (no update, no fill).
    """
    vals = x.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    var, seen, seed_sq = np.nan, 0, []
    for i, v in enumerate(vals):
        if np.isfinite(v):
            seen += 1
            if seen <= seed_obs:
                seed_sq.append(v * v)
                if seen == seed_obs:
                    var = float(np.mean(seed_sq))
            else:
                var = lam * var + (1 - lam) * v * v
        if seen >= min_obs and np.isfinite(var):
            out[i] = np.sqrt(var)
    return pd.Series(out, index=x.index, name="sigma_hat")


def _window_sum(r: pd.Series, start_excl: Any, end_incl: Any) -> float:
    """Sum of ``r`` over sessions in (start_excl, end_incl]; NaN if any is missing."""
    seg = r[(r.index > start_excl) & (r.index <= end_incl)]
    if len(seg) == 0 or seg.isna().any():
        return np.nan
    return float(seg.sum())


def _spread(es: ContractPanel, zn: ContractPanel, es_id: Any, zn_id: Any, start: Any, end: Any) -> float:
    if pd.isna(es_id) or pd.isna(zn_id):
        return np.nan
    return es.log_return(int(es_id), start, end) - zn.log_return(int(zn_id), start, end)


def compute_signals(sched: pd.DataFrame, ref: pd.DataFrame, es: ContractPanel, zn: ContractPanel,
                    *, kind: str = "event", cfg: FrozenConfig | None = None) -> pd.DataFrame:
    """One row per schedule month with drift, dose, direction, progress A and outcome Y.

    ``ref`` is ``contracts.reference_returns`` output indexed by session. Columns:
    ``month, kind, sample, dec, progress_start, entry, exit, n, R_E, R_B, D, sigma,
    z, dose, s, X_progress, X_hold, A, Y, es_id, zn_id, es_entry, es_exit,
    zn_entry, zn_exit, tradable, data_complete, QE, px_eligible, valid``
    (``es_entry`` etc. are settlements of the held contracts at entry and exit).
    """
    if kind not in _WINDOWS:
        raise ValueError("kind must be 'event' or 'pseudo'")
    cfg = cfg or frozen_config()
    w = cfg.target_equity_weight
    dec_c, prog_c, entry_c, exit_c, n_c, valid_c = _WINDOWS[kind]
    sessions = ref.index
    x = ref["r_es"] - ref["r_zn"]
    sigma_all = ewma_sigma(x, cfg.ewma_lambda)
    contracts = event_contracts(sched, es, zn, sessions, kind=kind).set_index("month")

    rows = []
    for r in sched.itertuples(index=False):
        dec, prog, entry, exit_ = (getattr(r, c) for c in (dec_c, prog_c, entry_c, exit_c))
        n = int(getattr(r, n_c))
        c = contracts.loc[r.month]
        row: dict[str, Any] = {"month": r.month, "kind": kind, "sample": r.sample, "dec": dec,
                               "progress_start": prog, "entry": entry, "exit": exit_, "n": n,
                               "es_id": c["es_id"], "zn_id": c["zn_id"],
                               "tradable": bool(c["tradable"]), "data_complete": bool(c["data_complete"]),
                               "QE": bool(r.is_quarter_end), "px_eligible": bool(getattr(r, "px_eligible", True))}
        R_E = np.expm1(_window_sum(ref["r_es"], r.prev_L, dec)) if pd.notna(dec) else np.nan
        R_B = np.expm1(_window_sum(ref["r_zn"], r.prev_L, dec)) if pd.notna(dec) else np.nan
        D = float(drift(R_E, R_B, w)) if np.isfinite(R_E) and np.isfinite(R_B) else np.nan
        sigma = float(sigma_all.get(dec, np.nan)) if pd.notna(dec) else np.nan
        z = D / (w * (1 - w) * sigma * np.sqrt(n)) if np.isfinite(D) and np.isfinite(sigma) and n > 0 else np.nan
        s = int(-np.sign(D)) if np.isfinite(D) else 0
        x_prog = _spread(es, zn, c["es_id"], c["zn_id"], prog, dec)
        x_hold = _spread(es, zn, c["es_id"], c["zn_id"], entry, exit_)
        scale_a = sigma * np.sqrt(cfg.progress_scale_sessions)
        scale_y = sigma * np.sqrt(cfg.outcome_scale_sessions)
        row.update(R_E=R_E, R_B=R_B, D=D, sigma=sigma, z=z,
                   dose=min(abs(z), cfg.dose_cap) if np.isfinite(z) else np.nan, s=s,
                   X_progress=x_prog, X_hold=x_hold,
                   A=s * x_prog / scale_a if np.isfinite(x_prog) and np.isfinite(scale_a) else np.nan,
                   Y=s * x_hold / scale_y if np.isfinite(x_hold) and np.isfinite(scale_y) else np.nan)
        for leg, panel, iid in (("es", es, c["es_id"]), ("zn", zn, c["zn_id"])):
            ok = pd.notna(iid)
            row[f"{leg}_entry"] = panel.price(int(iid), entry) if ok and pd.notna(entry) else np.nan
            row[f"{leg}_exit"] = panel.price(int(iid), exit_) if ok and pd.notna(exit_) else np.nan
        row["valid"] = bool(
            getattr(r, valid_c) and row["tradable"] and row["data_complete"] and s != 0
            and all(np.isfinite(row[k]) for k in ("D", "sigma", "z", "A", "Y"))
        )
        rows.append(row)
    df = pd.DataFrame(rows)
    for col in ("es_id", "zn_id"):
        df[col] = df[col].astype("Int64")
    return df


def stacked_panel(events: pd.DataFrame, pseudos: pd.DataFrame) -> pd.DataFrame:
    """Valid events (ME=1) and pseudo-events (ME=0) for the H2 regression."""
    cols = ["month", "sample", "QE", "dose", "A", "Y"]
    ev = events.loc[events["valid"], cols].assign(ME=1)
    ps = pseudos.loc[pseudos["valid"], cols].assign(ME=0)
    out = pd.concat([ev, ps], ignore_index=True)
    return out.sort_values(["month", "ME"], ignore_index=True)
