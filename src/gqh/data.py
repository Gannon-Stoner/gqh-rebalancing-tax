"""Raw Databento files -> cached derived data (data/derived/, git-ignored).

* ``settlements_ES.parquet``, ``settlements_ZN.parquet``: ``gqh.panel`` settlement panels with the
  contract-selection weight (open interest, or traded volume where none is published; A14).
* ``daily_volume.parquet``: contracts traded per trade date and outright, from ohlcv-1m.
* ``bbo_1m_close.parquet``: bbo-1m records stamped 14:00-16:30 ET (``ts_et`` = ET end of minute).
* ``ohlcv_1m_close.parquet``: ohlcv-1m bars starting 14:00-16:30 ET (``ts_et`` = ET bar start).

Only these windows are kept: they hold the settlement clocks (ZN 15:00, ES 16:00 /
16:15 ET) and the 15:59 ET PX fill minute. The OOS guard of ``gqh.panel`` applies to
the settlement panels; minute data is filtered to the same dates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from gqh.config import frozen_config
from gqh.panel import build_settlement_panel, oos_unlocked

ET = "America/New_York"
WINDOW_MINUTES = (14 * 60, 16 * 60 + 30)
BBO_COLS = ["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]
OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def _dbn(path: Path) -> pd.DataFrame:
    import databento as db

    return db.DBNStore.from_file(str(path)).to_df(map_symbols=False)


def close_window(paths: Iterable[Path], cols: list[str]) -> tuple[pd.DataFrame, dict[str, int], float]:
    """14:00-16:30 ET rows of minute files, plus records per file and the share stamped on a minute."""
    parts, counts, on_minute, total = [], {}, 0, 0
    for path in paths:
        df = _dbn(path)
        counts[Path(path).name] = len(df)
        idx = df.index.tz_convert(ET).tz_localize(None)
        on_minute += int(((idx.second == 0) & (idx.microsecond == 0) & (idx.nanosecond == 0)).sum())
        total += len(df)
        m = idx.hour * 60 + idx.minute
        keep = (m >= WINDOW_MINUTES[0]) & (m <= WINDOW_MINUTES[1])
        part = df.loc[keep, ["instrument_id", *cols]].copy()
        part.insert(0, "ts_et", idx[keep])
        parts.append(part.reset_index(drop=True))
    out = pd.concat(parts, ignore_index=True).sort_values(["ts_et", "instrument_id"], kind="mergesort", ignore_index=True)
    return out, counts, on_minute / max(total, 1)


BBO_GLOBS = ("is_bbo_1m_*.dbn.zst", "oos_bbo_1m_*.dbn.zst", "batch/*/*.bbo-1m.dbn.zst")   # streamed + batch files
OHLCV_GLOBS = ("is_ohlcv_1m_*.dbn.zst", "oos_ohlcv_1m_*.dbn.zst", "batch/*/*.ohlcv-1m.dbn.zst")
STATS_FILES = ("is_statistics", "oos_statistics")      # OOS files exist only after freeze-final (A19)
DEFS_FILES = ("is_definition", "oos_definition")


def _files(raw: Path, globs) -> list[Path]:
    globs = (globs,) if isinstance(globs, str) else tuple(globs)
    return sorted({f for g in globs for f in raw.glob(g)})


def _dbn_all(raw: Path, stems) -> pd.DataFrame:
    """Concatenate the DBN files that exist among ``stems`` (in order)."""
    stems = (stems,) if isinstance(stems, str) else tuple(stems)
    frames = [_dbn(raw / f"{s}.dbn.zst") for s in stems if (raw / f"{s}.dbn.zst").is_file()]
    return frames[0] if len(frames) == 1 else pd.concat(frames)


def build_derived(raw: Path, derived: Path, *, stats=STATS_FILES, defs=DEFS_FILES,
                  bbo_glob=BBO_GLOBS, ohlcv_glob=OHLCV_GLOBS) -> dict:
    """Write the derived parquet files; returns record counts for the audit."""
    derived.mkdir(parents=True, exist_ok=True)
    st, df_ = _dbn_all(raw, stats), _dbn_all(raw, defs)
    info: dict = {}
    last = {}
    vol = daily_volume(_files(raw, ohlcv_glob))
    vol.to_parquet(derived / "daily_volume.parquet", index=False)
    for root in ("ES", "ZN"):
        p = add_selection_weight(build_settlement_panel(st, df_, root), vol)
        p.to_parquet(derived / f"settlements_{root}.parquet", index=False)
        last[root] = p["date"].max()
    limit = None if oos_unlocked() else frozen_config().oos_start
    for name, glob, cols in (("bbo_1m_close", bbo_glob, BBO_COLS), ("ohlcv_1m_close", ohlcv_glob, OHLCV_COLS)):
        frame, counts, on_min = close_window(_files(raw, glob), cols)
        if limit is not None:
            frame = frame[frame["ts_et"] < limit]
        frame.to_parquet(derived / f"{name}.parquet", index=False)
        info[name] = {"files": counts, "share_on_minute": on_min, "rows_kept": int(len(frame))}
    info["last_settlement"] = {k: str(v.date()) for k, v in last.items()}
    return info


def load_derived(derived: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """(settlement panels, bbo extract, ohlcv extract)."""
    panels = {r: pd.read_parquet(derived / f"settlements_{r}.parquet") for r in ("ES", "ZN")}
    return panels, pd.read_parquet(derived / "bbo_1m_close.parquet"), pd.read_parquet(derived / "ohlcv_1m_close.parquet")


def bar_volume(ohlcv: pd.DataFrame) -> dict[int, pd.Series]:
    """ohlcv-1m volume per instrument indexed by ET bar start (a missing bar means no trades)."""
    return {int(i): g.set_index("ts_et")["volume"].astype(float) for i, g in ohlcv.groupby("instrument_id", sort=False)}


def daily_volume(paths: Iterable[Path]) -> pd.DataFrame:
    """Contracts traded per (CME trade date, instrument) from full-day ohlcv-1m files.

    The Globex day runs 18:00 ET to 17:00 ET, so a bar starting at or after 18:00 ET
    belongs to the next trade date: trade date = (ET bar start + 6 hours), normalized.
    Columns ``date, instrument_id, volume_1m``.
    """
    out = pd.concat([daily_volume_from_bars(_dbn(path)) for path in paths], ignore_index=True)
    return out.groupby(["date", "instrument_id"], as_index=False)["volume_1m"].sum()


def daily_volume_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """:func:`daily_volume` for one frame of ohlcv-1m bars indexed by UTC bar start."""
    et = bars.index.tz_convert(ET).tz_localize(None)
    g = pd.DataFrame({"date": (et + pd.Timedelta(hours=6)).normalize(), "instrument_id": bars["instrument_id"].to_numpy(),
                      "volume_1m": bars["volume"].to_numpy(dtype=float)})
    return g.groupby(["date", "instrument_id"], as_index=False)["volume_1m"].sum()


def add_selection_weight(panel: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Add ``volume_1m``, ``selection_weight`` and ``selection_source`` (amendment A14).

    CME open interest is absent from the statistics feed before MDP 3.0 (June 2010 to
    November 2015). On a date where no contract of the root has open interest, the
    contract ranking uses that date's traded volume from ohlcv-1m instead; on every
    other date it uses open interest, as frozen.
    """
    out = panel.merge(volume, on=["date", "instrument_id"], how="left")
    out["volume_1m"] = out["volume_1m"].fillna(0.0)
    has_oi = out.groupby("date")["open_interest"].transform(lambda s: s.notna().any())
    out["selection_weight"] = np.where(has_oi, out["open_interest"], out["volume_1m"])
    out["selection_source"] = np.where(has_oi, "open_interest", "volume_1m")
    return out
