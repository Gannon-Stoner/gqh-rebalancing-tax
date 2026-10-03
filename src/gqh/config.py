"""Read-only access to the pre-registered constants in ``config/frozen.yaml``.

The YAML file is committed under the ``prereg-final`` tag and is never written
by this code: ``load_frozen`` parses it into a fresh dict on every call, and
``frozen_config`` exposes the constants the pipeline uses as an immutable
dataclass.

Date conventions: sample boundaries are tz-naive, normalized ``pd.Timestamp``
dates (calendar dates, not instants). ``is_end`` is inclusive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

import pandas as pd
import yaml

FROZEN_RELPATH = Path("config") / "frozen.yaml"

Sample = Literal["PRE", "IS", "OOS"]


def repo_root() -> Path:
    """Return the repository root: the nearest ancestor holding ``config/frozen.yaml``.

    Searches upward from this file first (works for a source checkout and an
    editable install), then from the current working directory.
    """
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for candidate in (start, *start.parents):
            if (candidate / FROZEN_RELPATH).is_file():
                return candidate
    raise FileNotFoundError(
        f"could not locate {FROZEN_RELPATH} above {Path(__file__).resolve()} or {Path.cwd()}"
    )


def default_frozen_path() -> Path:
    """Path of the committed frozen config."""
    return repo_root() / FROZEN_RELPATH


def load_frozen(path: str | Path | None = None) -> dict[str, Any]:
    """Parse the frozen YAML into a new dict (callers may not write it back)."""
    p = Path(path) if path is not None else default_frozen_path()
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{p} did not parse to a mapping")
    return data


def _date(value: Any) -> pd.Timestamp:
    """Tz-naive normalized timestamp for a YAML date string."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        raise ValueError(f"expected a tz-naive date, got {value!r}")
    return ts.normalize()


def _ro(d: dict[str, float]) -> Mapping[str, float]:
    """Read-only mapping so a cached FrozenConfig cannot be altered in place."""
    return MappingProxyType(dict(d))


def _parse_dose_cap(dose_rule: str) -> float:
    """Extract the cap from the frozen dose rule ``"min(|z|, 2), ..."``."""
    m = re.search(r"min\(\s*\|z\|\s*,\s*([0-9]*\.?[0-9]+)\s*\)", dose_rule)
    if m is None:
        raise ValueError(f"cannot find dose cap in {dose_rule!r}")
    return float(m.group(1))


@dataclass(frozen=True)
class FrozenConfig:
    """Immutable view of the pre-registered constants used by the pipeline.

    Attributes
    ----------
    seed : int
        Master RNG seed (bootstrap, synthetic panels).
    is_start, is_end, oos_start : pd.Timestamp
        Sample boundaries; ``is_end`` is inclusive, OOS begins at ``oos_start``.
    oos_unlock_tag : str
        Git tag that must exist before any OOS date is loaded.
    ewma_lambda : float
        EWMA decay for sigma_hat of the daily spread return X.
    kappa : float
        Full-dose ex-ante 5-day risk per event as a fraction of NAV (0.03/sqrt(12)).
    dose_cap : float
        dose = min(|z|, dose_cap).
    target_equity_weight : float
        Equity weight w of the hypothetical calendar rebalancer (0.60).
    progress_scale_sessions, outcome_scale_sessions : int
        Return counts in the progress and holding windows (3 and 5); A and Y are
        scaled by sigma_hat * sqrt(these).
    min_events : int
        Minimum completed events before the gate is fitted.
    reference_nav : float
        Reference NAV in USD for sizing.
    multipliers : Mapping[str, float]
        Contract point value in USD per index point, keyed "ES"/"ZN".
    half_spreads : Mapping[str, float]
        Half-spread cost in USD per contract, keyed "ES"/"ZN".
    fee : float
        Fee in USD per contract per side.
    cost_multipliers : tuple[float, ...]
        Cost scalings reported (1x, 2x).
    variants : tuple[str, ...]
        Strategy row IDs in file order; ``primary`` is the headline row.
    """

    seed: int
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_unlock_tag: str
    ewma_lambda: float
    kappa: float
    dose_cap: float
    target_equity_weight: float
    progress_scale_sessions: int
    outcome_scale_sessions: int
    min_events: int
    reference_nav: float
    multipliers: Mapping[str, float]
    half_spreads: Mapping[str, float]
    fee: float
    cost_multipliers: tuple[float, ...]
    variants: tuple[str, ...]
    primary: str
    n_variants: int

    def sample_of(self, date: Any) -> Sample:
        """Label a date: 'PRE' before is_start, 'IS' through is_end, 'OOS' from oos_start."""
        d = _date(date)
        if d < self.is_start:
            return "PRE"
        if d <= self.is_end:
            return "IS"
        if d >= self.oos_start:
            return "OOS"
        raise ValueError(f"{d.date()} falls between is_end and oos_start")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FrozenConfig":
        """Build from the parsed YAML; raises KeyError if a frozen key is missing."""
        samples = raw["samples"]
        contracts = raw["contracts"]
        cfg = cls(
            seed=int(raw["seed"]),
            is_start=_date(samples["is_start"]),
            is_end=_date(samples["is_end"]),
            oos_start=_date(samples["oos_start"]),
            oos_unlock_tag=str(samples["oos_unlock_tag"]),
            ewma_lambda=float(raw["signal"]["ewma_lambda"]),
            kappa=float(raw["sizing"]["kappa"]),
            dose_cap=_parse_dose_cap(raw["signal"]["dose"]),
            target_equity_weight=float(raw["signal"]["target_equity_weight"]),
            progress_scale_sessions=int(raw["signal"]["progress_scale_sessions"]),
            outcome_scale_sessions=int(raw["signal"]["outcome_scale_sessions"]),
            min_events=int(raw["gate"]["min_events"]),
            reference_nav=float(raw["sizing"]["reference_nav_usd"]),
            multipliers=_ro({k: float(v) for k, v in contracts["multiplier_usd_per_point"].items()}),
            half_spreads=_ro({k: float(v) for k, v in contracts["half_spread_usd_per_contract"].items()}),
            fee=float(contracts["fee_usd_per_contract_per_side"]),
            cost_multipliers=tuple(float(x) for x in raw["costs"]["multipliers_reported"]),
            variants=tuple(raw["variants"].keys()),
            primary=str(raw["primary"]),
            n_variants=int(raw["n_variants"]),
        )
        if not (cfg.is_start <= cfg.is_end < cfg.oos_start):
            raise ValueError("frozen samples must satisfy is_start <= is_end < oos_start")
        if cfg.primary not in cfg.variants or cfg.n_variants != len(cfg.variants):
            raise ValueError("frozen variants, primary and n_variants disagree")
        return cfg


@lru_cache(maxsize=8)
def _frozen_config_cached(path: str) -> FrozenConfig:
    return FrozenConfig.from_dict(load_frozen(path))


def frozen_config(path: str | Path | None = None) -> FrozenConfig:
    """The frozen constants as an immutable ``FrozenConfig`` (cached per path)."""
    p = Path(path) if path is not None else default_frozen_path()
    return _frozen_config_cached(str(p.resolve()))


def sample_of(date: Any, cfg: FrozenConfig | None = None) -> Sample:
    """'PRE' | 'IS' | 'OOS' for a date under the frozen (or given) sample boundaries."""
    return (cfg or frozen_config()).sample_of(date)
