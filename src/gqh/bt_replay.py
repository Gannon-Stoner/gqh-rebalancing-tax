"""Second-engine check: replay the engine's trades in Backtrader (the Webull starter kit's engine).

Each traded event is replayed in its own ``backtrader.Cerebro`` with two daily feeds,
the held ES and ZN contracts' Databento settlements over the event window (entry
through exit). Orders are sized from the ledger (signed contracts) and fill at the
close of the order bar (``set_coc(True)``), which is the settlement. Futures use
the frozen multipliers, CME maintenance margins, and the frozen per-side cost
(half-spread + fee, times the cost multiplier) as a fixed per-contract commission.

Backtrader then computes the P&L on its own (broker value change). The check is that
it equals the engine's ledger P&L for every event. Decisions, contract selection and
sizing come from the engine, so this verifies the accounting and fills, not the
signal. PX (15:59 ET bid/ask) is not replayed (daily bars only).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gqh.config import FrozenConfig, frozen_config
from gqh.contracts import ContractPanel
from gqh.engine import side_cost

START_CASH = 1e8   # large enough that margin never blocks an order; P&L is the value change


def _bt():
    import backtrader as bt  # optional dependency (pinned like the starter kit: backtrader==1.9.78.123)

    return bt


def _feed(bt, panel: ContractPanel, iid: int, window: pd.DatetimeIndex, name: str):
    """Settlement bars over the window plus one flat placeholder bar the day after the exit.

    With cheat-on-close an order fills at the close of the bar it was issued on, but the
    broker executes it while processing the next bar; the placeholder lets the exit fill
    at the exit settlement. The position is flat by then, so its price never enters P&L.
    """
    s = panel.settle[iid].reindex(window)
    idx = window.append(pd.DatetimeIndex([window[-1] + pd.Timedelta(days=1)]))
    s = pd.Series(np.append(s.to_numpy(), s.iloc[-1]), index=idx)
    df = pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "volume": 0.0, "openinterest": 0.0}, index=idx)
    return bt.feeds.PandasData(dataname=df, name=name)


def replay_event(q_es: int, q_zn: int, es_id: int, zn_id: int, window: pd.DatetimeIndex, es: ContractPanel,
                 zn: ContractPanel, *, k: float = 1.0, margins: dict | None = None,
                 cfg: FrozenConfig | None = None) -> dict:
    """Backtrader P&L (USD, net of commission) of one event held from window[0] to window[-1]."""
    bt = _bt()
    cfg = cfg or frozen_config()
    margins = margins or {"ES": 26164.0, "ZN": 1875.0}
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(START_CASH)
    cerebro.broker.set_coc(True)                       # market orders fill at the order bar's close
    for leg, panel, iid in (("ES", es, es_id), ("ZN", zn, zn_id)):
        cerebro.adddata(_feed(bt, panel, iid, window, leg))
        cerebro.broker.addcommissioninfo(
            bt.CommInfoBase(commission=side_cost(leg, k=k, cfg=cfg), mult=cfg.multipliers[leg], margin=margins[leg],
                            commtype=bt.CommInfoBase.COMM_FIXED, stocklike=False), name=leg)

    class Replay(bt.Strategy):
        def __init__(self):
            self.fills = []

        def next(self):
            if len(self) == 1:
                for data, q in zip(self.datas, (q_es, q_zn)):
                    if q > 0:
                        self.buy(data=data, size=q)
                    elif q < 0:
                        self.sell(data=data, size=-q)
            elif len(self) == len(window):          # the exit bar (the placeholder follows it)
                for data in self.datas:
                    self.close(data=data)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append((order.data._name, order.executed.size, order.executed.price, order.executed.comm))

    cerebro.addstrategy(Replay)
    strat = cerebro.run()[0]
    return {"pnl": float(cerebro.broker.getvalue() - START_CASH), "fills": strat.fills}


def replay_ledger(ledger: pd.DataFrame, signals: pd.DataFrame, es: ContractPanel, zn: ContractPanel,
                  sessions: pd.DatetimeIndex, *, k: float = 1.0, margins: dict | None = None,
                  cfg: FrozenConfig | None = None) -> pd.DataFrame:
    """Per traded event: engine P&L, Backtrader P&L and their difference (USD)."""
    sig = signals.reset_index(drop=True)
    rows = []
    for i, t in ledger.reset_index(drop=True).iterrows():
        if not t["traded"]:
            continue
        window = sessions[(sessions >= t["entry"]) & (sessions <= t["exit"])]
        r = replay_event(int(t["q_es"]), int(t["q_zn"]), int(sig.at[i, "es_id"]), int(sig.at[i, "zn_id"]), window,
                         es, zn, k=k, margins=margins, cfg=cfg)
        rows.append({"month": t["month"], "engine_pnl": float(t["pnl"]), "backtrader_pnl": r["pnl"],
                     "diff": r["pnl"] - float(t["pnl"]), "fills": len(r["fills"])})
    return pd.DataFrame(rows)


def reconciliation_summary(rep: pd.DataFrame, tol_usd: float = 0.01) -> dict:
    """Counts and totals for the note: events, matches within ``tol_usd``, largest gap, totals."""
    if rep.empty:
        return {"events": 0}
    return {"events": int(len(rep)), "matched": int((rep["diff"].abs() <= tol_usd).sum()),
            "max_abs_diff_usd": float(rep["diff"].abs().max()), "engine_total_usd": float(rep["engine_pnl"].sum()),
            "backtrader_total_usd": float(rep["backtrader_pnl"].sum()), "tolerance_usd": tol_usd,
            "all_fills": bool((rep["fills"] == 4).all())}
