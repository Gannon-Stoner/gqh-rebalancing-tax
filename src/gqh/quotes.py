"""Quote state from Databento bbo-1m records (amendment A9).

A bbo-1m record is stamped (``ts_recv``) at the end of its minute and a missing
minute means the best bid/offer did not change. The quote state at time t is
therefore the last record with ``ts_recv`` <= t, provided it is at most
``max_stale`` old. A one-sided, crossed or missing (NaN) quote counts as no quote.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAX_STALE = pd.Timedelta(minutes=5)


class QuoteBook:
    """Point-in-time bid/ask lookup per instrument; usable as ``gqh.engine.QuoteFn``.

    ``bbo`` has columns ``ts_et`` (naive America/New_York timestamps) or a
    DatetimeIndex of them, ``instrument_id``, ``bid_px_00`` and ``ask_px_00``.
    """

    def __init__(self, bbo: pd.DataFrame, *, max_stale: pd.Timedelta = MAX_STALE):
        df = bbo.reset_index() if "ts_et" not in bbo.columns else bbo
        df = df.sort_values(["instrument_id", "ts_et"], kind="mergesort")
        self.max_stale = max_stale
        self._by_id = {int(i): (g["ts_et"].to_numpy(dtype="datetime64[ns]"), g["bid_px_00"].to_numpy(dtype=float),
                                g["ask_px_00"].to_numpy(dtype=float))
                       for i, g in df.groupby("instrument_id", sort=False)}

    def state(self, iid: int, t: pd.Timestamp) -> tuple[float, float, pd.Timedelta] | None:
        """(bid, ask, age) of the last record at or before ``t``; None if there is none."""
        rec = self._by_id.get(int(iid))
        if rec is None:
            return None
        ts, bid, ask = rec
        j = int(np.searchsorted(ts, np.datetime64(pd.Timestamp(t).to_datetime64(), "ns"), side="right")) - 1
        if j < 0:
            return None
        return float(bid[j]), float(ask[j]), pd.Timestamp(t) - pd.Timestamp(ts[j])

    def __call__(self, iid: int, t: pd.Timestamp) -> tuple[float, float] | None:
        """Fresh two-sided quote (bid, ask) at ``t``, or None."""
        st = self.state(iid, t)
        if st is None:
            return None
        bid, ask, age = st
        if age > self.max_stale or not (np.isfinite(bid) and np.isfinite(ask)) or bid <= 0 or bid > ask:
            return None
        return bid, ask
