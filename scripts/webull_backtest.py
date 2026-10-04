"""Run PG and P0 end to end in the Webull starter kit's backtest harness and check the note's numbers.

The kit (``gqh-webull-backtrader-starter``, the track's Webull starter ZIP) is Backtrader plus a Webull
OpenAPI feed. That feed serves US stocks/ETFs only, so it cannot supply ES/ZN futures; this runner keeps
everything else from the kit (Cerebro, the analyzers ``examples/backtest/main.py`` adds, its
``_compute_metrics`` / ``_print_results``, ``RecorderAnalyzer`` and the HTML report) and feeds it the
same Databento settlements the frozen engine uses, through ``bt.feeds.PandasData``.

One continuous Cerebro run per row over the whole walk-forward segment, IS and OOS, at a $10M NAV:
one feed per held contract, orders from the frozen engine's ledger (decisions, contracts and sizes are
the engine's; Backtrader does fills, commissions, margin and P&L), fills at the settlement
(cheat-on-close). Each event's Backtrader P&L then goes through the engine's own metric code, and the
script fails unless every reported number (return, vol, Sharpe 1x, max DD, worst month) equals
``results.json``. The frozen pipeline and ``results.json`` are not changed (amendment A21).

    python data/download.py --pull settlements    # once: ~$0.83 of Databento data (skip if data/derived exists)
    python scripts/webull_backtest.py             # fetches the kit ZIP from the track page on first run
    (WEBULL_KIT=/path/to/unzipped/kit uses a kit you already have)
    -> reports/webull_backtest.json, reports/webull_backtest.md, reports/webull_kit_{PG,P0}.html
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
KIT_URL = "https://www.gqhacks.com/webull/gqh-webull-backtrader-starter.zip"   # the track page's "DOWNLOAD KIT .ZIP"


def find_kit() -> Path:
    """WEBULL_KIT if set; else the kit unzipped in .webull_kit/ (fetched once from the track page,
    or from WEBULL_KIT_ZIP if that names a local copy of the ZIP)."""
    if os.environ.get("WEBULL_KIT"):
        kit = Path(os.environ["WEBULL_KIT"]).expanduser()
    else:
        cache = ROOT / ".webull_kit"
        hits = [p.parent for p in cache.glob("**/webull_bt/__init__.py")]
        if not hits:
            import io
            import urllib.request
            import zipfile
            src = os.environ.get("WEBULL_KIT_ZIP")
            print(f"fetching the Webull starter kit from {src or KIT_URL}", flush=True)
            data = Path(src).expanduser().read_bytes() if src else urllib.request.urlopen(KIT_URL, timeout=60).read()
            zipfile.ZipFile(io.BytesIO(data)).extractall(cache)
            hits = [p.parent for p in cache.glob("**/webull_bt/__init__.py")]
        kit = hits[0].parent if hits else cache
    if not (kit / "webull_bt").is_dir() or not (kit / "examples" / "backtest" / "main.py").is_file():
        raise SystemExit(f"Webull starter kit not found at {kit}: set WEBULL_KIT to the unzipped kit folder")
    return kit


KIT = find_kit()
sys.path[:0] = [str(KIT), str(KIT / "examples" / "backtest")]

import backtrader as bt  # noqa: E402

from main import _compute_metrics, _print_results  # noqa: E402  (the kit's metric/summary code)
from webull_bt.logging_utils import setup_logging  # noqa: E402
from webull_bt.visualize import RecorderAnalyzer, render_report  # noqa: E402

from gqh.config import frozen_config  # noqa: E402
from gqh.data import build_settlements_only  # noqa: E402
from gqh.engine import side_cost  # noqa: E402
from gqh.pipeline import _row_stats, prepare, segment_months  # noqa: E402
from gqh.reproduce import load_margins  # noqa: E402
from gqh.strategy import run_strategy  # noqa: E402

NAV = 10e6                      # the note's reference NAV
CHECKED = ("ann_return", "ann_vol", "sharpe", "max_drawdown", "worst_month", "trades")


def contract_feed(panel, iid: int, index: pd.DatetimeIndex, name: str):
    """Settlement bars on the common session index. Outside the contract's life the price is carried
    (no position is ever open then, so it never enters P&L)."""
    s = panel.settle[iid].reindex(index).ffill().bfill()
    df = pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "volume": 0.0, "openinterest": 0.0}, index=index)
    return bt.feeds.PandasData(dataname=df, name=name)


class LedgerStrategy(bt.Strategy):
    """Places the frozen engine's orders on their dates: close at exit, open at entry."""
    params = (("orders", None),)

    def __init__(self):
        self.by_name = {d._name: d for d in self.datas}
        self.closed_trades, self.trade_pnl, self.rejected = [], {}, []

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
            self.open_size = getattr(self, "open_size", {})
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


