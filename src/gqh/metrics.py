"""Row metrics from trade ledgers (HYPOTHESIS.md §8 reporting; §7 prediction 7).

Every row is measured on the same contiguous monthly index (the comparison
segment): an event's net return (P&L / reference NAV) is booked in its event
month, and months without a trade return 0. NAV is fixed (no compounding), so
drawdowns are on the cumulative sum of returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from gqh.config import FrozenConfig, frozen_config


def monthly_returns(ledger: pd.DataFrame, months: pd.PeriodIndex) -> pd.Series:
    """Net return per month on ``months`` (0 where the row did not trade)."""
    r = ledger.loc[ledger["traded"]].groupby("month")["ret"].sum()
    return r.reindex(months, fill_value=0.0).astype(float).rename("ret")


def max_drawdown(r: pd.Series) -> float:
    """Largest peak-to-trough fall of the cumulative (uncompounded) return, as a positive number."""
    wealth = np.concatenate([[0.0], np.cumsum(np.asarray(r, dtype=float))])
    return float(np.max(np.maximum.accumulate(wealth) - wealth))


def turnover(ledger: pd.DataFrame, years: float, cfg: FrozenConfig | None = None) -> float:
    """Annual traded notional / NAV: both legs, entry and exit, at the sizing prices."""
    cfg = cfg or frozen_config()
    t = ledger.loc[ledger["traded"]]
    per_event = 2.0 * t["gross_nav"]
    return float(per_event.sum() / years) if years > 0 else np.nan


def row_metrics(ledger: pd.DataFrame, months: pd.PeriodIndex, cfg: FrozenConfig | None = None) -> dict:
    """Annualized return, volatility, Sharpe, max drawdown, worst month, skew, trades and turnover."""
    r = monthly_returns(ledger, months)
    x = r.to_numpy()
    years = len(x) / 12.0
    sd = x.std(ddof=1)
    traded = ledger.loc[ledger["traded"] & ledger["month"].isin(months)]
    return {
        "months": len(x), "trades": int(len(traded)), "participation": float(len(traded) / len(x)) if len(x) else np.nan,
        "ann_return": float(x.mean() * 12), "ann_vol": float(sd * np.sqrt(12)),
        "sharpe": float(x.mean() / sd * np.sqrt(12)) if sd > 0 else np.nan,
        "max_drawdown": max_drawdown(r), "worst_month": float(x.min()), "best_month": float(x.max()),
        "skew": float(sps.skew(x, bias=False)) if sd > 0 else np.nan,
        "hit_rate": float((traded["pnl"] > 0).mean()) if len(traded) else np.nan,
        "turnover": turnover(traded, years, cfg), "cost_share_of_gross": _cost_share(traded),
    }


def _cost_share(traded: pd.DataFrame) -> float:
    gross = (traded["pnl"] + traded["cost"]).abs().sum()
    return float(traded["cost"].sum() / gross) if gross > 0 else np.nan


def realized_to_target(ledger: pd.DataFrame, cfg: FrozenConfig | None = None, scale: float = 1.0) -> pd.Series:
    """Per year: RMS of gross event P&L over its ex-ante 5-day risk target (dose/2)·κ·NAV·scale (prediction 7)."""
    cfg = cfg or frozen_config()
    t = ledger.loc[ledger["traded"]]
    target = t["dose"] / 2.0 * cfg.kappa * cfg.reference_nav * scale
    u = (t["pnl"] + t["cost"]) / target
    years = pd.PeriodIndex(t["month"]).year
    return u.groupby(years).apply(lambda v: float(np.sqrt(np.mean(v**2)))).rename("realized_to_target")
