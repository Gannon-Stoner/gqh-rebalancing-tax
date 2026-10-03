"""Synthetic data generators for validating the pipeline before any real data.

Everything here is pure and seeded: each function takes an explicit ``seed``
and builds its own ``numpy.random.Generator``; nothing touches the global RNG
or the network. Outputs are *synthetic* and carry no market information.

Conventions
-----------
* Returns are daily **log** returns, one row per session (the session index
  is supplied by the caller, e.g. from ``gqh.calendar``; this module never
  builds a trading calendar itself).
* Leg columns are ``r_es`` and ``r_zn``; the 1:1 spread return is
  ``X = r_es - r_zn`` (HYPOTHESIS.md section 3).
* A holding window "entry -> exit" covers the returns of sessions strictly
  after ``entry`` up to and including ``exit`` (entry exclusive, exit
  inclusive): a position entered at the entry settle earns exactly those
  returns.
* ``seed`` may be an int or anything ``numpy.random.default_rng`` accepts
  (a ``SeedSequence`` or a ``Generator``, which is then used directly).
* Standardized Student-t(nu) draws are scaled by ``sqrt((nu - 2) / nu)`` so
  they have unit variance (requires ``nu > 2``).
"""

from __future__ import annotations


import numpy as np
import pandas as pd
from scipy.signal import lfilter

LEG_COLUMNS = ("r_es", "r_zn")
MONTH_CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
               "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}


def standardized_t(rng: np.random.Generator, nu: float, size) -> np.ndarray:
    """Student-t(nu) draws rescaled to unit variance (nu > 2)."""
    if nu <= 2:
        raise ValueError("nu must exceed 2 for a finite variance")
    return rng.standard_t(nu, size=size) * np.sqrt((nu - 2.0) / nu)


def _garch_filter(sq_shock: np.ndarray, alpha: float, beta: float,
                  omega: float, h0: float) -> np.ndarray:
    """Conditional variances h_t = omega + alpha*e_{t-1}^2 + beta*h_{t-1}.

    ``sq_shock[t]`` must equal z_t**2 for the *standardized* shock of step t;
    the realised squared innovation is e_t**2 = h_t * z_t**2.
    """
    n = len(sq_shock)
    h = np.empty(n)
    h_prev, e2_prev = h0, h0
    for t in range(n):
        h_t = omega + alpha * e2_prev + beta * h_prev
        h[t] = h_t
        e2_prev = h_t * sq_shock[t]
        h_prev = h_t
    return h


def _check_garch(alpha: float, beta: float) -> None:
    if alpha < 0 or beta < 0 or alpha + beta >= 1:
        raise ValueError("need alpha >= 0, beta >= 0 and alpha + beta < 1")


