"""Risk Management and Liquidity & Capital numbers (FINAL_STRATEGY §9-§10; HYPOTHESIS.md §8).

All inputs are ledgers and daily P&L from ``gqh.engine``; nothing here changes a
decision. Margin figures are inputs (dated, cited in the note), not estimates.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gqh.config import FrozenConfig, frozen_config
from gqh.metrics import max_drawdown

STRESS_MONTHS = ("2011-08", "2015-08", "2018-02", "2020-03", "2022", "2023-03")


def stress_table(ledger: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Event P&L by leg (as % of NAV) for each registered stress period; '2022' is the whole year."""
    t = ledger[ledger["traded"]].copy()
    rows = []
    for tag in STRESS_MONTHS:
        sel = (pd.PeriodIndex(t["month"]).year == int(tag)) if len(tag) == 4 else (t["month"] == pd.Period(tag, "M"))
        g = t[np.asarray(sel)]
        rows.append({"period": tag, "events": int(len(g)), "es_pct": g["pnl_es"].sum() / nav * 100,
                     "zn_pct": g["pnl_zn"].sum() / nav * 100, "cost_pct": g["cost"].sum() / nav * 100,
                     "net_pct": g["pnl"].sum() / nav * 100,
                     "worst_event_pct": (g["pnl"].min() / nav * 100) if len(g) else np.nan})
    return pd.DataFrame(rows)


def factor_regression(event_ret: pd.Series, windows: pd.DataFrame, factors: pd.DataFrame) -> dict:
    """OLS of event net returns on factor returns summed over each holding window (entry, exit].

    ``windows`` has ``month, entry, exit`` per event (index aligned with ``event_ret``);
    ``factors`` is daily, indexed by date, in decimal returns (e.g. Mkt-RF, SMB, HML, Mom, ZN).
    Returns alpha per event, loadings, t-stats (HC1) and R².
    """
    import statsmodels.api as sm

    X = []
    for _, w in windows.iterrows():
        seg = factors[(factors.index > w["entry"]) & (factors.index <= w["exit"])]
        X.append(seg.sum())
    X = pd.DataFrame(X, index=event_ret.index)
    ok = X.notna().all(axis=1) & event_ret.notna()
    fit = sm.OLS(event_ret[ok].to_numpy(), sm.add_constant(X[ok].to_numpy())).fit(cov_type="HC1")
    names = ["alpha", *X.columns]
    return {"n": int(ok.sum()), "r2": float(fit.rsquared),
            "coef": dict(zip(names, map(float, fit.params))), "t": dict(zip(names, map(float, fit.tvalues)))}


def margin_ledger(ledger: pd.DataFrame, daily_net: pd.Series, margins: dict[str, float], nav: float) -> dict:
    """Margin-to-equity of the positions and the worst one-day variation-margin draw.

    ``margins`` gives USD initial margin per contract per leg; ``daily_net`` is the
    engine's daily net P&L (USD) of the same ledger.
    """
    t = ledger[ledger["traded"]]
    req = t["n_es"] * margins["ES"] + t["n_zn"] * margins["ZN"]
    return {"margin_to_equity_median": float(req.median() / nav) if len(t) else np.nan,
            "margin_to_equity_max": float(req.max() / nav) if len(t) else np.nan,
            "worst_daily_vm_pct": float(daily_net.min() / nav * 100) if len(daily_net) else np.nan}


def drawdown_probability(monthly: pd.Series, *, threshold: float = 0.075, horizon_months: int = 36,
                         draws: int = 9999, block: int = 3, seed: int = 0) -> float:
    """P(max drawdown >= threshold within ``horizon_months``), circular month-block bootstrap of monthly returns."""
    from gqh.stats import block_month_counts  # noqa: F401  (same resampling unit as the inference)

    x = monthly.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(horizon_months / block))
    starts = rng.integers(0, len(x), size=(draws, n_blocks))
    idx = ((starts[..., None] + np.arange(block)).reshape(draws, -1)[:, :horizon_months]) % len(x)
    paths = np.concatenate([np.zeros((draws, 1)), np.cumsum(x[idx], axis=1)], axis=1)
    dd = np.max(np.maximum.accumulate(paths, axis=1) - paths, axis=1)
    return float(np.mean(dd >= threshold))


