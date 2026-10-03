"""Settlement-panel loader (gqh.panel) on hand-built Databento-shaped frames."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gqh import panel as P

UTC = "UTC"


def _stats(rows: list[dict]) -> pd.DataFrame:
    """Rows: ts_recv (str UTC), iid, ts_ref (date str), stat_type, flags, price, qty, action, seq."""
    df = pd.DataFrame(rows)
    df["ts_recv"] = pd.to_datetime(df["ts_recv"]).dt.tz_localize(UTC)
    df["ts_ref"] = pd.to_datetime(df["ts_ref"]).dt.tz_localize(UTC)
    df = df.rename(columns={"iid": "instrument_id", "flags": "stat_flags", "qty": "quantity",
                            "action": "update_action", "seq": "sequence"})
    df["symbol"] = "mapped"
    return df.set_index("ts_recv")


def _defs() -> pd.DataFrame:
    rows = [
        ("2020-10-01", 1, "ESZ0", "ES", "F", "2020-12-18 14:30", 0.25, 50.0),
        ("2020-10-01", 2, "ESH1", "ES", "F", "2021-03-19 13:30", 0.25, 50.0),
        ("2020-10-01", 3, "ESZ0-ESH1", "ES", "S", "2020-12-18 14:30", 0.05, 50.0),
        ("2020-10-01", 4, "ZNZ0", "ZN", "F", "2020-12-21 18:01", 0.015625, 100000.0),
        ("2020-10-02", 1, "ESZ0", "ES", "F", "2020-12-18 14:30", 0.25, 50.0),   # re-sent definition
    ]
    df = pd.DataFrame(rows, columns=["ts_recv", "instrument_id", "raw_symbol", "asset", "instrument_class",
                                     "expiration", "min_price_increment", "unit_of_measure_qty"])
    df["ts_recv"] = pd.to_datetime(df["ts_recv"]).dt.tz_localize(UTC)
    df["expiration"] = pd.to_datetime(df["expiration"]).dt.tz_localize(UTC)
    df["symbol"] = "mapped"
    return df.set_index("ts_recv")


SETTLE, OI, VOL = P.SETTLEMENT_PRICE, P.OPEN_INTEREST, P.CLEARED_VOLUME


def test_final_settlement_beats_preliminary_and_later_preliminary():
    s = _stats([
        dict(ts_recv="2020-12-16 21:02", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=2, price=3700.80, qty=0, action=1, seq=1),
        dict(ts_recv="2020-12-16 22:46", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=6, price=3700.75, qty=0, action=1, seq=2),
        dict(ts_recv="2020-12-17 00:08", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=7, price=3700.70, qty=0, action=1, seq=3),
        dict(ts_recv="2020-12-17 01:00", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=2, price=3999.00, qty=0, action=1, seq=4),
    ])
    out = P.final_settlements(s)
    assert len(out) == 1 and out.at[0, "settle"] == 3700.70
    assert out.at[0, "date"] == pd.Timestamp("2020-12-16")   # ts_ref not localized to ET (would be 12-15)


def test_without_any_final_flag_the_last_record_is_used_and_intraday_never():
    """Pre-MDP 3.0 records carry no FINAL flag (A14): the last record per key is the settlement."""
    s = _stats([
        dict(ts_recv="2012-12-03 22:20", iid=1, ts_ref="2012-12-03", stat_type=SETTLE, flags=0, price=1.0, qty=0, action=1, seq=1),
        dict(ts_recv="2012-12-04 00:04", iid=1, ts_ref="2012-12-03", stat_type=SETTLE, flags=0, price=1.5, qty=0, action=1, seq=2),
        dict(ts_recv="2020-12-17 15:00", iid=1, ts_ref="2020-12-17", stat_type=SETTLE, flags=1 | 8, price=2.0, qty=0, action=1, seq=3),
        dict(ts_recv="2012-12-04 22:20", iid=2, ts_ref="2012-12-04", stat_type=SETTLE, flags=1, price=7.0, qty=0, action=1, seq=4),
        dict(ts_recv="2012-12-04 23:51", iid=2, ts_ref="2012-12-04", stat_type=SETTLE, flags=0, price=7.25, qty=0, action=1, seq=5),
    ])
    out = P.final_settlements(s).set_index(["instrument_id", "date"])
    assert out.loc[(1, pd.Timestamp("2012-12-03")), "settle"] == 1.5
    assert not out.loc[(1, pd.Timestamp("2012-12-03")), "final_flag"]
    assert (1, pd.Timestamp("2020-12-17")) not in out.index              # intraday only: no settlement
    assert out.loc[(2, pd.Timestamp("2012-12-04")), "settle"] == 7.0      # a flagged final beats later unflagged
    assert out.loc[(2, pd.Timestamp("2012-12-04")), "final_flag"]


def test_zero_placeholder_settlement_is_not_a_settlement():
    s = _stats([
        dict(ts_recv="2020-12-05 00:00", iid=2, ts_ref="2020-12-04", stat_type=SETTLE, flags=3, price=0.0, qty=0, action=1, seq=1),
    ])
    assert P.final_settlements(s).empty


def test_delete_removes_earlier_records_of_its_key_only():
    s = _stats([
        dict(ts_recv="2020-12-17 00:00", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=3, price=10.0, qty=0, action=1, seq=1),
        dict(ts_recv="2020-12-17 00:05", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=3, price=0.0, qty=0, action=2, seq=2),
        dict(ts_recv="2020-12-17 00:10", iid=2, ts_ref="2020-12-16", stat_type=SETTLE, flags=3, price=20.0, qty=0, action=1, seq=3),
        dict(ts_recv="2020-12-18 00:00", iid=1, ts_ref="2020-12-17", stat_type=SETTLE, flags=3, price=11.0, qty=0, action=1, seq=4),
    ])
    out = P.final_settlements(s).set_index(["instrument_id", "date"])["settle"]
    assert (1, pd.Timestamp("2020-12-16")) not in out.index
    assert out[(2, pd.Timestamp("2020-12-16"))] == 20.0 and out[(1, pd.Timestamp("2020-12-17"))] == 11.0


def test_open_interest_and_volume_take_the_last_new_record():
    s = _stats([
        dict(ts_recv="2020-12-17 06:00", iid=1, ts_ref="2020-12-16", stat_type=OI, flags=0, price=None, qty=100, action=1, seq=1),
        dict(ts_recv="2020-12-17 07:00", iid=1, ts_ref="2020-12-16", stat_type=OI, flags=0, price=None, qty=120, action=1, seq=2),
        dict(ts_recv="2020-12-17 06:00", iid=1, ts_ref="2020-12-16", stat_type=VOL, flags=0, price=None, qty=55, action=1, seq=3),
    ])
    assert P.daily_quantity(s, OI, "open_interest").at[0, "open_interest"] == 120
    assert P.daily_quantity(s, VOL, "cleared_volume").at[0, "cleared_volume"] == 55


def test_outright_definitions_keep_root_futures_and_the_exchange_symbol():
    es = P.outright_definitions(_defs(), "ES")
    assert list(es["symbol"]) == ["ESZ0", "ESH1"]                 # spread and ZN excluded, re-send collapsed
    assert es.at[0, "expiration"] == pd.Timestamp("2020-12-18")   # 14:30 UTC -> ET calendar date
    assert list(P.outright_definitions(_defs(), "ZN")["symbol"]) == ["ZNZ0"]


def test_panel_joins_and_masks_out_of_sample(monkeypatch):
    s = _stats([
        dict(ts_recv="2020-12-17 00:00", iid=1, ts_ref="2020-12-16", stat_type=SETTLE, flags=3, price=10.0, qty=0, action=1, seq=1),
        dict(ts_recv="2020-12-17 06:00", iid=1, ts_ref="2020-12-16", stat_type=OI, flags=0, price=None, qty=7, action=1, seq=2),
        dict(ts_recv="2020-12-17 00:00", iid=3, ts_ref="2020-12-16", stat_type=SETTLE, flags=3, price=0.5, qty=0, action=1, seq=3),
        dict(ts_recv="2024-10-03 00:00", iid=1, ts_ref="2024-10-02", stat_type=SETTLE, flags=3, price=12.0, qty=0, action=1, seq=4),
    ])
    monkeypatch.setattr(P, "oos_unlocked", lambda root=None: False)
    out = P.build_settlement_panel(s, _defs(), "ES")
    assert list(out["date"]) == [pd.Timestamp("2020-12-16")]      # spread (iid 3) and OOS date dropped
    assert out.at[0, "open_interest"] == 7 and out.at[0, "symbol"] == "ESZ0"
    with pytest.raises(PermissionError):
        P.build_settlement_panel(s, _defs(), "ES", allow_oos=True)
    monkeypatch.setattr(P, "oos_unlocked", lambda root=None: True)
    assert len(P.build_settlement_panel(s, _defs(), "ES")) == 2


PILOT = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.mark.skipif(not (PILOT / "pilot_statistics.dbn.zst").is_file(), reason="licensed pilot data not present")
def test_pilot_panels_are_well_formed():
    panels = P.load_panels(PILOT / "pilot_statistics.dbn.zst", PILOT / "pilot_definition.dbn.zst")
    for root, df in panels.items():
        assert not df.duplicated(["date", "instrument_id"]).any()
        assert df["symbol"].str.fullmatch(rf"{root}[HMUZ]\d").all()
        assert (df["date"] < pd.Timestamp("2024-10-02")).all()
        front_oi = df.groupby("date")["open_interest"].max()
        assert front_oi.notna().all()                              # every date has OI for some contract
    assert set(panels["ES"]["unit_qty"]) == {50.0} and set(panels["ZN"]["tick"]) == {0.015625}
