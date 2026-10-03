"""The remaining-return gate and the decisions of every strategy row.

Frozen rule (HYPOTHESIS.md §3 "Gate", frozen.yaml ``gate``): forecast
Ŷ = â + b̂·dose + ĉ·A from OLS on completed past events only, an expanding window
with at least 60 events, coefficients frozen at the end of IS for OOS. Trade iff
Ŷ > C (the cost hurdle, ``gqh.engine.size_events``); otherwise flat; never reverse.

* "Completed past events": valid rows whose exit session is strictly before the
  current row's decision session. After ``is_end`` only rows that exited by
  ``is_end`` are used, so OOS forecasts use the coefficients frozen at the end of IS.
* PD fits the restricted model Y = a + b·dose (c ≡ 0) the same way.
* PP runs the same procedure on pseudo-events, with pseudo-events as training data.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from gqh.config import FrozenConfig, frozen_config

FULL = ("dose", "A")
DOSE_ONLY = ("dose",)


def ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """OLS coefficients of y on [1, X] (intercept first)."""
    Z = np.column_stack([np.ones(len(y)), X])
    coef, *_ = np.linalg.lstsq(Z, y, rcond=None)
    return coef


def walk_forward(panel: pd.DataFrame, *, features: Sequence[str] = FULL, min_events: int | None = None,
                 freeze_at: pd.Timestamp | None = None, cfg: FrozenConfig | None = None) -> pd.DataFrame:
    """Expanding-window forecasts for every row of ``panel`` (``signals.compute_signals`` output).

    Columns (same index): ``n_train``, ``coef_<name>`` for the intercept and each
    feature, and ``yhat`` (NaN when fewer than ``min_events`` completed rows exist
    or the row itself lacks a feature).
    """
    cfg = cfg or frozen_config()
    min_events = cfg.min_events if min_events is None else min_events
    freeze_at = cfg.is_end if freeze_at is None else pd.Timestamp(freeze_at)
    feats = list(features)
    usable = panel["valid"].to_numpy(dtype=bool) & np.isfinite(panel["Y"].to_numpy(dtype=float))
    exits = pd.to_datetime(panel["exit"]).to_numpy()
    X_all = panel[feats].to_numpy(dtype=float)
    y_all = panel["Y"].to_numpy(dtype=float)
    names = ["coef_const", *[f"coef_{f}" for f in feats]]
    rows = []
    for i, dec in enumerate(pd.to_datetime(panel["dec"]).to_numpy()):
        out = {"n_train": 0, **{n: np.nan for n in names}, "yhat": np.nan}
        if not np.isnat(dec):
            done = usable & (exits < dec)
            if dec > np.datetime64(freeze_at):
                done &= exits <= np.datetime64(freeze_at)
            out["n_train"] = int(done.sum())
            if out["n_train"] >= min_events:
                coef = ols(X_all[done], y_all[done])
                out.update(dict(zip(names, coef)))
                x = X_all[i]
                if np.all(np.isfinite(x)):
                    out["yhat"] = float(coef[0] + x @ coef[1:])
        rows.append(out)
    return pd.DataFrame(rows, index=panel.index)


def gate_decisions(panel: pd.DataFrame, hurdle: pd.Series | np.ndarray, *, features: Sequence[str] = FULL,
                   cfg: FrozenConfig | None = None, **kw) -> pd.DataFrame:
    """Walk-forward forecasts plus ``hurdle`` and ``trade`` (valid, forecast exists and Ŷ > C)."""
    wf = walk_forward(panel, features=features, cfg=cfg, **kw)
    wf["hurdle"] = np.asarray(hurdle, dtype=float)
    wf["gated"] = wf["yhat"].notna()
    wf["trade"] = panel["valid"].to_numpy(dtype=bool) & wf["gated"] & (wf["yhat"] > wf["hurdle"]).fillna(False)
    return wf
