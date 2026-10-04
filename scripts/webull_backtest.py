"""Run PG and P0 end to end in the Webull starter kit's backtest harness and check the note's numbers.

    python scripts/webull_backtest.py          # no data, no download: replays data/replay/ (~1 minute)

The kit (``third_party/webull_kit``, the track's Webull starter ZIP, vendored unmodified) is Backtrader
plus a Webull OpenAPI feed. That feed serves US stocks/ETFs only, so it cannot supply ES/ZN futures; this
runner keeps everything else from the kit (Cerebro, the analyzers ``examples/backtest/main.py`` adds,
its ``_compute_metrics`` / ``_print_results``, ``RecorderAnalyzer`` and the HTML report) and feeds it
Databento settlements through ``bt.feeds.PandasData``.

Inputs, in order of preference:
  * data mode, if settlement data is on disk (``data/derived/`` from the full pipeline, or the four
    raw files from ``python data/download.py --pull settlements``): the frozen engine is rerun from
    the settlements (signals, gate, contracts, sizes), and the result must equal the committed replay
    files in ``data/replay/``. ``--write-replay`` rewrites them instead.
  * replay mode, otherwise: ``data/replay/`` holds the engine's per-event trade ledger for PG and P0
    (dates, contracts, sizes), the settlement prices of the held contracts on holding days only, and
    the session calendar. No signal is recomputed in this mode; the trades are replayed.

Each row runs as one continuous Cerebro backtest over the walk-forward segment (IS and OOS) at a $10M
NAV, one feed per held contract, fills at the settlement (cheat-on-close), frozen per-side costs as a
fixed commission, CME maintenance margins. Backtrader's per-event P&L then goes through the note's
metric code, and the script fails unless trades, return, volatility, Sharpe (1x), max drawdown, worst
month and turnover equal ``results.json`` for both rows in both samples (amendment A21).
Outputs: reports/webull_backtest.json, reports/webull_backtest.md, reports/webull_kit_{PG,P0}.html.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
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
from gqh.reproduce import load_margins  # noqa: E402

NAV = 10e6                      # the note's reference NAV
ROWS = ("PG", "P0")
CHECKED = ("trades", "ann_return", "ann_vol", "sharpe", "max_drawdown", "worst_month", "turnover")
REPLAY = ROOT / "data" / "replay"
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


def replay_texts(inp: Inputs) -> dict[str, str]:
    """The committed replay files, as text (deterministic formatting)."""
    out = {}
    for row, led in inp.ledgers.items():
        t = led.copy()
        t["month"] = t["month"].astype(str)
        for c in ("entry", "exit"):
            t[c] = pd.to_datetime(t[c]).dt.strftime("%Y-%m-%d")
        out[f"ledger_{row}.csv"] = t.to_csv(index=False, float_format="%.10g")
    p = inp.prices.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.strftime("%Y-%m-%d")
    out["settlements_holding_days.csv"] = p.to_csv(index=False, float_format="%.10g")
    out["sessions.csv"] = pd.DataFrame({"date": inp.sessions.strftime("%Y-%m-%d")}).to_csv(index=False)
    return out


def from_replay(texts: dict[str, str] | None = None) -> Inputs:
    """Read the replay tables (from disk, or from ``texts`` so both modes run on identical inputs)."""
    read = (lambda n: pd.read_csv(io.StringIO(texts[n]))) if texts else (lambda n: pd.read_csv(REPLAY / n))
    ledgers = {}
    for row in ROWS:
        led = read(f"ledger_{row}.csv")
        led["month"] = pd.PeriodIndex(led["month"], freq="M")
        for c in ("entry", "exit"):
            led[c] = pd.to_datetime(led[c])
        led["traded"] = led["traded"].astype(bool)
        ledgers[row] = led
    prices = read("settlements_holding_days.csv")
    prices["date"] = pd.to_datetime(prices["date"])
    sessions = pd.DatetimeIndex(pd.to_datetime(read("sessions.csv")["date"]))
    return Inputs(ledgers, prices, sessions, "replay: committed trade ledger and holding-day settlements")


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


def run_row(led: pd.DataFrame, inp: Inputs, cfg, margins: dict, k: float = 1.0):
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


# -- main --------------------------------------------------------------------------------------------
def main() -> None:
    setup_logging()
    cfg = frozen_config()
    results = json.loads((ROOT / "results.json").read_text())
    margins = load_margins(ROOT) or {"ES": 26164.0, "ZN": 1875.0}
    failures = []

    panels = None if "--replay" in sys.argv else _settlement_panels()
    if panels is None:
        inp = from_replay()
    else:
        texts = replay_texts(from_engine(panels))
        if "--write-replay" in sys.argv:
            REPLAY.mkdir(parents=True, exist_ok=True)
            for name, text in texts.items():
                (REPLAY / name).write_text(text)
            print(f"wrote {sorted(texts)} to {REPLAY.relative_to(ROOT)}/")
        stale = [n for n, t in texts.items() if not (REPLAY / n).is_file() or (REPLAY / n).read_text() != t]
        if stale:
            failures.append(f"committed replay files differ from the engine rerun: {stale}")
        else:
            print("engine rerun from settlements reproduces every committed replay file byte for byte")
        inp = from_replay(texts)
        inp.mode = "data: engine rerun from settlements (equals data/replay/)"
    print(f"input mode: {inp.mode}")

    months = {s: pd.period_range(*results[f"rows_{s}"]["months"], freq="M") for s in ("IS", "OOS")}
    out, lines = {}, []
    for row in ROWS:
        led = inp.ledgers[row]
        strat, metrics, bt_pnl = run_row(led, inp, cfg, margins)
        if strat.rejected:
            failures.append(f"{row}: {len(strat.rejected)} orders rejected, e.g. {strat.rejected[:3]}")
        tr = led["traded"]
        eng = led.loc[tr].set_index("month")["pnl"]
        diff = (bt_pnl.reindex(eng.index).fillna(0.0) - eng).abs()
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
        render_report(strat.analyzers.recorder.get_analysis(), strat.closed_trades,
                      str(ROOT / "reports" / f"webull_kit_{row}.html"),
                      title=f"{row} @1x, Webull starter kit harness ({led['month'].min()} to {led['month'].max()})",
                      metrics=metrics)

    (ROOT / "reports" / "webull_backtest.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    md = ["# PG and P0 in the Webull starter kit's backtest harness", "",
          "Generated by `scripts/webull_backtest.py` (amendment A21). Engine, analyzers, metric code and HTML report:",
          "the Webull starter kit's (`third_party/webull_kit`). Feed: Databento settlements via `PandasData` (the kit's",
          "Webull OpenAPI feed has no ES/ZN futures). Every metric below is computed from Backtrader's per-event P&L",
          "with the note's metric code and checked against `results.json`.", "",
          "| Row | Sample | Trades | Ret/yr | Vol/yr | Sharpe 1× | Max DD | Worst month | Turnover/yr | = results.json |",
          "|---|---|---|---|---|---|---|---|---|---|", *lines, ""]
    for row in ROWS:
        r, m = out[row], out[row]["kit_metrics"]
        md.append(f"- **{row}**: {r['events_matched_0.01usd']}/{r['events']} events match the engine to $0.01 "
                  f"(max gap ${r['max_abs_event_diff_usd']:.2f}). Kit-native summary on daily equity: net P&L "
                  f"${m['pnl']:,.0f}, max drawdown {m['max_drawdown_pct']:.2f}%, daily-annualized Sharpe "
                  f"{m['sharpe_ratio'] if m['sharpe_ratio'] is None else round(m['sharpe_ratio'], 2)} (a different "
                  f"estimator from the note's monthly one), {m['total_trades']} leg trades. "
                  f"Report: `reports/webull_kit_{row}.html`.")
    (ROOT / "reports" / "webull_backtest.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\ninput mode: {inp.mode}")
    if failures:
        raise SystemExit("MISMATCH: " + "; ".join(failures))
    print("OK: the Webull-kit Backtrader run reproduces every checked number in results.json")


if __name__ == "__main__":
    main()
