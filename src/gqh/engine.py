"""Contract-level positions, P&L, costs, executable fills and the trade ledger.

Frozen rules (HYPOTHESIS.md §3 "Position (P1)" and "Costs", frozen.yaml ``sizing``,
``contracts``, ``costs``):

* Leg notional N = (dose/2)·κ·NAV/(σ̂·√5), times the row's ``scale`` (PE), capped
  at 0.75·NAV per leg. Legs are 1:1 in notional, so gross <= 1.5·NAV.
* Direction s = +1 is long ES / short ZN; s = -1 is short ES / long ZN.
* Integer contracts per leg. Settlement rows enter at the entry settle and exit at
  the exit settle; each contract pays (half-spread + fee) per side, times the cost
  multiplier k (1x and 2x are reported).

Implementation details (AMENDMENTS.md A11):

* Contracts = round-half-up(N / (price·multiplier)), with price = the held
  contract's settle on the decision session, the last price known when the
  decision is taken. A leg that would exceed the cap is floored to it.
* If either leg rounds to zero contracts, the event is not traded
  ("below_one_lot"): one leg alone is not the 1:1 spread.
* "Ideal" P&L uses the unrounded contract counts on the same prices, so integer
  minus ideal is the rounding error the protocol asks to report.
* PX fills at the 15:59 ET bbo-1m quote (A9): buy at the ask, sell at the bid.
  The real half-spread is paid in the fill, so PX charges k·fee + (k-1)·half-spread
  per contract per side. No entry quote on either leg: not traded
  ("no_entry_quote"). No exit quote: that leg exits at the exit settle and pays the
  settlement-row cost (flagged ``px_exit_fallback``).
* Gate decisions are taken at 1x cost; the 2x rows re-cost the same trades.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from gqh.config import FrozenConfig, frozen_config
from gqh.contracts import ContractPanel

LEGS = ("ES", "ZN")
PER_LEG_CAP_NAV = 0.75
GROSS_CAP_NAV = 1.50
FILL_MINUTE = pd.Timedelta(hours=15, minutes=59)

QuoteFn = Callable[[int, pd.Timestamp], "tuple[float, float] | None"]
"""(instrument_id, ET timestamp) -> (bid, ask) of the fresh quote at that time, or None."""


def leg_notional(dose: float, sigma: float, *, cfg: FrozenConfig | None = None, scale: float = 1.0) -> float:
    """Target USD notional per leg: (dose/2)·κ·NAV/(σ̂·√5)·scale, capped at 0.75·NAV."""
    cfg = cfg or frozen_config()
    if not (np.isfinite(dose) and np.isfinite(sigma) and sigma > 0):
        return np.nan
    nav = cfg.reference_nav
    n = (dose / 2.0) * cfg.kappa * nav / (sigma * np.sqrt(cfg.outcome_scale_sessions)) * scale
    return float(min(n, PER_LEG_CAP_NAV * nav))


def contracts_for(notional: float, price: float, multiplier: float, *, cap_usd: float | None = None) -> tuple[int, float]:
    """(integer contracts, unrounded contracts) for a USD notional; rounds half up, never above the cap."""
    if not (np.isfinite(notional) and np.isfinite(price) and price > 0):
        return 0, np.nan
    exact = notional / (price * multiplier)
    n = int(np.floor(exact + 0.5))
    if cap_usd is not None:
        n = min(n, int(np.floor(cap_usd / (price * multiplier) + 1e-12)))
    return n, float(exact)


def side_cost(leg: str, *, k: float = 1.0, executable: bool = False, cfg: FrozenConfig | None = None) -> float:
    """USD per contract per side: k·(half-spread + fee); executable fills pay k·fee + (k-1)·half-spread."""
    cfg = cfg or frozen_config()
    hs, fee = cfg.half_spreads[leg], cfg.fee
    return k * fee + (k - 1.0) * hs if executable else k * (hs + fee)


def round_trip_cost(n_es: float, n_zn: float, *, k: float = 1.0, cfg: FrozenConfig | None = None) -> float:
    """USD cost of entering and exiting n_es ES and n_zn ZN contracts at settlement-row costs."""
    cfg = cfg or frozen_config()
    return 2.0 * (abs(n_es) * side_cost("ES", k=k, cfg=cfg) + abs(n_zn) * side_cost("ZN", k=k, cfg=cfg))


def cost_hurdle(cost_usd: float, notional: float, sigma: float, *, outcome_sessions: int = 5) -> float:
    """Gate hurdle C: round-trip cost in units of position risk, cost / (N·σ̂·√5)."""
    risk = notional * sigma * np.sqrt(outcome_sessions)
    return float(cost_usd / risk) if np.isfinite(risk) and risk > 0 else np.nan


def early_execution_savings_bp(q: float, p_early: float, p_late: float) -> float:
    """sign(q)·(p_late/p_early − 1)·1e4: a buy at 100 when the later price is 101 saves +100bp."""
    return float(np.sign(q) * (p_late / p_early - 1.0) * 1e4)


def size_events(signals: pd.DataFrame, es: ContractPanel, zn: ContractPanel, *,
                cfg: FrozenConfig | None = None, scale: float = 1.0) -> pd.DataFrame:
    """Ex-ante sizing of every row of ``signals`` (``signals.compute_signals`` output).

    Uses only information at the decision session ``dec``: dose, σ̂ and the held
    contracts' settles there. Columns (same index as ``signals``):
    ``notional`` (target USD per leg, after the cap), ``cap_bound``, ``es_size_px``,
    ``zn_size_px``, ``n_es``, ``n_zn`` (unsigned integer contracts), ``n_es_exact``,
    ``n_zn_exact``, ``below_one_lot``, ``cost_1x`` (USD round trip at settlement-row
    costs) and ``hurdle`` (the gate's C in position-risk units).
    """
    cfg = cfg or frozen_config()
    cap = PER_LEG_CAP_NAV * cfg.reference_nav
    rows = []
    for r in signals.itertuples(index=False):
        out: dict[str, Any] = {"notional": np.nan, "cap_bound": False, "es_size_px": np.nan, "zn_size_px": np.nan,
                               "n_es": 0, "n_zn": 0, "n_es_exact": np.nan, "n_zn_exact": np.nan,
                               "below_one_lot": True, "cost_1x": np.nan, "hurdle": np.nan}
        ids_ok = pd.notna(r.es_id) and pd.notna(r.zn_id) and pd.notna(r.dec)
        uncapped = (r.dose / 2.0) * cfg.kappa * cfg.reference_nav / (r.sigma * np.sqrt(cfg.outcome_scale_sessions)) * scale \
            if np.isfinite(r.dose) and np.isfinite(r.sigma) and r.sigma > 0 else np.nan
        if ids_ok and np.isfinite(uncapped):
            n_usd = leg_notional(r.dose, r.sigma, cfg=cfg, scale=scale)
            px = {"ES": es.price(int(r.es_id), r.dec), "ZN": zn.price(int(r.zn_id), r.dec)}
            n_es, x_es = contracts_for(n_usd, px["ES"], cfg.multipliers["ES"], cap_usd=cap)
            n_zn, x_zn = contracts_for(n_usd, px["ZN"], cfg.multipliers["ZN"], cap_usd=cap)
            out.update(notional=n_usd, es_size_px=px["ES"], zn_size_px=px["ZN"], n_es=n_es, n_zn=n_zn,
                       n_es_exact=x_es, n_zn_exact=x_zn,
                       cap_bound=bool(uncapped > cap or np.floor(x_es + 0.5) > n_es or np.floor(x_zn + 0.5) > n_zn),
                       below_one_lot=bool(n_es == 0 or n_zn == 0))
            if not out["below_one_lot"]:
                out["cost_1x"] = round_trip_cost(n_es, n_zn, k=1.0, cfg=cfg)
                out["hurdle"] = cost_hurdle(out["cost_1x"], n_usd, r.sigma, outcome_sessions=cfg.outcome_scale_sessions)
        rows.append(out)
    df = pd.DataFrame(rows, index=signals.index)
    for c in ("n_es", "n_zn"):
        df[c] = df[c].astype("int64")
    return df


def _fill(quote: QuoteFn, iid: int, day: pd.Timestamp, q: float, opening: bool) -> float:
    """Executable price for a signed quantity: buys pay the ask, sells receive the bid (NaN if no quote)."""
    qt = quote(iid, day + FILL_MINUTE)
    if qt is None:
        return np.nan
    bid, ask = qt
    buy = (q > 0) == opening          # opening a long or closing a short is a buy
    return float(ask if buy else bid)


def _reason(r, z, trade: bool, executable: bool, quote: QuoteFn | None) -> str:
    if not r.valid:
        return "invalid"
    if not trade:
        return "not_selected"
    if z.below_one_lot:
        return "below_one_lot"
    if executable:
        if not r.px_eligible:
            return "px_ineligible"
        q_es, q_zn = r.s * z.n_es, -r.s * z.n_zn
        if not (np.isfinite(_fill(quote, int(r.es_id), r.entry, q_es, True))
                and np.isfinite(_fill(quote, int(r.zn_id), r.entry, q_zn, True))):
            return "no_entry_quote"
    return ""


def run_row(signals: pd.DataFrame, sized: pd.DataFrame, trade: Any, *, row: str, k: float = 1.0,
            cfg: FrozenConfig | None = None, executable: bool = False, quote: QuoteFn | None = None) -> pd.DataFrame:
    """Trade ledger of one strategy row: one line per ``signals`` row.

    ``trade`` is the row's decision per event (bool, aligned with ``signals``);
    ``sized`` is :func:`size_events` output. Settlement rows fill at the entry and
    exit settles; ``executable=True`` fills at the 15:59 ET quote from ``quote``.
    P&L columns are USD; ``ret`` is net P&L over the reference NAV.
    """
    cfg = cfg or frozen_config()
    if executable and quote is None:
        raise ValueError("executable fills need a quote function")
    nav, mult = cfg.reference_nav, cfg.multipliers
    trade = np.asarray(trade, dtype=bool)
    out = []
    for i, (r, z) in enumerate(zip(signals.itertuples(index=False), sized.itertuples(index=False))):
        reason = _reason(r, z, bool(trade[i]), executable, quote)
        line: dict[str, Any] = {"row": row, "month": r.month, "kind": r.kind, "sample": r.sample, "dec": r.dec,
                                "entry": r.entry, "exit": r.exit, "s": r.s, "dose": r.dose, "sigma": r.sigma,
                                "traded": reason == "", "reason": reason, "k": k, "cap_bound": bool(z.cap_bound),
                                "px_exit_fallback": False}
        zero = dict(n_es=0, n_zn=0, q_es=0, q_zn=0, notional=0.0, gross_nav=0.0, es_in=np.nan, es_out=np.nan,
                    zn_in=np.nan, zn_out=np.nan, pnl_es=0.0, pnl_zn=0.0, cost=0.0, pnl=0.0, pnl_ideal=0.0)
        if reason:
            line.update(zero)
        else:
            q = {"ES": r.s * z.n_es, "ZN": -r.s * z.n_zn}
            q_exact = {"ES": r.s * z.n_es_exact, "ZN": -r.s * z.n_zn_exact}
            ids = {"ES": int(r.es_id), "ZN": int(r.zn_id)}
            settle_in = {"ES": r.es_entry, "ZN": r.zn_entry}
            settle_out = {"ES": r.es_exit, "ZN": r.zn_exit}
            pnl = cost = ideal = 0.0
            for leg in LEGS:
                if executable:
                    p_in = _fill(quote, ids[leg], r.entry, q[leg], True)
                    p_out = _fill(quote, ids[leg], r.exit, q[leg], False)
                    exit_exec = bool(np.isfinite(p_out))
                    if not exit_exec:
                        p_out, line["px_exit_fallback"] = settle_out[leg], True
                    per_contract = side_cost(leg, k=k, executable=True, cfg=cfg) + side_cost(leg, k=k, executable=exit_exec, cfg=cfg)
                else:
                    p_in, p_out = settle_in[leg], settle_out[leg]
                    per_contract = 2.0 * side_cost(leg, k=k, cfg=cfg)
                g = q[leg] * mult[leg] * (p_out - p_in)
                line[f"pnl_{leg.lower()}"] = g
                line[f"{leg.lower()}_in"], line[f"{leg.lower()}_out"] = p_in, p_out
                pnl += g
                cost += abs(q[leg]) * per_contract
                ideal += q_exact[leg] * mult[leg] * (p_out - p_in) - abs(q_exact[leg]) * per_contract
            line.update(n_es=z.n_es, n_zn=z.n_zn, q_es=q["ES"], q_zn=q["ZN"], notional=z.notional,
                        gross_nav=(z.n_es * z.es_size_px * mult["ES"] + z.n_zn * z.zn_size_px * mult["ZN"]) / nav,
                        cost=cost, pnl=pnl - cost, pnl_ideal=ideal)
        line["ret"] = line["pnl"] / nav
        line["rounding"] = line["pnl"] - line["pnl_ideal"]
        out.append(line)
    return pd.DataFrame(out)


def daily_pnl(ledger: pd.DataFrame, signals: pd.DataFrame, es: ContractPanel, zn: ContractPanel,
              sessions: pd.DatetimeIndex, *, cfg: FrozenConfig | None = None) -> pd.DataFrame:
    """Per-session USD P&L of a ledger, marked to the held contracts' settles.

    Gross P&L of session t is q·multiplier·(S_t − S_{t−1}) for t in (entry, exit],
    with the entry and exit fills replacing S_entry and S_exit (so a PX trade also
    marks fill-to-settle on the entry session). Costs are booked half on the entry
    session and half on the exit session. Columns ``gross``, ``cost``, ``net``.
    Summing over sessions reproduces the ledger's ``pnl`` (tested).
    """
    cfg = cfg or frozen_config()
    sessions = pd.DatetimeIndex(sessions)
    gross = pd.Series(0.0, index=sessions)
    cost = pd.Series(0.0, index=sessions)
    sig = signals.reset_index(drop=True)
    for i, t in ledger.reset_index(drop=True).iterrows():
        if not t["traded"]:
            continue
        r = sig.iloc[i]
        window = sessions[(sessions >= t["entry"]) & (sessions <= t["exit"])]
        for leg, panel, iid in (("ES", es, int(r["es_id"])), ("ZN", zn, int(r["zn_id"]))):
            q = t[f"q_{leg.lower()}"] * cfg.multipliers[leg]
            path = panel.settle[iid].reindex(window).to_numpy(dtype=float)
            path[-1] = t[f"{leg.lower()}_out"]
            gross.loc[window[1:]] += q * np.diff(path)
            gross.loc[window[0]] += q * (path[0] - t[f"{leg.lower()}_in"])   # 0 for settlement fills
        cost.loc[window[0]] += t["cost"] / 2.0
        cost.loc[window[-1]] += t["cost"] / 2.0
    return pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost})
