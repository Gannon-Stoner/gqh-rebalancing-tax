"""Shared pytest fixtures. Deterministic: no network, no market data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gqh.calendar import SessionCalendar, xnys_sessions
from gqh.config import FrozenConfig, frozen_config


@pytest.fixture(scope="session")
def cfg() -> FrozenConfig:
    """The pre-registered constants from config/frozen.yaml."""
    return frozen_config()


@pytest.fixture
def rng(cfg: FrozenConfig) -> np.random.Generator:
    """A fresh generator seeded with the frozen seed for each test."""
    return np.random.default_rng(cfg.seed)


@pytest.fixture(scope="session")
def xnys_2009_2028() -> pd.DatetimeIndex:
    """XNYS sessions from 2009-12-01 through 2028-01-31 (covers every month 2010-2027)."""
    return xnys_sessions("2009-12-01", "2028-01-31")


@pytest.fixture(scope="session")
def xnys_cal(xnys_2009_2028: pd.DatetimeIndex) -> SessionCalendar:
    """SessionCalendar on the pure XNYS sessions (no settlement filtering)."""
    return SessionCalendar(xnys_2009_2028)
