"""Replay PG and P0 in the Webull starter kit's backtest harness and check the note's numbers.

    python data/download.py --quote settlements
    python data/download.py --pull settlements
    python scripts/webull_backtest.py

The unmodified Webull starter kit is vendored in ``third_party/webull_kit``. Its Backtrader
engine, analyzers and report generator receive licensed Databento ES/ZN settlements through
``PandasData``; no Webull account or broker connection is used.

The default (also available as ``--data``) rebuilds signals, gate decisions, contract selection
and sizes from local licensed settlements, then executes the resulting orders in Backtrader.
No price data or replay bundle is distributed. Missing inputs stop with download instructions.

Each row runs as one continuous Cerebro backtest over the walk-forward segment (IS and OOS) at a $10M
NAV, one feed per held contract, fills at the settlement (cheat-on-close), frozen per-side costs as a
fixed commission, CME maintenance margins. Backtrader's per-event P&L then goes through the note's
metric code, and the script fails unless trades, return, volatility, Sharpe (1x), max drawdown, worst
month and turnover equal ``results.json`` for both rows in both samples (amendment A21).
Outputs: reports/webull_backtest.{html,json,md}, reports/webull_kit_{PG,P0}.html.
Use ``--output-dir PATH`` to isolate reports and ``--verbose`` for the kit's trade-by-trade log.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import math
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
KIT = Path(os.environ.get("WEBULL_KIT", ROOT / "third_party" / "webull_kit")).expanduser()
if not (KIT / "webull_bt").is_dir() or not (KIT / "examples" / "backtest" / "main.py").is_file():
    raise SystemExit(f"Webull starter kit not found at {KIT}")
sys.path[:0] = [str(KIT), str(KIT / "examples" / "backtest")]

import backtrader as bt  # noqa: E402


from main import _compute_metrics, _print_results  # noqa: E402  (the kit's metric/summary code)
from webull_bt.logging_utils import setup_logging  # noqa: E402
from webull_bt.visualize import RecorderAnalyzer, render_report  # noqa: E402

from gqh.config import frozen_config  # noqa: E402
from gqh.engine import side_cost  # noqa: E402
from gqh.metrics import row_metrics  # noqa: E402
from gqh.panel import oos_unlocked  # noqa: E402
from gqh.reproduce import load_margins  # noqa: E402

NAV = 10e6                      # the note's reference NAV
ROWS = ("PG", "P0")
CHECKED = ("trades", "ann_return", "ann_vol", "sharpe", "max_drawdown", "worst_month", "turnover")
LEDGER_COLS = ["month", "sample", "entry", "exit", "traded", "es_id", "zn_id", "q_es", "q_zn", "gross_nav", "cost",
               "pnl"]
RAW_SETTLEMENT_FILES = ("is_definition", "is_statistics", "oos_definition", "oos_statistics")


@dataclass
class Inputs:
    ledgers: dict[str, pd.DataFrame]      # per row: the walk-forward segment, LEDGER_COLS
    prices: pd.DataFrame                  # root, instrument_id, date, settle (holding days of traded events)
    sessions: pd.DatetimeIndex            # trading sessions from the first entry to the last exit
    mode: str


# -- inputs ------------------------------------------------------------------------------------------
def _settlement_panels() -> dict[str, pd.DataFrame] | None:
    if not oos_unlocked(ROOT):
        raise SystemExit("PROTOCOL TAG MISSING: clone the Git repository with its freeze-final tag "
                         "(or run `git fetch --tags`). The frozen loader keeps OOS locked without it.")
    full = ROOT / "data" / "derived"
    if all((full / f"settlements_{r}.parquet").is_file() for r in ("ES", "ZN")):
        return {r: pd.read_parquet(full / f"settlements_{r}.parquet") for r in ("ES", "ZN")}
    raw = ROOT / "data" / "raw"
    if all((raw / f"{s}.dbn.zst").is_file() for s in RAW_SETTLEMENT_FILES):
        from gqh.data import build_settlements_only
        print("building settlement panels from definition + statistics (data/derived_settlements/)", flush=True)
        return build_settlements_only(raw, ROOT / "data" / "derived_settlements", ROOT / "data" / "selection_ranks.csv")
    return None


def from_engine(panels: dict[str, pd.DataFrame]) -> Inputs:
    """Rerun the frozen engine from settlements and cut the replay tables out of it."""
    from gqh.pipeline import prepare
    from gqh.strategy import run_strategy

    cfg = frozen_config()
    world = prepare(panels, start=cfg.is_start, end=None, cfg=cfg)
    run = run_strategy(world.events, world.pseudos, world.es, world.zn, quote=None, cfg=cfg, cost_multipliers=(1.0,))
    ids = world.events.set_index("month")[["es_id", "zn_id"]]
    ledgers = {}
    for row in ROWS:
        led = run.ledgers[(row, 1.0)]
        led = led[led["month"] >= run.segment_start].join(ids, on="month")
        ledgers[row] = led[LEDGER_COLS].reset_index(drop=True)
    days = []
    for led in ledgers.values():
        for _, t in led[led["traded"]].iterrows():
            window = world.sessions[(world.sessions >= t["entry"]) & (world.sessions <= t["exit"])]
            for root, panel, col in (("ES", world.es, "es_id"), ("ZN", world.zn, "zn_id")):
                s = panel.settle[int(t[col])].reindex(window)
                days.append(pd.DataFrame({"root": root, "instrument_id": int(t[col]), "date": window,
                                          "settle": s.to_numpy()}))
    prices = (pd.concat(days).drop_duplicates(["root", "instrument_id", "date"])
              .sort_values(["root", "instrument_id", "date"]).reset_index(drop=True))
    first = min(led.loc[led["traded"], "entry"].min() for led in ledgers.values())
    last = max(led.loc[led["traded"], "exit"].max() for led in ledgers.values())
    sessions = world.sessions[(world.sessions >= first) & (world.sessions <= last)]
    return Inputs(ledgers, prices, sessions, "data: engine rerun from settlements")


def load_inputs() -> Inputs:
    """Rebuild from licensed local data; never substitute a saved trade ledger."""
    panels = _settlement_panels()
    if panels is None:
        raise SystemExit(
            "DATA MISSING: licensed settlement data is required. Set DATABENTO_API_KEY in .env, "
            "run `python data/download.py --quote settlements`, then "
            "`python data/download.py --pull settlements`, and rerun this command. "
            "No download or charge is initiated by this runner.")
    return from_engine(panels)


def validate_inputs(inp: Inputs) -> None:
    """Reject gaps before the feed carries prices across flat (off-holding) days."""
    if (inp.sessions.empty or inp.sessions.hasnans or not inp.sessions.is_unique
            or not inp.sessions.is_monotonic_increasing):
        raise ValueError("session calendar must be nonempty, ordered and unique")
    if inp.prices.duplicated(["root", "instrument_id", "date"]).any():
        raise ValueError("duplicate contract/date settlements")
    if not inp.prices["settle"].map(lambda x: math.isfinite(x) and x > 0).all():
        raise ValueError("settlements must be finite and positive")
    px = inp.prices.set_index(["root", "instrument_id", "date"])["settle"]
    for row, led in inp.ledgers.items():
        if not led["month"].is_unique or not led["month"].is_monotonic_increasing:
            raise ValueError(f"{row}: event months must be ordered and unique")
        if led.loc[~led["traded"], ["q_es", "q_zn", "pnl"]].ne(0).any().any():
            raise ValueError(f"{row}: a non-traded event has contracts or P&L")
        traded = led.loc[led["traded"]]
        if traded.empty:
            raise ValueError(f"{row}: no traded events to replay")
        for _, t in traded.iterrows():
            if t["entry"] not in inp.sessions or t["exit"] not in inp.sessions or t["entry"] >= t["exit"]:
                raise ValueError(f"{row} {t['month']}: invalid entry/exit sessions")
            window = inp.sessions[(inp.sessions >= t["entry"]) & (inp.sessions <= t["exit"])]
            for leg, idcol, qcol in (("ES", "es_id", "q_es"), ("ZN", "zn_id", "q_zn")):
                q = t[qcol]
                if not math.isfinite(q) or q != int(q):
                    raise ValueError(f"{row} {t['month']}: {qcol} must be a whole contract count")
                if q == 0:
                    continue
                expected = pd.MultiIndex.from_product([[leg], [int(t[idcol])], window])
                missing = expected.difference(px.index)
                if len(missing):
                    raise ValueError(f"{row} {t['month']}: missing holding-day settlement {missing[0]}")


# -- the kit run -------------------------------------------------------------------------------------
def contract_feed(prices: pd.Series, index: pd.DatetimeIndex, name: str):
    """Settlement bars on the session index. Off the holding days the price is carried; no position is
    open then, so it never enters P&L or equity."""
    s = prices.reindex(index).ffill().bfill()
    df = pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "volume": 0.0, "openinterest": 0.0}, index=index)
    return bt.feeds.PandasData(dataname=df, name=name)


class LedgerStrategy(bt.Strategy):
    """Places the frozen engine's orders on their dates: close at exit, open at entry."""
    params = (("orders", None),)

    def __init__(self):
        self.by_name = {d._name: d for d in self.datas}
        self.closed_trades, self.trade_pnl, self.rejected, self.open_size = [], {}, [], {}

    def next(self):
        day = self.datas[0].datetime.date(0)
        for o in self.p.orders.get(day, []):
            data = self.by_name[o["name"]]
            if o["q"] is None:
                self.close(data=data)
            elif o["q"] > 0:
                self.buy(data=data, size=o["q"])
            elif o["q"] < 0:
                self.sell(data=data, size=-o["q"])

    def notify_order(self, order):
        if order.status in (order.Margin, order.Rejected, order.Canceled):
            self.rejected.append((order.data._name, str(self.datas[0].datetime.date(0))))

    def notify_trade(self, trade):
        if trade.justopened:
            self.open_size[trade.ref] = trade.size
        if trade.isclosed:
            key = (trade.data._name, bt.num2date(trade.dtopen).date())
            self.trade_pnl[key] = self.trade_pnl.get(key, 0.0) + trade.pnlcomm
            size = self.open_size.pop(trade.ref)
            mult = self.broker.getcommissioninfo(trade.data).p.mult
            self.closed_trades.append({     # the record format the kit's strategies keep (dual_ma.py)
                "symbol": trade.data._name, "direction": "LONG" if size > 0 else "SHORT", "size": abs(size),
                "entry_price": trade.price, "exit_price": trade.price + trade.pnl / (size * mult),
                "open_dt": bt.num2date(trade.dtopen), "close_dt": bt.num2date(trade.dtclose),
                "pnl": trade.pnl, "pnlcomm": trade.pnlcomm, "commission": trade.commission,
                "bars_held": trade.barlen})