def ar1_garch_t(n: int, *, phi: float = 0.05, alpha: float = 0.08,
                beta: float = 0.90, nu: float = 5, daily_vol: float = 0.011,
                mu: float = 0.0, seed: int, burn: int = 1000) -> np.ndarray:
    """AR(1)-GARCH(1,1)-t returns (the protocol's synthetic null).

    Model::

        r_t = mu + phi * (r_{t-1} - mu) + e_t
        e_t = sqrt(h_t) * z_t,            z_t ~ t(nu) scaled to unit variance
        h_t = omega + alpha * e_{t-1}**2 + beta * h_{t-1}
        omega = daily_vol**2 * (1 - phi**2) * (1 - alpha - beta)

    so E[h_t] = Var(e_t) = daily_vol**2 * (1 - phi**2) and the unconditional
    variance of r_t is exactly ``daily_vol**2``. The recursion starts at the
    unconditional values and the first ``burn`` draws are discarded.

    Note: with the defaults (alpha=0.08, beta=0.90, nu=5) the fourth moment of
    e_t does not exist (beta^2 + 2ab + a^2*kurt(z) > 1), so sample kurtosis is
    large and noisy by design; the variance is finite.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if abs(phi) >= 1:
        raise ValueError("|phi| must be < 1")
    _check_garch(alpha, beta)
    rng = np.random.default_rng(seed)
    total = n + burn
    z = standardized_t(rng, nu, total)
    var_e = daily_vol ** 2 * (1.0 - phi ** 2)
    omega = var_e * (1.0 - alpha - beta)
    h = _garch_filter(z ** 2, alpha, beta, omega, var_e)
    e = np.sqrt(h) * z
    r = np.empty(total)
    prev = mu
    for t in range(total):
        prev = mu + phi * (prev - mu) + e[t]
        r[t] = prev
    return r[burn:]


def _as_index(sessions) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(sessions))
    if not idx.is_monotonic_increasing or idx.has_duplicates:
        raise ValueError("sessions must be strictly increasing")
    return idx.rename("date")


def correlated_leg_returns(sessions, *, vol_es: float = 0.011,
                           vol_zn: float = 0.0040, rho: float = -0.2,
                           seed: int, garch: bool = True, nu: float = 5,
                           alpha: float = 0.08, beta: float = 0.90,
                           phi: float = 0.0, burn: int = 1000) -> pd.DataFrame:
    """Daily log returns for the ES and ZN legs with target vols and correlation.

    Model (zero mean)::

        z_es = t1,  z_zn = rho * t1 + sqrt(1 - rho**2) * t2    (t1, t2 iid
                                                    unit-variance t(nu))
        e_leg,t = vol_leg * sqrt(1 - phi**2) * sqrt(h_t) * z_leg,t
        r_leg,t = phi * r_leg,t-1 + e_leg,t                      (AR(1) per leg)

    ``h_t`` is a *common* volatility state with E[h_t] = 1: with
    ``garch=True`` it follows h_t = (1 - alpha - beta) + alpha * u_{t-1}**2
    + beta * h_{t-1} with u_t**2 = h_t * (z_es**2 + z_zn**2) / 2; with
    ``garch=False`` it is identically 1. Because h_t is independent of the
    current shocks and both legs share ``phi``, Corr(r_es, r_zn) = rho and
    Sd(r_leg) = vol_leg exactly in population for any |phi| < 1 (the
    (1 - phi**2) factor keeps the vols on target), and the spread X = r_es -
    r_zn is AR(1) with coefficient phi too. ``phi`` defaults to 0 (white
    legs, identical to earlier outputs); ``garch=True, nu=5, phi != 0`` is
    the protocol's AR(1)-GARCH(1,1)-t5 null (HYPOTHESIS.md section 3) for the
    end-to-end size check. The first ``burn`` draws are discarded whenever
    ``garch`` is on or ``phi != 0``. Returns a DataFrame indexed by
    ``sessions`` (named ``date``) with columns ``r_es`` and ``r_zn``.
    """
    idx = _as_index(sessions)
    if not -1 < rho < 1:
        raise ValueError("rho must lie in (-1, 1)")
    if abs(phi) >= 1:
        raise ValueError("|phi| must be < 1")
    rng = np.random.default_rng(seed)
    total = len(idx) + (burn if (garch or phi != 0) else 0)
    t1 = standardized_t(rng, nu, total)
    t2 = standardized_t(rng, nu, total)
    z_es = t1
    z_zn = rho * t1 + np.sqrt(1.0 - rho ** 2) * t2
    if garch:
        _check_garch(alpha, beta)
        h = _garch_filter(0.5 * (z_es ** 2 + z_zn ** 2), alpha, beta,
                          1.0 - alpha - beta, 1.0)
    else:
        h = np.ones(total)
    s = np.sqrt(h) * np.sqrt(1.0 - phi ** 2)
    r_es, r_zn = vol_es * s * z_es, vol_zn * s * z_zn
    if phi != 0:
        r_es = lfilter([1.0], [1.0, -phi], r_es)
        r_zn = lfilter([1.0], [1.0, -phi], r_zn)
    out = pd.DataFrame({"r_es": r_es, "r_zn": r_zn})
    out = out.iloc[total - len(idx):].reset_index(drop=True)
    out.index = idx
    return out


_LEG_SPLIT = {"spread": (0.5, -0.5), "es": (1.0, 0.0), "zn": (0.0, -1.0)}


def plant_event_effect(returns_df: pd.DataFrame, events_df: pd.DataFrame,
                       per_event_move, *, entry_col: str = "L_m4",
                       exit_col: str = "F1", leg: str = "spread",
                       es_col: str = "r_es", zn_col: str = "r_zn"
                       ) -> pd.DataFrame:
    """Add a known spread move to each event's holding window.

    For every row of ``events_df`` the amount ``m`` (``per_event_move``: a
    scalar, an array/Series aligned with the rows, or the name of a column of
    ``events_df``) is spread evenly over the returns of sessions strictly
    after ``row[entry_col]`` up to and including ``row[exit_col]``. The split
    between legs is set by ``leg``:

    * ``'spread'``: ES gets +m/2, ZN gets -m/2 (split evenly);
    * ``'es'``: ES gets +m;   ``'zn'``: ZN gets -m.

    In every case the window sum of ``es_col - zn_col`` rises by exactly
    ``m`` and no return outside the window changes. Overlapping windows add
    up. Rows with a missing entry, exit or move are skipped. Returns a new
    DataFrame; the input is not modified.
    """
    if leg not in _LEG_SPLIT:
        raise ValueError(f"leg must be one of {sorted(_LEG_SPLIT)}")
    if isinstance(per_event_move, str):
        moves = events_df[per_event_move].to_numpy(dtype=float)
    else:
        moves = np.broadcast_to(np.asarray(per_event_move, dtype=float),
                                (len(events_df),))
    w_es, w_zn = _LEG_SPLIT[leg]
    out = returns_df.copy()
    idx = out.index
    pos_es = out.columns.get_loc(es_col)
    pos_zn = out.columns.get_loc(zn_col)
    es = out[es_col].to_numpy(dtype=float, copy=True)
    zn = out[zn_col].to_numpy(dtype=float, copy=True)
    entries = pd.to_datetime(events_df[entry_col]).to_numpy()
    exits = pd.to_datetime(events_df[exit_col]).to_numpy()
    for entry, exit_, m in zip(entries, exits, moves):
        if pd.isna(entry) or pd.isna(exit_) or np.isnan(m):
            continue
        i0, i1 = idx.get_loc(entry), idx.get_loc(exit_)
        if i1 <= i0:
            raise ValueError(f"exit {exit_} is not after entry {entry}")
        k = i1 - i0
        es[i0 + 1:i1 + 1] += w_es * m / k
        zn[i0 + 1:i1 + 1] += w_zn * m / k
    out.iloc[:, pos_es] = es
    out.iloc[:, pos_zn] = zn
    return out


def impulse_returns(sessions, date, size: float, leg: str = "es"
                    ) -> pd.DataFrame:
    """All-zero leg returns except one jump of ``size`` on ``date``.

    ``leg`` follows :func:`plant_event_effect`: ``'es'`` puts +size on
    ``r_es``, ``'zn'`` puts -size on ``r_zn`` and ``'spread'`` splits it
    (+size/2, -size/2); in every case the spread return X = r_es - r_zn equals
    ``size`` on ``date`` and 0 elsewhere. Columns ``r_es``, ``r_zn``.
    """
    if leg not in _LEG_SPLIT:
        raise ValueError(f"leg must be one of {sorted(_LEG_SPLIT)}")
    idx = _as_index(sessions)
    out = pd.DataFrame(0.0, index=idx, columns=list(LEG_COLUMNS))
    i = idx.get_loc(pd.Timestamp(date))
    w_es, w_zn = _LEG_SPLIT[leg]
    out.iloc[i, 0] = w_es * size
    out.iloc[i, 1] = w_zn * size
    return out


# --------------------------------------------------------------------------
# Synthetic futures contract chain
# --------------------------------------------------------------------------

_ROOT_DEFAULTS = {
    "ES": {"start_price": 1100.0, "daily_vol": 0.011, "id_base": 1_000_000},
    "ZN": {"start_price": 120.0, "daily_vol": 0.004, "id_base": 2_000_000},
}


def third_friday(year: int, month: int) -> pd.Timestamp:
    """Calendar third Friday of ``year``-``month``."""
    first = pd.Timestamp(year, month, 1)
    return first + pd.Timedelta(days=(4 - first.weekday()) % 7 + 14)


def _session_at(days: pd.DatetimeIndex, pos: int, what: str) -> pd.Timestamp:
    """``days[pos]`` for a non-negative in-range ``pos``; ValueError otherwise
    (a negative position would silently wrap to the end of ``days``)."""
    if not 0 <= pos < len(days):
        raise ValueError(f"supplied days do not cover the lookback for {what}")
    return days[pos]


def _month_days(days: pd.DatetimeIndex, year: int, month: int) -> pd.DatetimeIndex:
    in_month = days[(days.year == year) & (days.month == month)]
    if len(in_month) == 0:
        raise ValueError(f"supplied days contain no session in {year:04d}-{month:02d}")
    return in_month


def es_expiration(year: int, month: int, days: pd.DatetimeIndex) -> pd.Timestamp:
    """ES expiration: the third Friday, or the prior session if it is not one.

    ``days`` must span the third Friday (ValueError otherwise)."""
    tf = third_friday(year, month)
    if len(days) == 0 or tf > days[-1]:
        raise ValueError(f"supplied days end before {tf.date()} (ES {year}-{month:02d})")
    return _session_at(days, int(days.searchsorted(tf, side="right")) - 1,
                       f"ES {year}-{month:02d}")


def zn_expiration(year: int, month: int, days: pd.DatetimeIndex) -> pd.Timestamp:
    """ZN last trading day, approximated as the 7th session before the last
    session of the contract month (CME: seventh business day preceding the
    last business day of the delivery month; sessions stand in for business
    days). ValueError if ``days`` lacks the month or the 7 sessions before it."""
    in_month = _month_days(days, year, month)
    return _session_at(days, days.get_loc(in_month[-1]) - 7,
                       f"ZN {year}-{month:02d} last trading day")


def zn_first_position_day(year: int, month: int,
                          days: pd.DatetimeIndex) -> pd.Timestamp:
    """ZN first position day, approximated as the 2nd session before the
    first session of the contract month (CME: second business day preceding
    the first business day of the delivery month). ValueError if ``days``
    lacks the month or the 2 sessions before it."""
    in_month = _month_days(days, year, month)
    return _session_at(days, days.get_loc(in_month[0]) - 2,
                       f"ZN {year}-{month:02d} first position day")


def _padded_days(idx: pd.DatetimeIndex, years_before: int = 2,
                 years_after: int = 4) -> pd.DatetimeIndex:
    """The supplied sessions, padded with weekdays outside their range."""
    before = pd.bdate_range(idx[0] - pd.DateOffset(years=years_before),
                            idx[0] - pd.Timedelta(days=1))
    after = pd.bdate_range(idx[-1] + pd.Timedelta(days=1),
                           idx[-1] + pd.DateOffset(years=years_after))
    return before.append(idx).append(after).rename("date")


def synthetic_contract_chain(sessions, *, root: str, months: str = "HMUZ",
                             multiplier: float, basis_jump: float = 0.05,
                             seed: int, daily_vol: float | None = None,
                             start_price: float | None = None,
                             n_listed: int = 3, roll_sessions: int = 8,
                             roll_end_lead: int = 2,
                             total_oi: int = 1_000_000,
                             basis_noise: float | None = None) -> pd.DataFrame:
    """Overlapping quarterly futures with a carry basis and an OI roll.

    Returns a long DataFrame with one row per (session, listed contract) and
    columns ``date, instrument_id, symbol, expiration, settle,
    open_interest, first_position_day, multiplier``, sorted by date then
    expiration.

    Prices. A common log "spot" path s_t (AR(1)-GARCH-t with phi=0 and
    ``daily_vol``; s = 0 on the first session) drives every contract::

        log(settle_k,t / start_price) = s_t + basis_jump * n_k,t / g_k + b_k,t

    where n_k,t is the number of sessions from t to contract k's expiration,
    g_k the number of sessions between the previous contract's expiration
    and contract k's, and b_k,t an iid N(0, ``basis_noise``**2) stochastic
    basis drawn separately per (contract, session) from its own seeded
    stream (default ``basis_noise = 0.1 * daily_vol``; 0 gives one purely
    common path, as before). The noise makes the wrong contract give a
    measurably different window return (the window-return difference
    between two contracts has sd 2 * basis_noise) without accumulating.
    Within a contract the daily log return is ds_t - basis_jump / g_k +
    (b_k,t - b_k,t-1). The basis converges to zero at expiry, so the next
    contract trades about ``basis_jump`` (in log) above the expiring one and
    a naively spliced front series jumps by about ``basis_jump`` at each
    roll (basis_jump * (1 + n * (1/g_next - 1/g_front)) plus the noise
    difference, when rolled n sessions before the front expires).

    Listing. On each session the ``n_listed`` nearest contracts whose
    expiration is on or after that session are listed; a contract trades on
    its expiration day and disappears after it.

    Open interest (deterministic). The roll anchor is the front contract's
    expiration for ES and its first position day for ZN (real ZN OI leaves
    the delivery month before FPD, in the last week of Feb/May/Aug/Nov,
    which is why the protocol picks ZN by FPD). With n = sessions to the
    front contract's anchor, the migrated fraction is w = clip((roll_sessions
    + roll_end_lead - n) / roll_sessions, 0, 1), so OI moves from front to
    next over ``roll_sessions`` sessions and finishes ``roll_end_lead``
    sessions before the anchor. front = T(1 - w) + 0.01Tw, next = Tw +
    0.05T(1 - w), deferred j >= 2 = 0.05T / 2**(j - 1), with T = ``total_oi``.
    With the defaults the highest-OI contract switches 6 sessions before the
    anchor: for ES 6 sessions before expiry, for ZN about L-7 of the month
    before delivery, inside that month's (L-8, F1] event window, where the
    highest-OI contract at L-8 differs from the protocol's FPD-rule contract.

    Expirations. ES: third Friday of the contract month, moved to the prior
    session when it is not a session. ZN: :func:`zn_expiration`, with
    ``first_position_day`` from :func:`zn_first_position_day` (NaT for other
    roots). Dates outside the supplied sessions use weekdays as sessions.

    Identifiers. ``instrument_id = base + 100 * year + month`` (base 1e6 for
    ES, 2e6 for ZN). ``symbol`` uses the exchange's one-digit year
    (``ESH0``), which is ambiguous across decades exactly as in the real
    feed, so downstream code must key on ``instrument_id``.
    """
    root = root.upper()
    if root not in _ROOT_DEFAULTS:
        raise ValueError(f"root must be one of {sorted(_ROOT_DEFAULTS)}")
    defaults = _ROOT_DEFAULTS[root]
    vol = defaults["daily_vol"] if daily_vol is None else daily_vol
    noise_sd = 0.1 * vol if basis_noise is None else float(basis_noise)
    if noise_sd < 0:
        raise ValueError("basis_noise must be >= 0")
    p0 = defaults["start_price"] if start_price is None else start_price
    idx = _as_index(sessions)
    days = _padded_days(idx)
    month_nums = sorted(MONTH_CODES[ch] for ch in months)
    code_of = {v: k for k, v in MONTH_CODES.items()}

    contracts = []
    for year in range(idx[0].year - 1, idx[-1].year + 3):
        for m in month_nums:
            if root == "ES":
                exp, fpd = es_expiration(year, m, days), pd.NaT
            else:
                exp = zn_expiration(year, m, days)
                fpd = zn_first_position_day(year, m, days)
            contracts.append({
                "instrument_id": defaults["id_base"] + 100 * year + m,
                "symbol": f"{root}{code_of[m]}{year % 10}",
                "expiration": exp, "first_position_day": fpd})
    contracts.sort(key=lambda c: c["expiration"])
    exp_idx = pd.DatetimeIndex([c["expiration"] for c in contracts])
    exp_pos = days.get_indexer(exp_idx)
    anchor_col = "expiration" if root == "ES" else "first_position_day"
    anchor_pos = days.get_indexer(pd.DatetimeIndex([c[anchor_col] for c in contracts]))
    gap = np.diff(exp_pos, prepend=exp_pos[0] - round(252 / len(month_nums)))
    day_pos = days.get_indexer(idx)

    r = ar1_garch_t(len(idx), phi=0.0, daily_vol=vol, seed=seed)
    s = np.cumsum(r) - r[0]
    # Own stream for the per-contract basis, so the common path is unchanged.
    noise = noise_sd * np.random.default_rng([seed, 1]).standard_normal(
        (len(contracts), len(idx)))

    rows = []
    for i, t in enumerate(idx):
        j0 = int(exp_idx.searchsorted(t, side="left"))
        n_front = anchor_pos[j0] - day_pos[i]
        w = min(max((roll_sessions + roll_end_lead - n_front)
                    / roll_sessions, 0.0), 1.0)
        for rank in range(n_listed):
            c = contracts[j0 + rank]
            n_k = exp_pos[j0 + rank] - day_pos[i]
            if rank == 0:
                oi = total_oi * (1 - w) + 0.01 * total_oi * w
            elif rank == 1:
                oi = total_oi * w + 0.05 * total_oi * (1 - w)
            else:
                oi = 0.05 * total_oi / 2 ** (rank - 1)
            rows.append({
                "date": t, "instrument_id": c["instrument_id"],
                "symbol": c["symbol"], "expiration": c["expiration"],
                "settle": p0 * np.exp(s[i] + basis_jump * n_k / gap[j0 + rank]
                                      + noise[j0 + rank, i]),
                "open_interest": int(round(oi)),
                "first_position_day": c["first_position_day"],
                "multiplier": float(multiplier)})
    out = pd.DataFrame(rows)
    out["first_position_day"] = pd.to_datetime(out["first_position_day"])
    return out.sort_values(["date", "expiration"], ignore_index=True)


# --------------------------------------------------------------------------
# Per-event panels for H1/H2 size and power calibration
# --------------------------------------------------------------------------

def planted_event_panel(n_months: int, *, b: float, c: float,
                        sigma: float = 1.0, seed: int, ar: float = 0.0,
                        a: float = 0.0, gamma: float = 0.0,
                        a_pseudo: float = 0.0, b_pseudo: float | None = None,
                        c_pseudo: float = 0.0, hetero: float = 0.0,
                        nu: float = 5, start: str = "2010-06") -> pd.DataFrame:
    """Stacked synthetic (dose, A, Y) panel: one event and one pseudo-event
    per month, with known coefficients.

    Columns ``month`` (pandas Period, the bootstrap unit), ``ME`` (1 = event,
    0 = pseudo-event), ``QE`` (1 in Mar/Jun/Sep/Dec), ``dose``, ``A``, ``Y``;
    ``2 * n_months`` rows sorted by month then ME. Draws::

        dose = min(|z|, 2), z ~ N(0, 1);   A ~ N(0, 1), independent of dose
        event  (ME=1): Y = a + b*dose + gamma*QE + c*A + eps
        pseudo (ME=0): Y = a_pseudo + b_pseudo*dose + c_pseudo*A + eps

    ``b_pseudo`` defaults to ``b``. So in the stacked H2 regression the true
    interaction is c_E = c - c_pseudo (and a_E = a - a_pseudo, b_E = b -
    b_pseudo). Noise: eps = sigma * (1 + hetero * dose) * u, where in each
    series separately u_t = ar * u_{t-1} + sqrt(1 - ar**2) * eta_t over
    months, eta unit-variance t(nu), so Var(u) = 1 for any |ar| < 1.
    """
    if abs(ar) >= 1:
        raise ValueError("|ar| must be < 1")
    rng = np.random.default_rng(seed)
    b_ps = b if b_pseudo is None else b_pseudo
    months = pd.period_range(start, periods=n_months, freq="M")
    qe = np.isin(months.month, (3, 6, 9, 12)).astype(int)
    frames = []
    for me, (a_, b_, c_, g_) in ((1, (a, b, c, gamma)),
                                 (0, (a_pseudo, b_ps, c_pseudo, 0.0))):
        dose = np.minimum(np.abs(rng.standard_normal(n_months)), 2.0)
        progress = rng.standard_normal(n_months)
        eta = standardized_t(rng, nu, n_months)
        u = np.empty(n_months)
        u[0] = eta[0]
        for t in range(1, n_months):
            u[t] = ar * u[t - 1] + np.sqrt(1.0 - ar ** 2) * eta[t]
        eps = sigma * (1.0 + hetero * dose) * u
        y = a_ + b_ * dose + g_ * qe + c_ * progress + eps
        frames.append(pd.DataFrame({"month": months, "ME": me, "QE": qe,
                                    "dose": dose, "A": progress, "Y": y}))
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["month", "ME"], ignore_index=True)


# Amendment A4: synthetic null specifications for the size/power checks, fixed
# before any market data was loaded. Daily ES/ZN legs from these settings are run
# through the real schedule and signal code; the H2 null additionally plants the
# same ordinary-reversal slope at month-end and pseudo-events (c_E = 0).
PROTOCOL_NULLS: dict[str, dict] = {
    "base": {"phi": 0.05, "alpha": 0.08, "beta": 0.90, "nu": 5, "rho": -0.2,
             "vol_es": 0.011, "vol_zn": 0.0040, "garch": True},
    "stress_corr": {"phi": 0.05, "alpha": 0.08, "beta": 0.90, "nu": 5, "rho": 0.3,
                    "vol_es": 0.011, "vol_zn": 0.0040, "garch": True},
}
H2_REVERSAL_NULL: dict[str, float] = {"c": -0.10, "c_pseudo": -0.10, "c_E": 0.0}


def protocol_null_legs(sessions, name: str = "base", *, seed) -> pd.DataFrame:
    """Daily ES/ZN log returns under a registered synthetic null (A4)."""
    spec = PROTOCOL_NULLS[name]
    return correlated_leg_returns(sessions, seed=seed, **spec)
