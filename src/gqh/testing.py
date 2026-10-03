"""Reusable assertion helpers for look-ahead, P&L-window and size checks.

These are plain functions that raise ``AssertionError`` with a specific
message, so they work inside pytest and in ad-hoc validation scripts alike.
Randomness is always derived from an explicit seed.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist


def _keys(frame: pd.DataFrame | pd.Series, key: str | None) -> pd.Index:
    return frame.index if key is None else pd.Index(frame[key])


def _rows_upto(frame, key: str | None, cut):
    """Rows of ``frame`` whose key is <= ``cut``, with a fresh positional index
    when the key is a column."""
    out = frame[_keys(frame, key) <= cut]
    return out if key is None else out.reset_index(drop=True)


def assert_truncation_invariant(fn: Callable, data, cut_points, key: str | None = None,
                                *, rtol: float = 1e-12, atol: float = 1e-12) -> None:
    """Assert ``fn`` uses no information after each row's own key (no look-ahead).

    For every ``cut`` in ``cut_points``: ``fn(data restricted to key <= cut)``
    must reproduce, for the rows with key <= cut, exactly the rows that
    ``fn(data)`` produces for key <= cut (same keys, same values within
    ``rtol``/``atol``, NaNs in the same places). ``key`` names a column present
    in both the input and the output; ``None`` means the (sorted) index. ``fn``
    may return a DataFrame or a Series.
    """
    full = fn(data)
    for cut in cut_points:
        part = fn(_rows_upto(data, key, cut))
        want, got = _rows_upto(full, key, cut), _rows_upto(part, key, cut)
        if isinstance(want, pd.Series):
            want, got = want.to_frame(), got.to_frame()
        try:
            pd.testing.assert_frame_equal(got, want, rtol=rtol, atol=atol,
                                          check_exact=False)
        except AssertionError as err:
            raise AssertionError(
                f"output at or before cut {cut!r} changes when later data is "
                f"removed (look-ahead): {err}") from None


def assert_pnl_only_in_window(pnl_series: pd.Series, window_start_exclusive,
                              window_end_inclusive, atol: float = 1e-12) -> None:
    """Assert P&L is zero (|pnl| <= atol) outside the holding window(s).

    The window is (start, end]: a position entered at the start settle earns
    the returns of later sessions up to and including the exit settle. Pass
    scalars for one window or equal-length sequences for several (the union
    is allowed). NaN P&L counts as zero (no position).

    One-sided: it cannot see a MISSING in-window return (early exit, late
    entry, all-zero P&L). Pair it with :func:`assert_pnl_matches_window`.
    """
    starts = np.atleast_1d(pd.to_datetime(window_start_exclusive))
    ends = np.atleast_1d(pd.to_datetime(window_end_inclusive))
    if len(starts) != len(ends):
        raise ValueError("need as many window starts as ends")
    idx = pd.DatetimeIndex(pnl_series.index)
    inside = np.zeros(len(idx), dtype=bool)
    for lo, hi in zip(starts, ends):
        inside |= (idx > lo) & (idx <= hi)
    values = np.nan_to_num(pnl_series.to_numpy(dtype=float), nan=0.0)
    bad = ~inside & (np.abs(values) > atol)
    if bad.any():
        dates = list(idx[bad][:5].strftime("%Y-%m-%d"))
        raise AssertionError(f"{int(bad.sum())} sessions carry P&L outside the "
                             f"window(s), first: {dates}")


def assert_pnl_matches_window(pnl_series: pd.Series, returns: pd.Series,
                              window_start_exclusive, window_end_inclusive,
                              position=1.0, atol: float = 1e-12) -> None:
    """Assert P&L equals position * return inside each window and 0 outside.

    Two-sided complement to :func:`assert_pnl_only_in_window`, which cannot see
    a missing in-window return: exiting one session early (dropping the F1
    month-turn return), entering one session late, a sign flip or an all-zero
    P&L all fail here. Windows are (start, end] as there; pass scalars for one
    window or equal-length sequences for several, with ``position`` a scalar or
    one value per window (overlapping windows add). ``pnl_series`` and
    ``returns`` (the per-session return the position earns, e.g. X = r_es -
    r_zn) must share the same index. NaN P&L counts as zero (no position).
    """
    starts = np.atleast_1d(pd.to_datetime(window_start_exclusive))
    ends = np.atleast_1d(pd.to_datetime(window_end_inclusive))
    if len(starts) != len(ends):
        raise ValueError("need as many window starts as ends")
    pos = np.broadcast_to(np.asarray(position, dtype=float), (len(starts),))
    if not pnl_series.index.equals(returns.index):
        raise ValueError("pnl_series and returns must share the same index")
    idx = pd.DatetimeIndex(pnl_series.index)
    ret = returns.to_numpy(dtype=float)
    expected = np.zeros(len(idx))
    for lo, hi, p in zip(starts, ends, pos):
        expected += np.where((idx > lo) & (idx <= hi), p * ret, 0.0)
    got = np.nan_to_num(pnl_series.to_numpy(dtype=float), nan=0.0)
    bad = np.abs(got - expected) > atol
    if bad.any():
        first = idx[bad][:5].strftime("%Y-%m-%d").tolist()
        raise AssertionError(f"{int(bad.sum())} sessions where P&L != position * "
                             f"return in-window (or != 0 outside), first: {first}")


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Exact (Clopper-Pearson) two-sided CI for a binomial proportion k/n."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError("need n > 0 and 0 <= k <= n")
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(beta_dist.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(beta_dist.ppf(1.0 - tail, k + 1, n - k))
    return lo, hi


def rejection_rate(test_fn: Callable, generator_fn: Callable, n_panels: int,
                   alpha: float, seed: int, *, pass_rng: bool = False,
                   level: float = 0.95) -> tuple[float, tuple[float, float]]:
    """Monte Carlo rejection rate of a test, with an exact binomial CI.

    Panel i is ``generator_fn(rng_i)`` and its p-value is ``test_fn(panel)``
    (or ``test_fn(panel, rng_test_i)`` with ``pass_rng=True``, for tests that
    draw their own bootstrap samples). A panel rejects when p <= alpha. The
    generators come from ``np.random.SeedSequence(seed).spawn``, so the result
    is reproducible per seed and panel i does not depend on ``n_panels``.
    Returns ``(rate, (lo, hi))`` with a Clopper-Pearson CI at ``level``.
    """
    if n_panels <= 0:
        raise ValueError("n_panels must be positive")
    children = np.random.SeedSequence(seed).spawn(n_panels)
    rejections = 0
    for child in children:
        gen_seq, test_seq = child.spawn(2)
        panel = generator_fn(np.random.default_rng(gen_seq))
        if pass_rng:
            p = test_fn(panel, np.random.default_rng(test_seq))
        else:
            p = test_fn(panel)
        if not np.isfinite(p):
            raise AssertionError(f"test_fn returned a non-finite p-value: {p}")
        rejections += bool(p <= alpha)
    return rejections / n_panels, clopper_pearson(rejections, n_panels, level)


def assert_size_ok(rate_ci, alpha: float,
                   band: tuple[float, float] = (0.03, 0.07)) -> None:
    """Assert an estimated size is acceptable for a nominal ``alpha`` test.

    ``rate_ci`` is the ``(rate, (lo, hi))`` pair from :func:`rejection_rate`.
    Passes iff the point rate lies inside ``band`` (inclusive; the frozen
    ``size_check_band``). The CI is reported in the failure message.
    """
    rate, (lo, hi) = rate_ci
    b_lo, b_hi = band
    if not b_lo <= alpha <= b_hi:
        raise ValueError(f"band {band} does not contain alpha={alpha}")
    if not b_lo <= rate <= b_hi:
        raise AssertionError(
            f"rejection rate {rate:.4f} (CI [{lo:.4f}, {hi:.4f}]) at nominal "
            f"alpha={alpha} is outside the size band [{b_lo}, {b_hi}]")