def months_to_t2(monthly: pd.Series) -> float:
    """Months of data needed for t = 2 at the observed monthly Sharpe: (2 / SR_monthly)²."""
    x = monthly.to_numpy(dtype=float)
    sr = x.mean() / x.std(ddof=1)
    return float((2.0 / sr) ** 2) if sr > 0 else np.inf


def stop_loss_stress(ledger: pd.DataFrame, daily: pd.DataFrame, cfg: FrozenConfig | None = None,
                     k_sigma: float = 2.0) -> dict:
    """Exit an event once its running gross loss exceeds k·(ex-ante 5-day risk); a stress row only (not traded).

    Returns total net P&L (USD) with and without the stop and the number of stopped events.
    ``daily`` must be ``engine.daily_pnl`` output for each traded event, given here as a
    dict-like per-event frame: columns ``month, date, gross`` (one row per event-session).
    """
    cfg = cfg or frozen_config()
    t = ledger[ledger["traded"]].set_index("month")
    stopped, total_stop = 0, 0.0
    for m, g in daily.groupby("month"):
        if m not in t.index:
            continue
        row = t.loc[m]
        limit = k_sigma * row["dose"] / 2.0 * cfg.kappa * cfg.reference_nav
        cum = g.sort_values("date")["gross"].cumsum().to_numpy()
        hit = np.flatnonzero(cum <= -limit)
        gross = cum[hit[0]] if len(hit) else cum[-1]
        stopped += int(len(hit) > 0)
        total_stop += gross - row["cost"]
    return {"stopped_events": stopped, "net_with_stop": total_stop, "net_without_stop": float(t["pnl"].sum())}


def impact_cost(n: float, price: float, multiplier: float, sigma_d: float, volume: float, y: float = 1.0) -> float:
    """Square-root impact per contract (USD): y·σ_d·√(Q/V)·price·multiplier."""
    if not (volume > 0 and np.isfinite(sigma_d)):
        return np.inf
    return float(y * sigma_d * np.sqrt(abs(n) / volume) * price * multiplier)


def sharpe_vs_nav(ledger: pd.DataFrame, months: pd.PeriodIndex, sigma_d: pd.DataFrame, volume: pd.DataFrame,
                  navs=(1e6, 1e7, 1e8, 3e8, 1e9), cfg: FrozenConfig | None = None) -> pd.DataFrame:
    """Net annualized Sharpe when positions scale with NAV and each fill pays square-root impact (Y = 1).

    ``sigma_d`` and ``volume`` hold, per traded event (same index as ``ledger``), the
    columns ``ES`` and ``ZN``: daily return vol and daily traded volume of the held
    contract on the fill day. Integer rounding is ignored here (scenario, not backtest).
    """
    cfg = cfg or frozen_config()
    ref_nav = cfg.reference_nav
    t = ledger[ledger["traded"]]
    out = []
    for nav in navs:
        scale = nav / ref_nav
        ret = pd.Series(0.0, index=months)
        for i, r in t.iterrows():
            if r["month"] not in ret.index:
                continue
            gross = (r["pnl"] + r["cost"]) * scale
            base_cost = r["cost"] * scale
            imp = 0.0
            for leg, n_col, px in (("ES", "n_es", r["es_in"]), ("ZN", "n_zn", r["zn_in"])):
                n = r[n_col] * scale
                imp += 2 * n * impact_cost(n, px, cfg.multipliers[leg], sigma_d.at[i, leg], volume.at[i, leg])
            ret[r["month"]] += (gross - base_cost - imp) / nav
        x = ret.to_numpy()
        out.append({"nav": nav, "sharpe": float(x.mean() / x.std(ddof=1) * np.sqrt(12)) if x.std(ddof=1) > 0 else np.nan,
                    "ann_return": float(x.mean() * 12)})
    return pd.DataFrame(out)
