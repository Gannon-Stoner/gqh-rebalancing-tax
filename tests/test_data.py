"""Derived-data helpers (gqh.data): trade-date volume and the contract-selection weight (A14)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from gqh import data as D
from gqh.contracts import ContractPanel


def test_bars_after_18_et_belong_to_the_next_trade_date():
    # EST (UTC-5) until the DST switch on Sunday 2012-03-11, EDT (UTC-4) from then on
    idx = pd.DatetimeIndex(["2012-03-08 22:59", "2012-03-08 23:00", "2012-03-09 21:59", "2012-03-11 22:00"], tz="UTC")
    bars = pd.DataFrame({"instrument_id": [1, 1, 1, 1], "volume": [5, 7, 11, 13]}, index=idx)
    out = D.daily_volume_from_bars(bars).set_index("date")["volume_1m"]
    # 17:59 ET Thu -> Thu; 18:00 ET Thu -> Fri; 16:59 ET Fri -> Fri; Sunday 18:00 ET -> Monday
    assert out.to_dict() == {pd.Timestamp("2012-03-08"): 5, pd.Timestamp("2012-03-09"): 18, pd.Timestamp("2012-03-12"): 13}


def _panel():
    d1, d2 = pd.Timestamp("2012-03-08"), pd.Timestamp("2016-03-08")
    rows = [(d1, 1, 100.0, np.nan), (d1, 2, 99.0, np.nan), (d2, 1, 100.0, 50.0), (d2, 2, 99.0, 900.0)]
    p = pd.DataFrame(rows, columns=["date", "instrument_id", "settle", "open_interest"])
    p["symbol"] = p["instrument_id"].map({1: "ESH2", 2: "ESM2"})
    p["expiration"] = p["instrument_id"].map({1: pd.Timestamp("2022-03-18"), 2: pd.Timestamp("2022-06-17")})
    vol = pd.DataFrame({"date": [d1, d1, d2], "instrument_id": [1, 2, 1], "volume_1m": [300.0, 2_000.0, 10_000.0]})
    return D.add_selection_weight(p, vol), d1, d2


def test_volume_ranks_contracts_only_on_dates_without_open_interest():
    p, d1, d2 = _panel()
    w = p.set_index(["date", "instrument_id"])
    assert w.loc[(d1, 2), "selection_weight"] == 2_000 and w.loc[(d1, 2), "selection_source"] == "volume_1m"
    assert w.loc[(d2, 1), "selection_weight"] == 50 and w.loc[(d2, 2), "selection_source"] == "open_interest"
    es = ContractPanel.from_long(p, "ES")
    assert es.max_oi(d1) == 2 and es.max_oi(d2) == 2           # volume picks ESM2 on d1; OI picks it on d2
    assert w.loc[(d2, 2), "volume_1m"] == 0.0                  # no bars that day: zero volume, not missing