def run_row(led: pd.DataFrame, inp: Inputs, cfg, margins: dict, k: float = 1.0, *, verbose: bool = False):
    traded = led[led["traded"]]
    first, last = traded["entry"].min(), traded["exit"].max()
    sessions = inp.sessions[(inp.sessions >= first) & (inp.sessions <= last)]
    index = sessions.append(pd.DatetimeIndex([sessions[-1] + pd.Timedelta(days=1)]))   # lets the last exit fill
    px = {key: g.set_index("date")["settle"] for key, g in inp.prices.groupby(["root", "instrument_id"])}

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(NAV)
    cerebro.broker.set_coc(True)                       # market orders fill at the order bar's close (settlement)
    orders: dict = {}
    names, event_of = set(), {}
    for _, t in traded.iterrows():
        for leg, col, qcol in (("ES", "es_id", "q_es"), ("ZN", "zn_id", "q_zn")):
            iid, q = int(t[col]), int(t[qcol])
            if q == 0:
                continue
            name = f"{leg}_{iid}"
            if name not in names:
                names.add(name)
                cerebro.adddata(contract_feed(px[(leg, iid)], index, name))
                cerebro.broker.addcommissioninfo(bt.CommInfoBase(
                    commission=side_cost(leg, k=k, cfg=cfg), mult=cfg.multipliers[leg], margin=margins[leg],
                    commtype=bt.CommInfoBase.COMM_FIXED, stocklike=False), name=name)
            orders.setdefault(t["exit"].date(), []).append({"name": name, "q": None})
            orders.setdefault(t["entry"].date(), []).append({"name": name, "q": q})
            event_of[(name, t["entry"].date())] = t["month"]
    for day in orders:                                  # exits before entries on the same bar
        orders[day].sort(key=lambda o: o["q"] is not None)

    cerebro.addstrategy(LedgerStrategy, orders=orders)
    # the analyzers examples/backtest/main.py adds
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Days, compression=1,
                        riskfreerate=0.0, annualize=True)
    cerebro.addanalyzer(RecorderAnalyzer, _name="recorder")
    with warnings.catch_warnings():
        # The legacy kit clock emits this deprecation on every Python 3.14 bar.
        # Suppress only that known warning; engine errors and other warnings remain visible.
        warnings.filterwarnings("ignore", message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
                                category=DeprecationWarning)
        strat = cerebro.run(runonce=False)[0]
    metrics = _compute_metrics(cerebro, strat, NAV)
    if verbose:
        _print_results(strat, metrics)

    # with cheat-on-close the broker executes an order while processing the next bar, so a trade's open
    # date is the bar after the entry: attribute it to that contract's latest entry on or before it
    pnl = pd.Series(0.0, index=traded["month"].unique())
    for (name, opened), v in strat.trade_pnl.items():
        entry = max(d for (n, d) in event_of if n == name and d <= opened)
        pnl[event_of[(name, entry)]] += v
    return strat, metrics, pnl


