"""Frozen-config loader: values, types, sample labels, and read-only behaviour."""

from __future__ import annotations

import hashlib
import math

import pandas as pd
import pytest

from gqh.config import FrozenConfig, default_frozen_path, frozen_config, load_frozen, sample_of


def test_kappa_matches_formula(cfg: FrozenConfig) -> None:
    assert abs(cfg.kappa - 0.03 / math.sqrt(12)) < 1e-6


def test_variants(cfg: FrozenConfig) -> None:
    assert cfg.n_variants == 6
    assert cfg.primary == "PG"
    assert cfg.variants == ("PG", "P0", "PD", "PE", "PX", "PP")


def test_dates_parse(cfg: FrozenConfig) -> None:
    assert cfg.is_start == pd.Timestamp("2010-06-07")
    assert cfg.is_end == pd.Timestamp("2024-10-01")
    assert cfg.oos_start == pd.Timestamp("2024-10-02")
    for d in (cfg.is_start, cfg.is_end, cfg.oos_start):
        assert isinstance(d, pd.Timestamp) and d.tzinfo is None and d == d.normalize()
    assert cfg.oos_unlock_tag == "freeze-final"


def test_scalar_constants(cfg: FrozenConfig) -> None:
    assert cfg.seed == 20261003
    assert cfg.ewma_lambda == 0.94
    assert cfg.dose_cap == 2.0
    assert cfg.min_events == 60
    assert cfg.reference_nav == 10_000_000
    assert dict(cfg.multipliers) == {"ES": 50.0, "ZN": 1000.0}
    assert dict(cfg.half_spreads) == {"ES": 6.25, "ZN": 7.8125}
    assert cfg.fee == 2.50
    assert cfg.cost_multipliers == (1.0, 2.0)


def test_half_spreads_are_one_tick(cfg: FrozenConfig) -> None:
    # Half-spread = half of one minimum tick: ES 0.25 pt x $50 = $12.50; ZN 1/64 pt x $1000 = $15.625.
    assert cfg.half_spreads["ES"] == 0.25 * cfg.multipliers["ES"] / 2
    assert cfg.half_spreads["ZN"] == cfg.multipliers["ZN"] / 64 / 2


@pytest.mark.parametrize(
    "date, label",
    [
        ("2010-06-04", "PRE"),
        ("2010-06-07", "IS"),
        ("2024-10-01", "IS"),
        ("2024-10-02", "OOS"),
        ("2026-01-02", "OOS"),
    ],
)
def test_sample_of(cfg: FrozenConfig, date: str, label: str) -> None:
    assert cfg.sample_of(date) == label
    assert sample_of(pd.Timestamp(date)) == label


def test_sample_of_rejects_tz_aware(cfg: FrozenConfig) -> None:
    with pytest.raises(ValueError):
        cfg.sample_of(pd.Timestamp("2015-01-02", tz="America/New_York"))


def test_config_is_immutable(cfg: FrozenConfig) -> None:
    with pytest.raises(AttributeError):
        cfg.kappa = 1.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        cfg.multipliers["ES"] = 1.0  # type: ignore[index]


def test_load_frozen_returns_fresh_dict_and_never_writes() -> None:
    path = default_frozen_path()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    a = load_frozen()
    a["seed"] = -1
    b = load_frozen(path)
    assert b["seed"] == 20261003
    assert b["protocol"] == "prereg-final"
    assert frozen_config().seed == 20261003
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_from_dict_rejects_inconsistent_variants() -> None:
    raw = load_frozen()
    raw["n_variants"] = 5
    with pytest.raises(ValueError):
        FrozenConfig.from_dict(raw)
