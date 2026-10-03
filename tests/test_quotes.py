"""Point-in-time quote state from bbo-1m records (gqh.quotes, amendment A9)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from gqh.quotes import QuoteBook

T = pd.Timestamp


def _book() -> QuoteBook:
    rows = [  # ts_et is the END of the minute the record summarizes
        ("2024-03-01 15:50", 7, 5000.00, 5000.25),
        ("2024-03-01 15:58", 7, 5001.00, 5001.25),
        ("2024-03-01 16:00", 7, 5009.00, 5009.25),   # after the fill minute: must never be used at 15:59
        ("2024-03-01 15:52", 9, 110.0, 110.015625),
        ("2024-03-01 15:59", 8, 101.0, 100.5),       # crossed
        ("2024-03-01 15:59", 6, np.nan, 100.5),      # one-sided
    ]
    df = pd.DataFrame(rows, columns=["ts_et", "instrument_id", "bid_px_00", "ask_px_00"])
    df["ts_et"] = pd.to_datetime(df["ts_et"])
    return QuoteBook(df.sample(frac=1.0, random_state=0))   # input order must not matter


def test_last_record_at_or_before_t_and_never_after():
    q = _book()
    assert q(7, T("2024-03-01 15:59")) == (5001.00, 5001.25)
    assert q(7, T("2024-03-01 15:58")) == (5001.00, 5001.25)   # stamped exactly at t counts
    assert q(7, T("2024-03-01 16:00")) == (5009.00, 5009.25)


def test_stale_crossed_one_sided_and_unknown_quotes_are_none():
    q = _book()
    assert q(9, T("2024-03-01 15:57")) == (110.0, 110.015625)  # 5 minutes old: still fresh
    assert q(9, T("2024-03-01 15:58")) is None                 # 6 minutes old
    assert q(8, T("2024-03-01 15:59")) is None
    assert q(6, T("2024-03-01 15:59")) is None
    assert q(5, T("2024-03-01 15:59")) is None
    assert q(7, T("2024-03-01 15:49")) is None                 # nothing yet
    assert _book().state(9, T("2024-03-01 15:58"))[2] == pd.Timedelta(minutes=6)