def run_row(row: str, led: pd.DataFrame, world, cfg, margins: dict, k: float = 1.0):
    ev = world.events.set_index("month")
    traded = led[led["traded"]]
    first, last = traded["entry"].min(), traded["exit"].max()
    sessions = world.sessions[(world.sessions >= first) & (world.sessions <= last)]
    index = sessions.append(pd.DatetimeIndex([sessions[-1] + pd.Timedelta(days=1)]))   # lets the last exit fill

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(NAV)
    cerebro.broker.set_coc(True)                       # market orders fill at the order bar's close (settlement)
    orders: dict = {}
    names, event_of = set(), {}
    for _, t in traded.iterrows():
        for leg, panel, col, qcol in (("ES", world.es, "es_id", "q_es"), ("ZN", world.zn, "zn_id", "q_zn")):
            iid, q = int(ev.at[t["month"], col]), int(t[qcol])
            if q == 0:
                continue
            name = f"{leg}_{iid}"
            if name not in names:
                names.add(name)
                cerebro.adddata(contract_feed(panel, iid, index, name))
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
    strat = cerebro.run(runonce=False)[0]
    metrics = _compute_metrics(cerebro, strat, NAV)
    _print_results(strat, metrics)

    # with cheat-on-close the broker executes an order while processing the next bar, so a trade's open
    # date is the bar after the entry: attribute it to that contract's latest entry on or before it
    pnl = pd.Series(0.0, index=traded["month"].unique())
    for (name, opened), v in strat.trade_pnl.items():
        entry = max(d for (n, d) in event_of if n == name and d <= opened)
        pnl[event_of[(name, entry)]] += v
    return strat, metrics, pnl


def load_settlements() -> dict[str, pd.DataFrame]:
    """Settlement panels: data/derived/ if the full pipeline has built it (unless GQH_SETTLEMENTS_ONLY=1),
    else built from the settlements-only download (``python data/download.py --pull settlements``)."""
    full = ROOT / "data" / "derived"
    if os.environ.get("GQH_SETTLEMENTS_ONLY") != "1" and all((full / f"settlements_{r}.parquet").is_file()
                                                              for r in ("ES", "ZN")):
        return {r: pd.read_parquet(full / f"settlements_{r}.parquet") for r in ("ES", "ZN")}
    raw = ROOT / "data" / "raw"
    need = [raw / f"{s}.dbn.zst" for s in ("is_definition", "is_statistics", "oos_definition", "oos_statistics")]
    missing = [p.name for p in need if not p.is_file()]
    if missing:
        raise SystemExit(f"missing {missing}: run `python data/download.py --pull settlements` (needs "
                         "DATABENTO_API_KEY in .env; about $0.83)")
    print("building settlement panels from definition + statistics (data/derived_settlements/)", flush=True)
    return build_settlements_only(raw, ROOT / "data" / "derived_settlements", ROOT / "data" / "selection_ranks.csv")


