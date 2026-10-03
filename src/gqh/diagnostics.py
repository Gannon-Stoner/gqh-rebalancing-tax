"""Descriptive diagnostics (HYPOTHESIS.md §6). None of these are tests.

1. ``event_paths``: the signed, σ̂-scaled cumulative path of the 1:1 spread X from
   L-12 to F1+5, with sign and dose frozen at L-12 (drift since the previous L,
   σ̂ through L-12), summarized by era. Displacement shows as an earlier rise and a
   later fall; decay as a collapse of the whole path.
2. ``clock_panel``: the ZN 15:00 -> 16:00 ET mid return on L versus other days,
   before and after 2021-01-14, unconditional and signed by the L-5 direction s; the
   ES 15:00 -> 16:00 ET mid return as context (its settlement clock moved 2020-10-26).
3. ``legs_direction``: P&L by leg and by direction s for a ledger.
4. ``action_ledger``: per event, forecast, hurdle, decision, realized outcome, the
   forecast error times the position, gross and net P&L and leg contributions.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from gqh.calendar import SessionCalendar, n_since_prev_L
from gqh.config import FrozenConfig, frozen_config
from gqh.signals import drift, ewma_sigma

ERAS = (("2010-15", "2010-01", "2015-12"), ("2016-20", "2016-01", "2020-12"), ("2021-24", "2021-01", "2024-09"),
        ("OOS", "2024-10", "2099-12"))
CLOCK_SWITCH_ZN = pd.Timestamp("2021-01-14")


def _era(month: pd.Period) -> str:
    for name, lo, hi in ERAS:
        if pd.Period(lo, "M") <= month <= pd.Period(hi, "M"):
            return name
    return "PRE"


def event_paths(ref: pd.DataFrame, sched: pd.DataFrame, *, cfg: FrozenConfig | None = None,
                offsets: Iterable[int] = range(-12, 7)) -> pd.DataFrame:
    """One row per month: s and dose frozen at L-12 and the cumulative signed path s·ΣX/σ̂ at L+k.

    Offsets k are sessions relative to L (k = 1 is F1, k = 6 is F1+5); the path is 0
    at L-12. Uses reference within-contract returns (A8).
    """
    cfg = cfg or frozen_config()
    w = cfg.target_equity_weight
    sessions = ref.index
    cal = SessionCalendar(sessions)
    x = ref["r_es"] - ref["r_zn"]
    sig = ewma_sigma(x, cfg.ewma_lambda)
    offsets = list(offsets)
    rows = []
    for r in sched.itertuples(index=False):
        if pd.isna(r.L) or r.L not in cal:
            continue
        iL = cal.position(r.L)
        i0 = iL - 12
        if i0 < 0 or iL + max(offsets) >= len(sessions):
            continue
        d12 = sessions[i0]
        seg = lambda col: ref[col][(sessions > r.prev_L) & (sessions <= d12)]  # noqa: E731
        if seg("r_es").isna().any() or seg("r_zn").isna().any():
            continue
        R_E, R_B = np.expm1(seg("r_es").sum()), np.expm1(seg("r_zn").sum())
        D = float(drift(R_E, R_B, w))
        s_hat = float(sig.iloc[i0])
        n = n_since_prev_L(cal, d12)
        if not (np.isfinite(D) and np.isfinite(s_hat) and n > 0 and D != 0):
            continue
        z = D / (w * (1 - w) * s_hat * np.sqrt(n))
        s = -np.sign(D)
        cum = np.cumsum(x.iloc[i0 + 1: iL + max(offsets) + 1].to_numpy()) * s / s_hat
        path = {k: (0.0 if k == -12 else float(cum[k + 12 - 1])) for k in offsets}
        rows.append({"month": r.month, "era": _era(r.month), "sample": r.sample, "s": int(s),
                     "dose": float(min(abs(z), cfg.dose_cap)), **{f"k{k:+d}": v for k, v in path.items()}})
    return pd.DataFrame(rows)


def path_profile(paths: pd.DataFrame) -> pd.DataFrame:
    """Dose-weighted mean path by era (rows: era; columns: offsets), plus event counts."""
    cols = [c for c in paths.columns if c.startswith("k")]
    out = {}
    for era, g in paths.groupby("era", sort=False):
        wts = g["dose"].to_numpy()
        out[era] = {**{c: float(np.average(g[c], weights=wts)) for c in cols}, "events": len(g)}
    return pd.DataFrame(out).T


def legs_direction(ledger: pd.DataFrame) -> pd.DataFrame:
    """Traded events by direction s: count and total/mean P&L by leg (USD), gross and net."""
    t = ledger[ledger["traded"]].copy()
    t["gross"] = t["pnl"] + t["cost"]
    g = t.groupby("s")
    return pd.DataFrame({"events": g.size(), "pnl_es": g["pnl_es"].sum(), "pnl_zn": g["pnl_zn"].sum(),
                         "gross": g["gross"].sum(), "net": g["pnl"].sum(), "mean_net": g["pnl"].mean()})


def action_ledger(ledger: pd.DataFrame, gate: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    """Per event: Ŷ, hurdle, decision, realized Y, (Y − Ŷ)·traded, P&L gross/net and legs."""
    led = ledger.reset_index(drop=True)
    g = gate.reset_index(drop=True)
    sig = signals.reset_index(drop=True)
    out = pd.DataFrame({"month": led["month"], "sample": led["sample"], "yhat": g["yhat"], "hurdle": g["hurdle"],
                        "decision": g["trade"], "traded": led["traded"], "Y": sig["Y"],
                        "forecast_error_x_position": (sig["Y"] - g["yhat"]) * led["traded"].astype(float),
                        "gross": led["pnl"] + led["cost"], "net": led["pnl"], "pnl_es": led["pnl_es"],
                        "pnl_zn": led["pnl_zn"]})
    return out


def clock_panel(quotes, ref: pd.DataFrame, sched: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """ZN and ES 15:00 -> 16:00 ET mid log returns of the reference contract per session.

    Columns ``date, is_L, s`` (the event's L-5 direction on L days, else 0), ``era``
    ("pre"/"post" 2021-01-14 for ZN), ``zn``, ``es`` (NaN where a quote is missing).
    ``quotes`` is a ``gqh.quotes.QuoteBook``.
    """
    s_on_L = dict(zip(sched["L"], events["s"])) if len(events) == len(sched) else {}
    rows = []
    for d in ref.index[1:]:
        rec = {"date": d, "is_L": d in s_on_L, "s": int(s_on_L.get(d, 0)), "era": "post" if d >= CLOCK_SWITCH_ZN else "pre"}
        for leg in ("es", "zn"):
            iid = ref.at[d, f"{leg}_id"]
            mids = []
            for hh in (15, 16):
                q = quotes(int(iid), d + pd.Timedelta(hours=hh)) if pd.notna(iid) else None
                mids.append((q[0] + q[1]) / 2 if q else np.nan)
            rec[leg] = float(np.log(mids[1] / mids[0])) if all(np.isfinite(mids)) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def clock_summary(panel: pd.DataFrame) -> pd.DataFrame:
    """Mean 15:00 -> 16:00 return in bp: L vs other days, and on L signed in the predicted flow direction."""
    out = []
    for era, g in panel.groupby("era"):
        for leg in ("zn", "es"):
            L, other = g[g["is_L"]], g[~g["is_L"]]
            flow = L["s"] if leg == "es" else -L["s"]   # s = +1: rebalancers buy ES and sell ZN
            out.append({"era": era, "leg": leg, "L_mean_bp": L[leg].mean() * 1e4, "other_mean_bp": other[leg].mean() * 1e4,
                        "L_flow_signed_mean_bp": (L[leg] * flow).mean() * 1e4, "n_L": int(L[leg].notna().sum()),
                        "n_other": int(other[leg].notna().sum())})
    return pd.DataFrame(out)
