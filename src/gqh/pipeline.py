"""End-to-end evaluation: derived data -> signals -> six rows -> tests, metrics, capacity.

``evaluate`` returns a plain dict that ``gqh.reproduce`` writes as JSON with sorted
keys and floats rounded to 10 significant digits, so two runs are byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gqh import stats as S
from gqh.calendar import SessionCalendar, qualifying_sessions, trading_schedule
from gqh.capacity import capacity_summary, capacity_table
from gqh.config import FrozenConfig, frozen_config
from gqh.contracts import ContractPanel, reference_returns
from gqh import diagnostics as G
from gqh.data import bar_volume
from gqh.metrics import monthly_returns, realized_to_target, row_metrics
from gqh.quotes import QuoteBook
from gqh.signals import compute_signals, stacked_panel
from gqh.strategy import StrategyRun, run_strategy

# Deflation counts (HYPOTHESIS.md §5, §8): the 6 registered rows; plus the 29 logged prior month-end
# variants; plus the 45 logged trend/vol variants (amendment A15).
PRIOR_LOOKS = {"registered_6": 6, "month_end_family_35": 35, "all_logged_80": 80}
DELTA_PAIRS = (("PG", "P0"), ("PG", "PD"), ("PG", "PE"))


@dataclass
class World:
    sessions: pd.DatetimeIndex
    sched: pd.DataFrame
    es: ContractPanel
    zn: ContractPanel
    ref: pd.DataFrame
    events: pd.DataFrame
    pseudos: pd.DataFrame
    es_long: pd.DataFrame | None = None
    zn_long: pd.DataFrame | None = None


def prepare(panels: dict[str, pd.DataFrame], *, start=None, end=None, cfg: FrozenConfig | None = None) -> World:
    """Sessions, schedule, contracts, reference returns and signals from settlement panels."""
    cfg = cfg or frozen_config()
    qual = qualifying_sessions(panels["ES"]["date"].unique(), panels["ZN"]["date"].unique(), start, end)
    sched = trading_schedule(SessionCalendar(qual))
    es, zn = ContractPanel.from_long(panels["ES"], "ES"), ContractPanel.from_long(panels["ZN"], "ZN")
    ref = reference_returns(es, zn, qual)
    ev = compute_signals(sched, ref, es, zn, kind="event", cfg=cfg)
    ps = compute_signals(sched, ref, es, zn, kind="pseudo", cfg=cfg)
    return World(qual, sched, es, zn, ref, ev, ps, panels["ES"], panels["ZN"])


def _test(t: S.CoefTest) -> dict:
    return {"term": t.term, "estimate": t.estimate, "se": t.se, "t": t.t, "p_one_sided": t.p,
            "ci90": list(t.ci), "alternative": t.alternative, "method": t.method, "draws": t.draws, "n": t.n}


def confirmatory(world: World, *, cfg: FrozenConfig, draws: int) -> dict:
    """H1 and H2 on IS rows: month-block primary, Holm over the pair, wild and Newey-West sensitivities."""
    ev = world.events[world.events["sample"] == "IS"]
    st = stacked_panel(ev, world.pseudos[world.pseudos["sample"] == "IS"])
    out = {}
    for name, fn, data in (("H1", S.h1_test, ev), ("H2", S.h2_test, st)):
        out[name] = {m: _test(fn(data, seed=cfg.seed, draws=draws, method=m))
                     for m in ("month_block", "wild", "newey_west")}
    adj = S.holm([out["H1"]["month_block"]["p_one_sided"], out["H2"]["month_block"]["p_one_sided"]])
    out["holm"] = {"H1": float(adj[0]), "H2": float(adj[1]), "alpha": 0.05,
                   "reject": {"H1": bool(adj[0] < 0.05), "H2": bool(adj[1] < 0.05)}}
    out["mde"] = {"H1_b_IS": S.mde(out["H1"]["month_block"]["se"]), "H2_cE_IS": S.mde(out["H2"]["month_block"]["se"])}
    return out


def segment_months(run: StrategyRun, events: pd.DataFrame, sample: str) -> pd.PeriodIndex:
    """IS: the common walk-forward segment through the last IS month; OOS: every OOS month."""
    m = pd.PeriodIndex(events.loc[events["sample"] == sample, "month"], freq="M")
    if m.empty:
        return pd.PeriodIndex([], freq="M")
    start = max(run.segment_start, m.min()) if sample == "IS" else m.min()
    return pd.period_range(start, m.max(), freq="M")


def _row_stats(led: pd.DataFrame, months: pd.PeriodIndex, cfg: FrozenConfig) -> dict:
    m = row_metrics(led, months, cfg)
    r = monthly_returns(led, months).to_numpy()
    ok = len(r) > 3 and r.std(ddof=1) > 0
    m["psr0"] = S.probabilistic_sharpe(r) if ok else None
    m["dsr"] = {name: (S.deflated_sharpe(r, n) if ok else None) for name, n in PRIOR_LOOKS.items()}
    return m


def rows_section(world: World, run: StrategyRun, volume: dict[int, pd.Series], *, sample: str,
                 cfg: FrozenConfig, draws: int) -> dict:
    """Metrics of every row and cost multiplier, ΔSR CIs, capacity and realized-to-target vol on one sample."""
    months = segment_months(run, world.events, sample)
    if months.empty:
        return {"months": []}
    out: dict = {"months": [str(months[0]), str(months[-1])], "n_months": len(months), "rows": {}, "delta_sharpe": {},
                 "monthly_returns_1x": {}}
    for (row, k), led in sorted(run.ledgers.items()):
        out["rows"][f"{row}@{k:g}x"] = _row_stats(led, months, cfg)
        if k == 1.0:
            out["monthly_returns_1x"][row] = monthly_returns(led, months).round(12).tolist()
    for a, b in DELTA_PAIRS:
        for k in cfg.cost_multipliers:
            ra, rb = (monthly_returns(run.ledgers[(x, k)], months) for x in (a, b))
            est, ci = S.delta_sharpe_ci(ra, rb, seed=cfg.seed, draws=draws)
            out["delta_sharpe"][f"{a}-{b}@{k:g}x"] = {"estimate": est, "ci90": list(ci)}
    seg = lambda led: led[led["month"].isin(months)]  # noqa: E731
    out["capacity"] = {
        "PG_settle_windows": capacity_summary(capacity_table(seg(run.ledgers[("PG", 1.0)]),
                                                             world.events[world.events["month"].isin(months)], volume,
                                                             mode="settle", cfg=cfg)),
    }
    if ("PX", 1.0) in run.ledgers:
        out["capacity"]["PX_fill_minute"] = capacity_summary(capacity_table(
            seg(run.ledgers[("PX", 1.0)]), world.events[world.events["month"].isin(months)], volume, mode="px", cfg=cfg))
        px = seg(run.ledgers[("PX", 1.0)])
        out["px_fills"] = {"reasons": px["reason"].value_counts().to_dict(),
                           "exit_fallbacks": int(px["px_exit_fallback"].sum())}
    rtt = realized_to_target(seg(run.ledgers[("PG", 1.0)]), cfg)
    out["realized_to_target_PG"] = {str(y): v for y, v in rtt.items()}
    return out


def oos_section(world: World, *, cfg: FrozenConfig, draws: int) -> dict:
    """b_OOS, c_OOS and the differences Δb = b_OOS − b_IS, Δc = c_OOS − c_IS with 90% CIs (no ratios).

    Before OOS rows exist it states the OOS MDE from the IS standard errors scaled to
    the OOS length, so the MDE is on record before opening.
    """
    ev, ps = world.events, world.pseudos
    parts = {s: (ev[ev["sample"] == s], stacked_panel(ev[ev["sample"] == s], ps[ps["sample"] == s])) for s in ("IS", "OOS")}
    out: dict = {}
    for name, terms, term, idx in (("b", S.H1_TERMS, S.H1_TERM, 0), ("c_E", S.H2_TERMS, S.H2_TERM, 1)):
        df_is = parts["IS"][idx]
        df_is = df_is[df_is["valid"]] if "valid" in df_is.columns else df_is
        b_is, d_is = S.coef_draws(df_is.astype({c: float for c in ("QE", "ME") if c in df_is.columns}),
                                  terms, term, seed=cfg.seed, draws=draws)
        df_oos = parts["OOS"][idx]
        df_oos = df_oos[df_oos["valid"]] if "valid" in df_oos.columns else df_oos
        if len(df_oos) < 12:
            se_is = float(np.std(d_is, ddof=1))
            n_is = len(df_is)
            out[name] = {"IS": b_is, "OOS": None, "oos_rows": int(len(df_oos)),
                         "mde_oos_at_24_months": S.mde(se_is * np.sqrt(n_is / (24 * (1 if idx == 0 else 2))))}
            continue
        b_oos, d_oos = S.coef_draws(df_oos.astype({c: float for c in ("QE", "ME") if c in df_oos.columns}),
                                    terms, term, seed=cfg.seed + 1, draws=draws)
        diff = d_oos - d_is
        out[name] = {"IS": b_is, "OOS": b_oos, "oos_rows": int(len(df_oos)),
                     "OOS_ci90": [float(v) for v in np.nanquantile(d_oos, [0.05, 0.95])],
                     "delta": b_oos - b_is, "delta_ci90": [float(v) for v in np.nanquantile(diff, [0.05, 0.95])]}
    return out


def evaluate(world: World, bbo: pd.DataFrame, ohlcv: pd.DataFrame, *, cfg: FrozenConfig | None = None,
             draws: int = 9999, samples: tuple[str, ...] = ("IS",), margins: dict | None = None,
             factors: pd.DataFrame | None = None) -> dict:
    """Everything the note reports, as a dict of plain values."""
    cfg = cfg or frozen_config()
    run = run_strategy(world.events, world.pseudos, world.es, world.zn, quote=QuoteBook(bbo), cfg=cfg)
    volume = bar_volume(ohlcv)
    ev = world.events
    res = {
        "protocol": {"seed": cfg.seed, "draws": draws, "is": [str(cfg.is_start.date()), str(cfg.is_end.date())],
                     "primary": cfg.primary, "prior_looks": PRIOR_LOOKS},
        "sample_counts": {s: {"events": int((ev["sample"] == s).sum()), "valid_events": int((ev["valid"] & (ev["sample"] == s)).sum()),
                              "valid_pseudos": int((world.pseudos["valid"] & (world.pseudos["sample"] == s)).sum())}
                          for s in ("IS", "OOS")},
        "segment_start": str(run.segment_start), "pe_participation_p": run.participation,
        "gate_final_coefficients": {g: run.gates[g].dropna(subset=["yhat"]).iloc[-1].filter(like="coef_").to_dict()
                                    if run.gates[g]["yhat"].notna().any() else None for g in ("PG", "PD", "PP")},
        "confirmatory": confirmatory(world, cfg=cfg, draws=draws),
        "oos_slopes": oos_section(world, cfg=cfg, draws=draws),
    }
    for s in samples:
        res[f"rows_{s}"] = rows_section(world, run, volume, sample=s, cfg=cfg, draws=draws)
    res["diagnostics"] = diagnostics_section(world, run, QuoteBook(bbo), cfg=cfg)
    for s in samples:
        months = segment_months(run, world.events, s)
        if len(months):
            res[f"risk_{s}"] = risk_section(world, run, months, cfg=cfg, margins=margins, factors=factors)
    return res


def diagnostics_section(world: World, run: StrategyRun, quotes: QuoteBook, *, cfg: FrozenConfig) -> dict:
    """§6 diagnostics: event-time path by era, legs and direction, action ledger, benchmark clock."""
    paths = G.event_paths(world.ref, world.sched, cfg=cfg)
    prof = G.path_profile(paths) if len(paths) else pd.DataFrame()
    pg = run.ledgers[("PG", 1.0)]
    act = G.action_ledger(pg, run.gates["PG"], world.events)
    act = act[act["yhat"].notna()]
    clock = G.clock_summary(G.clock_panel(quotes, world.ref, world.sched, world.events))
    return {
        "event_path_by_era": {era: row.to_dict() for era, row in prof.iterrows()},
        "legs_direction": {row: {str(k): v for k, v in G.legs_direction(run.ledgers[(row, 1.0)]).to_dict(orient="index").items()}
                           for row in ("P0", "PG")},
        "action_ledger_PG": act.assign(month=act["month"].astype(str)).to_dict(orient="list"),
        "benchmark_clock": clock.to_dict(orient="records"),
    }


def _event_daily(led: pd.DataFrame, world: World, cfg: FrozenConfig) -> pd.DataFrame:
    """Per traded event, its daily gross P&L rows (month, date, gross) from ``engine.daily_pnl``."""
    from gqh.engine import daily_pnl

    rows = []
    for i in np.flatnonzero(led["traded"].to_numpy()):
        one = led.copy()
        one["traded"] = False
        one.iloc[i, one.columns.get_loc("traded")] = True
        d = daily_pnl(one, world.events, world.es, world.zn, world.sessions, cfg=cfg)
        d = d[(d.index >= led.iloc[i]["entry"]) & (d.index <= led.iloc[i]["exit"])]
        rows.append(pd.DataFrame({"month": led.iloc[i]["month"], "date": d.index, "gross": d["gross"].to_numpy()}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["month", "date", "gross"])


def risk_section(world: World, run: StrategyRun, months: pd.PeriodIndex, *, cfg: FrozenConfig,
                 margins: dict | None = None, factors: pd.DataFrame | None = None) -> dict:
    """Stress table, survival, months to t = 2, 2σ stop stress, margin, factor regression, impact curve."""
    from gqh import risk as R
    from gqh.engine import daily_pnl
    from gqh.signals import ewma_sigma

    nav = cfg.reference_nav
    out: dict = {}
    seg = lambda led: led[led["month"].isin(months)]  # noqa: E731
    for row in ("PG", "P0"):
        led = seg(run.ledgers[(row, 1.0)])
        r = monthly_returns(led, months)
        block = {"stress": R.stress_table(led, nav).to_dict(orient="records"),
                 "p_drawdown_7p5_in_36m": R.drawdown_probability(r, seed=cfg.seed),
                 "months_to_t2": R.months_to_t2(r)}
        ev_daily = _event_daily(led, world, cfg)
        block["stop_2sigma_stress"] = R.stop_loss_stress(led, ev_daily, cfg)
        if margins:
            daily = daily_pnl(led, world.events[world.events["month"].isin(months)], world.es, world.zn, world.sessions, cfg=cfg)
            block["margin"] = R.margin_ledger(led, daily["net"], margins, nav)
        if factors is not None:   # Ken French Mkt-RF, SMB, HML, Mom plus the ZN reference return (§9)
            t = led[led["traded"]]
            f = factors.join(world.ref["r_zn"].rename("ZN"), how="inner")
            block["factor_regression"] = R.factor_regression(t["ret"], t[["month", "entry", "exit"]], f)
        out[row] = block
    # Square-root impact scenario for PG: σ_d = EWMA vol of each leg at the decision; V = traded volume on the entry day.
    pg = seg(run.ledgers[("PG", 1.0)])
    t = pg[pg["traded"]]
    if len(t):
        vol_es, vol_zn = ewma_sigma(world.ref["r_es"], cfg.ewma_lambda), ewma_sigma(world.ref["r_zn"], cfg.ewma_lambda)
        ev = world.events.reset_index(drop=True)
        sig_d = pd.DataFrame({"ES": [vol_es.get(d, np.nan) for d in t["dec"]], "ZN": [vol_zn.get(d, np.nan) for d in t["dec"]]},
                             index=t.index)
        vmap = {leg: p.set_index(["date", "instrument_id"])["volume_1m"] if "volume_1m" in p.columns else None
                for leg, p in (("ES", world.es_long), ("ZN", world.zn_long)) if p is not None}
        if vmap and all(v is not None for v in vmap.values()):
            V = pd.DataFrame({leg: [float(vmap[leg].get((e, int(ev.loc[i, f"{leg.lower()}_id"])), np.nan))
                                    for i, e in zip(t.index, t["entry"])] for leg in ("ES", "ZN")}, index=t.index)
            out["impact_PG"] = R.sharpe_vs_nav(pg, months, sig_d, V, cfg=cfg).to_dict(orient="records")
    return out