def main() -> None:
    setup_logging()
    cfg = frozen_config()
    results = json.loads((ROOT / "results.json").read_text())
    panels = load_settlements()
    world = prepare(panels, start=cfg.is_start, end=None, cfg=cfg)
    margins = load_margins(ROOT) or {"ES": 26164.0, "ZN": 1875.0}
    run = run_strategy(world.events, world.pseudos, world.es, world.zn, quote=None, cfg=cfg, cost_multipliers=(1.0,))

    out, lines, failures = {}, [], []
    for row in ("PG", "P0"):
        led = run.ledgers[(row, 1.0)]
        led = led[led["month"] >= run.segment_start]
        strat, metrics, bt_pnl = run_row(row, led, world, cfg, margins)
        if strat.rejected:
            failures.append(f"{row}: {len(strat.rejected)} orders rejected, e.g. {strat.rejected[:3]}")
        eng = led.set_index("month")["pnl"][led.set_index("month")["traded"]]
        diff = (bt_pnl.reindex(eng.index).fillna(0.0) - eng).abs()
        led_bt = led.copy()
        led_bt.loc[led_bt["traded"], "pnl"] = led_bt.loc[led_bt["traded"], "month"].map(bt_pnl).to_numpy()
        rec = {"kit_metrics": {k: v for k, v in metrics.items()}, "events": int(len(eng)),
               "events_matched_0.01usd": int((diff <= 0.01).sum()), "max_abs_event_diff_usd": float(diff.max()),
               "total_pnl_usd": {"backtrader": float(bt_pnl.sum()), "engine": float(eng.sum())}, "samples": {}}
        for s in ("IS", "OOS"):
            months = segment_months(run, world.events, s)
            mine = _row_stats(led_bt, months, cfg)
            ref = results[f"rows_{s}"]["rows"][f"{row}@1x"]
            cmp = {c: {"backtrader": mine[c], "results_json": ref[c]} for c in CHECKED}
            bad = [c for c in CHECKED if not (mine[c] is None and ref[c] is None)
                   and not math.isclose(float(mine[c]), float(ref[c]), rel_tol=1e-6, abs_tol=1e-9)]
            if bad:
                failures.append(f"{row} {s}: {bad}")
            rec["samples"][s] = {"months": [str(months[0]), str(months[-1])], "metrics": cmp, "match": not bad}
            lines.append(f"| {row} | {s} | {mine['trades']} | {mine['ann_return']:.2%} | {mine['ann_vol']:.2%} | "
                         f"{mine['sharpe']:.2f} | {mine['max_drawdown']:.2%} | {mine['worst_month']:.2%} | "
                         f"{'yes' if not bad else 'NO'} |")
        out[row] = rec
        render_report(strat.analyzers.recorder.get_analysis(), strat.closed_trades,
                      str(ROOT / "reports" / f"webull_kit_{row}.html"),
                      title=f"{row} @1x, Webull starter kit harness ({led['month'].min()} to {led['month'].max()})",
                      metrics=metrics)

    (ROOT / "reports" / "webull_backtest.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    md = ["# PG and P0 in the Webull starter kit's backtest harness", "",
          "Generated by `scripts/webull_backtest.py` (amendment A21). Feed: Databento settlements via `PandasData`",
          "(the kit's Webull OpenAPI feed has no ES/ZN futures). Engine, analyzers, metric code and HTML report: the kit's.",
          "Metrics below are computed from Backtrader's per-event P&L with the note's metric code.", "",
          "| Row | Sample | Trades | Ret/yr | Vol/yr | Sharpe 1× | Max DD | Worst month | = results.json |",
          "|---|---|---|---|---|---|---|---|---|", *lines, ""]
    for row in ("PG", "P0"):
        r, m = out[row], out[row]["kit_metrics"]
        md.append(f"- **{row}**: {r['events_matched_0.01usd']}/{r['events']} events match the engine to $0.01 "
                  f"(max gap ${r['max_abs_event_diff_usd']:.2f}). Kit-native summary on daily equity: net P&L "
                  f"${m['pnl']:,.0f}, max drawdown {m['max_drawdown_pct']:.2f}%, daily-annualized Sharpe "
                  f"{m['sharpe_ratio'] if m['sharpe_ratio'] is None else round(m['sharpe_ratio'], 2)}, "
                  f"{m['total_trades']} leg trades. Report: `reports/webull_kit_{row}.html`.")
    (ROOT / "reports" / "webull_backtest.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    if failures:
        raise SystemExit("MISMATCH: " + "; ".join(failures))
    print("\nOK: the Webull-kit Backtrader run reproduces every checked number in results.json")


if __name__ == "__main__":
    main()