# -- main --------------------------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=(
        "Rebuild PG/P0 from licensed local settlements and verify 1x costs in the Webull starter kit. "
        "Download instructions: python data/download.py --quote settlements, then --pull settlements."))
    ap.add_argument("--data", action="store_true", help="rebuild from local settlements (the default)")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "reports", help="report directory (default: reports/)")
    ap.add_argument("--verbose", action="store_true", help="include the kit's trade-by-trade log")
    return ap.parse_args(argv)


def reconcile_events(row: str, engine: pd.Series, replay: pd.Series, failures: list[str]) -> pd.Series:
    """Every event must match: aggregate metric agreement cannot hide offsetting errors."""
    diff = (replay.reindex(engine.index) - engine).abs()
    bad = diff.isna() | (diff > 0.01)
    if bad.any():
        failures.append(f"{row}: {int(bad.sum())}/{len(engine)} event P&Ls differ by more than $0.01 or are missing")
    extra = replay.index.difference(engine.index)
    if len(extra):
        failures.append(f"{row}: unexpected replay events {list(extra.astype(str))}")
    return diff


def equity_svg(curves: dict, oos_start: pd.Timestamp) -> str:
    """Embed the broker's recorded daily equity without a browser plotting dependency."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    with plt.rc_context({"font.size": 11.5, "svg.fonttype": "none"}):
        fig, ax = plt.subplots(figsize=(10.5, 3.7), layout="constrained")
        for row, color, label in (("PG", "#1466a3", "PG strategy"), ("P0", "#b55b13", "P0 always-trade")):
            eq = curves[row]
            # RecorderAnalyzer converts midnight session labels to Eastern. Recover
            # the original UTC session dates rather than displaying the previous day.
            dates = pd.to_datetime(eq["datetime"], utc=True).tz_convert(None)
            values = [(float(value) - NAV) / NAV * 100 for value in eq["value"]]
            ax.plot(dates, values, color=color, linewidth=1.6, label=label)
        ax.axvline(oos_start, color="#64748b", linewidth=1, linestyle="--")
        ax.axvspan(oos_start, max(pd.to_datetime(c["datetime"], utc=True).max().tz_convert(None)
                                 for c in curves.values()), color="#cbd5e1", alpha=.28,
                   label=f"OOS from {oos_start:%b %Y}")
        ax.axhline(0, color="#64748b", linewidth=.7)
        ax.set_ylabel("Cumulative return (% of fixed NAV)")
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(axis="y", alpha=.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left", frameon=False, ncols=3, fontsize=11.5)
        ax.margins(x=.01)
        stream = io.StringIO()
        fig.savefig(stream, format="svg", metadata={"Date": None})
        plt.close(fig)
    markup = stream.getvalue()
    return "\n".join(line.rstrip() for line in markup[markup.index("<svg"):].splitlines())


def render_summary(out: dict, inp: Inputs, failures: list[str], destination: Path,
                   curves: dict, oos_start: pd.Timestamp) -> None:
    """Small offline entry point: note-comparable metrics before the detailed kit charts."""
    rows = []
    for row in ROWS:
        for sample, rec in out[row]["samples"].items():
            m = {k: v["backtrader"] for k, v in rec["metrics"].items()}
            values = [row, sample, str(m["trades"]), f"{m['ann_return']:.2%}", f"{m['ann_vol']:.2%}",
                      f"{m['sharpe']:.2f}", f"{m['max_drawdown']:.2%}", f"{m['worst_month']:.2%}",
                      f"{m['turnover']:.1f}×", "PASS" if rec["match"] else "FAIL"]
            rows.append("<tr>" + "".join(f"<td>{html.escape(v)}</td>" for v in values) + "</tr>")
    checks = "".join(f"<li>{row}: {out[row]['events_matched_0.01usd']}/{out[row]['events']} event P&amp;Ls "
                     f"match to $0.01; largest gap ${out[row]['max_abs_event_diff_usd']:.4f}.</li>" for row in ROWS)
    errors = "" if not failures else "<ul>" + "".join(f"<li>{html.escape(e)}</li>" for e in failures) + "</ul>"
    status = "PASS" if not failures else "FAIL"
    color = "#166534" if not failures else "#991b1b"
    destination.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Webull replay verification — {status}</title><style>
body{{font:17px/1.55 system-ui,sans-serif;margin:3rem auto;padding:0 1.5rem;max-width:1100px;color:#17202a}}
h1{{line-height:1.2}} .status{{font-weight:700;color:{color}}} table{{border-collapse:collapse;width:100%;font-size:15px}}
th,td{{padding:.65rem .5rem;border-bottom:1px solid #cbd5e1;text-align:right}}th:first-child,td:first-child{{text-align:left}}
.table{{overflow-x:auto}}a{{color:#075985}}code{{font-size:.9em}}.muted{{color:#475569}}
</style></head><body><h1>Webull starter kit replay verification</h1>
<p class="status">{status}: PG and P0, 1× frozen costs, $10 million reference NAV.</p>{errors}
<p><strong>Input mode:</strong> {html.escape(inp.mode)}.</p>
<p>Backtrader replays the frozen ES/ZN orders at settlement with the registered per-side costs.
Signals, contract selection and sizing are rebuilt from local licensed settlements using the frozen
research engine. Backtrader independently checks fills and accounting at assumed settlement marks.
This is not a Webull live-data or executable bid/ask backtest.</p>
<h2>Metrics checked against the Quant Note's results.json</h2><div class="table"><table><thead><tr>
<th>Row</th><th>Sample</th><th>Trades</th><th>Return/yr</th><th>Vol/yr</th><th>Sharpe</th><th>Max DD</th>
<th>Worst month</th><th>Turnover/yr</th><th>Metrics</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="muted">Net monthly event returns, fixed NAV, no compounding. Sharpe uses monthly returns annualized by √12.
Trades and turnover use the rebuilt ledger; the six-row strategy study, inference, capacity and 2× costs
are outside this PG/P0 1× check. IS and OOS dates follow results.json.</p><ul>{checks}</ul>
<h2>Daily settlement equity from Backtrader</h2>
<div style="overflow-x:auto" role="img" aria-label="PG and P0 daily cumulative returns on fixed NAV, with the out-of-sample period shaded from October 2024">
{equity_svg(curves, oos_start)}</div>
<p class="muted">Each curve uses the broker's recorded daily equity, net of 1× costs, divided by the fixed
$10 million starting NAV. This shows mark-to-market changes during each holding period. The table above
instead books each event's total P&amp;L in its event month; daily drawdowns and Sharpe therefore differ.
The extra flat processing day lets Backtrader complete the final settlement exit.</p>
<h2>Detailed reports</h2><p><a href="webull_kit_PG.html">PG strategy</a> ·
<a href="webull_kit_P0.html">P0 always-trade benchmark</a> ·
<a href="webull_backtest.json">Machine-readable verification</a> · <a href="webull_backtest.md">Text report</a></p>
<p class="muted">The kit's detailed charts use daily equity and individual leg trades, so their native Sharpe
and trade counts differ from the monthly event metrics above. The portfolio equity chart is at the bottom
of each detailed report. Those charts load Plotly from its CDN and require internet; this summary works offline.</p>
</body></html>""", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging()
    cfg = frozen_config()
    results = json.loads((ROOT / "results.json").read_text())
    margins = load_margins(ROOT) or {"ES": 26164.0, "ZN": 1875.0}
    failures = []

    inp = load_inputs()
    try:
        validate_inputs(inp)
    except ValueError as exc:
        raise SystemExit(f"INVALID REPLAY INPUT: {exc}") from exc
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"input mode: {inp.mode}")
    scope = "signals, contract selection and sizes rebuilt from licensed local settlements"
    print(f"Checking PG/P0 at 1x costs against results.json; {scope}.", flush=True)

    months = {s: pd.period_range(*results[f"rows_{s}"]["months"], freq="M") for s in ("IS", "OOS")}
    out, lines, curves = {}, [], {}
    for row in ROWS:
        led = inp.ledgers[row]
        print(f"Running {row}...", flush=True)
        strat, metrics, bt_pnl = run_row(led, inp, cfg, margins, verbose=args.verbose)
        if strat.rejected:
            failures.append(f"{row}: {len(strat.rejected)} orders rejected, e.g. {strat.rejected[:3]}")
        expected_legs = int(led.loc[led["traded"], ["q_es", "q_zn"]].ne(0).sum().sum())
        if len(strat.closed_trades) != expected_legs:
            failures.append(f"{row}: expected {expected_legs} closed leg trades, got {len(strat.closed_trades)}")
        if any(strat.getposition(data).size for data in strat.datas):
            failures.append(f"{row}: positions remain open after the final exit")
        tr = led["traded"]
        eng = led.loc[tr].set_index("month")["pnl"]
        diff = reconcile_events(row, eng, bt_pnl, failures)
        led_bt = led.copy()                             # every return below is Backtrader's P&L / NAV
        led_bt.loc[tr, "pnl"] = led_bt.loc[tr, "month"].map(bt_pnl).to_numpy()
        led_bt["ret"] = led_bt["pnl"] / NAV
        rec = {"kit_metrics": dict(metrics), "events": int(len(eng)),
               "events_matched_0.01usd": int((diff <= 0.01).sum()), "max_abs_event_diff_usd": float(diff.max()),
               "total_pnl_usd": {"backtrader": float(bt_pnl.sum()), "engine": float(eng.sum())}, "samples": {}}
        for s, m in months.items():
            mine = row_metrics(led_bt, m, cfg)
            ref = results[f"rows_{s}"]["rows"][f"{row}@1x"]
            cmp = {c: {"backtrader": mine[c], "results_json": ref[c]} for c in CHECKED}
            bad = [c for c in CHECKED if not math.isclose(float(mine[c]), float(ref[c]), rel_tol=1e-6, abs_tol=1e-9)]
            if bad:
                failures.append(f"{row} {s}: {bad}")
            rec["samples"][s] = {"months": [str(m[0]), str(m[-1])], "metrics": cmp, "match": not bad}
            lines.append(f"| {row} | {s} | {mine['trades']} | {mine['ann_return']:.2%} | {mine['ann_vol']:.2%} | "
                         f"{mine['sharpe']:.2f} | {mine['max_drawdown']:.2%} | {mine['worst_month']:.2%} | "
                         f"{mine['turnover']:.1f}× | {'yes' if not bad else 'NO'} |")
        out[row] = rec
        recorded = strat.analyzers.recorder.get_analysis()
        curves[row] = recorded["equity"]
        render_report(recorded, strat.closed_trades,
                      str(output_dir / f"webull_kit_{row}.html"),
                      title=f"{row} @1x, Webull starter kit harness ({led['month'].min()} to {led['month'].max()})",
                      metrics=metrics)

    out["_verification"] = {"passed": not failures, "input_mode": inp.mode, "cost_multiplier": 1.0,
                            "checked_metrics": list(CHECKED), "failures": failures}
    (output_dir / "webull_backtest.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    md = ["# PG and P0 in the Webull starter kit's backtest harness", "",
          "Generated by `scripts/webull_backtest.py` (amendment A21). Engine, analyzers, metric code and HTML report:",
          "the Webull starter kit's (`third_party/webull_kit`). Feed: Databento settlements via `PandasData` (the kit's",
          "Webull OpenAPI feed has no ES/ZN futures). Every metric below is computed from Backtrader's per-event P&L",
          "with the note's metric code and checked against `results.json` (trades and turnover use the rebuilt ledger).",
          f"Input mode: {inp.mode}. Signals, selection and sizing are rebuilt before the Backtrader check.",
          "Scope: PG and P0, IS and OOS, 1x costs only; not PX bid/ask execution, inference or capacity.", "",
          "| Row | Sample | Trades | Ret/yr | Vol/yr | Sharpe 1× | Max DD | Worst month | Turnover/yr | = results.json |",
          "|---|---|---|---|---|---|---|---|---|---|", *lines, ""]
    for row in ROWS:
        r, m = out[row], out[row]["kit_metrics"]
        md.append(f"- **{row}**: {r['events_matched_0.01usd']}/{r['events']} events match the engine to $0.01 "
                  f"(max gap ${r['max_abs_event_diff_usd']:.2f}). Kit-native summary on daily equity: net P&L "
                  f"${m['pnl']:,.0f}, max drawdown {m['max_drawdown_pct']:.2f}%, daily-annualized Sharpe "
                  f"{m['sharpe_ratio'] if m['sharpe_ratio'] is None else round(m['sharpe_ratio'], 2)} (a different "
                  f"estimator from the note's monthly one), {m['total_trades']} leg trades. "
                  f"Report: `webull_kit_{row}.html`.")
    md.extend(["", "Verification: " + ("FAIL" if failures else "PASS"), *[f"- {f}" for f in failures]])
    (output_dir / "webull_backtest.md").write_text("\n".join(md) + "\n")
    render_summary(out, inp, failures, output_dir / "webull_backtest.html", curves, months["OOS"][0].start_time)
    print("\n".join(md))
    print(f"\ninput mode: {inp.mode}")
    if failures:
        raise SystemExit("MISMATCH: " + "; ".join(failures))
    print("PASS: PG/P0 event P&Ls and all 28 checked sample metrics match results.json at 1x costs.")
    print(f"Open summary: {output_dir / 'webull_backtest.html'}")


if __name__ == "__main__":
    main()
