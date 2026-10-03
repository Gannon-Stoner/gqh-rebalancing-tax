"""Tests for gqh.synth: every generator is checked against the property it
promises. All draws are seeded, so every assertion is deterministic."""

import numpy as np
import pandas as pd
import pytest

from gqh import synth

LONG = pd.bdate_range("1900-01-01", "2099-12-31")  # ~52k sessions


def acf1(x):
    x = np.asarray(x) - np.mean(x)
    return float(np.dot(x[1:], x[:-1]) / np.dot(x, x))


# ---------------------------------------------------------------- AR-GARCH-t

def test_ar1_garch_t_moments_on_long_sample():
    r = synth.ar1_garch_t(200_000, daily_vol=0.011, seed=11)
    assert r.shape == (200_000,)
    assert abs(r.std() / 0.011 - 1) < 0.10
    assert pd.Series(r).kurt() > 0          # fat tails (excess kurtosis)
    assert acf1(r ** 2) > 0.05              # volatility clustering


def test_ar1_garch_t_ar_coefficient_and_mean():
    r = synth.ar1_garch_t(200_000, phi=0.3, mu=0.001, daily_vol=0.01, seed=5)
    assert abs(acf1(r) - 0.3) < 0.03
    assert abs(r.mean() - 0.001) < 3e-4
    assert abs(r.std() / 0.01 - 1) < 0.10


def test_ar1_garch_t_seed_reproducible_and_seeds_differ():
    a = synth.ar1_garch_t(500, seed=1)
    np.testing.assert_array_equal(a, synth.ar1_garch_t(500, seed=1))
    assert not np.allclose(a, synth.ar1_garch_t(500, seed=2))


def test_ar1_garch_t_rejects_bad_parameters():
    with pytest.raises(ValueError):
        synth.ar1_garch_t(10, alpha=0.2, beta=0.85, seed=0)
    with pytest.raises(ValueError):
        synth.ar1_garch_t(10, nu=2, seed=0)
    with pytest.raises(ValueError):
        synth.ar1_garch_t(10, phi=1.0, seed=0)


# ----------------------------------------------------------- leg returns

@pytest.mark.parametrize("garch", [True, False])
def test_correlated_leg_returns_hit_vol_and_correlation(garch):
    df = synth.correlated_leg_returns(LONG, vol_es=0.011, vol_zn=0.004,
                                      rho=-0.2, seed=3, garch=garch)
    assert list(df.columns) == ["r_es", "r_zn"]
    assert df.index.equals(LONG) and df.index.name == "date"
    assert abs(df["r_es"].std() / 0.011 - 1) < 0.10
    assert abs(df["r_zn"].std() / 0.004 - 1) < 0.10
    assert abs(df.corr().iloc[0, 1] - (-0.2)) < 0.05
    if garch:
        assert acf1(df["r_es"] ** 2) > 0.05
        assert acf1(df["r_zn"] ** 2) > 0.05


def test_correlated_leg_returns_reproducible_by_seed():
    idx = LONG[:300]
    a = synth.correlated_leg_returns(idx, seed=7)
    pd.testing.assert_frame_equal(a, synth.correlated_leg_returns(idx, seed=7))
    assert not np.allclose(a, synth.correlated_leg_returns(idx, seed=8))


# ----------------------------------------------------------- planting

IDX = pd.bdate_range("2020-01-01", periods=60)


def _events():
    return pd.DataFrame({"entry": [IDX[5], IDX[20], IDX[22], pd.NaT],
                         "exit": [IDX[10], IDX[25], IDX[27], IDX[40]],
                         "move": [0.03, -0.02, 0.01, 0.5]})


@pytest.mark.parametrize("leg", ["spread", "es", "zn"])
def test_plant_event_effect_moves_only_window_by_exact_amount(leg):
    base = synth.correlated_leg_returns(IDX, seed=1)
    ev = _events()
    out = synth.plant_event_effect(base, ev, "move", entry_col="entry",
                                   exit_col="exit", leg=leg)
    d_spread = (out.r_es - out.r_zn) - (base.r_es - base.r_zn)
    inside = np.zeros(len(IDX), dtype=bool)
    for i0, i1 in [(5, 10), (20, 25), (22, 27)]:      # NaT row is skipped
        inside[i0 + 1:i1 + 1] = True
    assert np.all(d_spread[~inside] == 0)
    assert np.all((out - base)[~inside].to_numpy() == 0)
    assert d_spread.iloc[6:11].sum() == pytest.approx(0.03, abs=1e-15)
    np.testing.assert_allclose(d_spread.iloc[6:11], 0.03 / 5, atol=1e-15)
    # overlapping windows add: (20, 25] and (22, 27]
    assert d_spread.iloc[21:28].sum() == pytest.approx(-0.01, abs=1e-15)
    np.testing.assert_allclose(d_spread.iloc[23:26], (-0.02 + 0.01) / 5,
                               atol=1e-15)
    d_es, d_zn = out.r_es - base.r_es, out.r_zn - base.r_zn
    if leg == "es":
        assert np.all(d_zn == 0)
    elif leg == "zn":
        assert np.all(d_es == 0)
    else:
        np.testing.assert_allclose(d_es, -d_zn, atol=1e-16)
    pd.testing.assert_frame_equal(base, synth.correlated_leg_returns(IDX, seed=1))


def test_plant_event_effect_scalar_and_array_moves():
    base = pd.DataFrame(0.0, index=IDX, columns=["r_es", "r_zn"])
    ev = _events().iloc[:2]
    a = synth.plant_event_effect(base, ev, 0.04, entry_col="entry", exit_col="exit")
    b = synth.plant_event_effect(base, ev, np.array([0.04, 0.04]),
                                 entry_col="entry", exit_col="exit")
    pd.testing.assert_frame_equal(a, b)
    assert (a.r_es - a.r_zn).sum() == pytest.approx(0.08)


def test_plant_event_effect_rejects_exit_not_after_entry():
    base = pd.DataFrame(0.0, index=IDX, columns=["r_es", "r_zn"])
    ev = pd.DataFrame({"entry": [IDX[5]], "exit": [IDX[5]]})
    with pytest.raises(ValueError):
        synth.plant_event_effect(base, ev, 0.01, entry_col="entry", exit_col="exit")


@pytest.mark.parametrize("leg", ["es", "zn", "spread"])
def test_impulse_returns_single_jump(leg):
    out = synth.impulse_returns(IDX, IDX[17], 0.05, leg=leg)
    x = out.r_es - out.r_zn
    assert x.loc[IDX[17]] == pytest.approx(0.05)
    assert np.count_nonzero(x) == 1
    assert np.count_nonzero(out.to_numpy()) == (2 if leg == "spread" else 1)


# ----------------------------------------------------------- contract chain

CHAIN_IDX = pd.bdate_range("2011-01-03", "2015-12-31")


def _chain(root, idx=CHAIN_IDX, **kw):
    mult = {"ES": 50, "ZN": 1000}[root]
    kw.setdefault("daily_vol", 0.002)          # small, so roll jumps stand out
    return synth.synthetic_contract_chain(idx, root=root, multiplier=mult,
                                          basis_jump=0.05, seed=9, **kw)


def _within_contract_returns(chain):
    px = chain.pivot(index="date", columns="instrument_id", values="settle")
    return np.log(px).diff()


def _highest_oi(chain):
    top = chain.loc[chain.groupby("date")["open_interest"].idxmax()]
    return top.set_index("date")


@pytest.mark.parametrize("root", ["ES", "ZN"])
def test_chain_shape_and_listing(root):
    ch = _chain(root)
    assert list(ch.columns[:6]) == ["date", "instrument_id", "symbol",
                                    "expiration", "settle", "open_interest"]
    assert (ch.groupby("date").size() == 3).all()
    assert (ch.groupby("instrument_id")["date"].max()
            <= ch.groupby("instrument_id")["expiration"].first()).all()
    assert (ch.settle > 0).all()
    assert ch.symbol.str.fullmatch(root + r"[HMUZ]\d").all()
    assert (ch.multiplier == {"ES": 50, "ZN": 1000}[root]).all()


@pytest.mark.parametrize("root", ["ES", "ZN"])
def test_within_contract_returns_are_continuous(root):
    rets = _within_contract_returns(_chain(root, basis_noise=0.0))
    common = rets.sub(rets.mean(axis=1), axis=0)
    assert common.abs().max().max() < 0.05 / 50   # only the small carry drift differs
    assert rets.abs().max().max() < 0.05 / 2      # nothing near a basis jump
    # Default basis noise (0.1 * daily_vol = 2e-4 here) adds bounded, non-jump differences.
    noisy = _within_contract_returns(_chain(root))
    assert noisy.sub(noisy.mean(axis=1), axis=0).abs().max().max() < 0.05 / 50 + 8 * 2e-4
    assert noisy.abs().max().max() < 0.05 / 2


@pytest.mark.parametrize("root", ["ES", "ZN"])
def test_naive_highest_oi_splice_jumps_by_basis_at_rolls(root):
    ch = _chain(root)
    top = _highest_oi(ch)
    spliced = np.log(top["settle"]).diff()
    within = _within_contract_returns(ch)
    rolls = top.index[1:][top["instrument_id"].to_numpy()[1:]
                          != top["instrument_id"].to_numpy()[:-1]]
    assert len(rolls) >= 19                       # ~4 per year over 5 years
    for d in rolls:
        new_id = top.loc[d, "instrument_id"]
        jump = spliced.loc[d] - within.loc[d, new_id]
        assert abs(jump / 0.05 - 1) < 0.10, (d, jump)
    non_roll = spliced.drop(rolls).dropna()
    assert non_roll.abs().max() < 0.05 / 2


@pytest.mark.parametrize("root", ["ES", "ZN"])
def test_open_interest_peak_migrates_before_anchor(root):
    # Anchor: expiry for ES, first position day for ZN.
    ch = _chain(root)
    top = _highest_oi(ch)
    sess = ch["date"].drop_duplicates().reset_index(drop=True)
    pos = pd.Series(sess.index, index=sess)
    col = "expiration" if root == "ES" else "first_position_day"
    for iid, grp in top.groupby("instrument_id"):
        anchor = ch.loc[ch.instrument_id == iid, col].iloc[0]
        last_top = grp.index.max()
        if anchor > CHAIN_IDX[-1]:
            continue                               # still front at the end
        lead = pos[anchor] - pos[last_top]
        assert 1 <= lead <= 10, (iid, last_top, anchor)


def test_es_expirations_are_third_fridays_or_prior_session():
    removed = pd.Timestamp("2013-06-21")           # third Friday, made a holiday
    idx = CHAIN_IDX.drop(removed)
    ch = _chain("ES", idx=idx)
    exps = pd.DatetimeIndex(ch["expiration"].unique())
    for exp in exps:
        tf = synth.third_friday(exp.year, exp.month)
        if tf == removed:
            assert exp == pd.Timestamp("2013-06-20")
        else:
            assert exp == tf and exp.weekday() == 4 and 15 <= exp.day <= 21
    assert ch["first_position_day"].isna().all()


def test_zn_first_position_day_precedes_contract_month():
    ch = _chain("ZN")
    per = ch.drop_duplicates("instrument_id")
    for _, row in per.iterrows():
        fpd, exp = row.first_position_day, row.expiration
        month_start = exp.to_period("M").start_time
        assert fpd < month_start
        assert (month_start - fpd).days <= 6       # two sessions before
        assert exp.month in (3, 6, 9, 12)
    sessions = CHAIN_IDX
    fpd = synth.zn_first_position_day(2014, 3, sessions)
    assert fpd == pd.Timestamp("2014-02-27")      # Mar 3 2014 is the 1st session
    assert synth.zn_expiration(2014, 3, sessions) == pd.Timestamp("2014-03-20")


def test_chain_reproducible_by_seed():
    a, b = _chain("ES"), _chain("ES")
    pd.testing.assert_frame_equal(a, b)
    c = synth.synthetic_contract_chain(CHAIN_IDX, root="ES", multiplier=50, seed=10)
    assert not np.allclose(a.settle, c.settle)


# ----------------------------------------------------------- event panels

def _ols(y, *cols):
    X = np.column_stack([np.ones(len(y))] + list(cols))
    return np.linalg.lstsq(X, y, rcond=None)[0]


def test_planted_panel_recovers_coefficients_by_ols():
    p = synth.planted_event_panel(40_000, b=0.08, c=-0.15, c_pseudo=0.05,
                                  a=0.02, seed=21)
    assert len(p) == 80_000 and set(p.ME) == {0, 1}
    assert (p.groupby("month").size() == 2).all()
    assert p.dose.between(0, 2).all() and (p.dose == 2).any()
    ev = p[p.ME == 1]
    a_hat, b_hat, c_hat = _ols(ev.Y.to_numpy(), ev.dose, ev.A)
    assert a_hat == pytest.approx(0.02, abs=0.04)
    assert b_hat == pytest.approx(0.08, abs=0.03)
    assert c_hat == pytest.approx(-0.15, abs=0.02)
    me = p.ME.to_numpy()
    coef = _ols(p.Y.to_numpy(), me, p.dose, me * p.dose, p.A, me * p.A)
    assert coef[5] == pytest.approx(-0.20, abs=0.03)   # c_E = c - c_pseudo
    assert coef[3] == pytest.approx(0.0, abs=0.05)     # b_E = 0 by default


def test_planted_panel_ar_and_heteroskedastic_noise():
    p = synth.planted_event_panel(40_000, b=0.0, c=0.0, ar=0.5, hetero=1.0,
                                  seed=4)
    ev = p[p.ME == 1]
    eps = ev.Y.to_numpy() / (1.0 + ev.dose.to_numpy())
    assert acf1(eps) == pytest.approx(0.5, abs=0.03)
    hi, lo = ev.Y[ev.dose > 1.5], ev.Y[ev.dose < 0.3]
    assert hi.std() > 1.8 * lo.std()


def test_planted_panel_quarter_end_dummy_and_seed():
    p = synth.planted_event_panel(24, b=0.1, c=-0.1, seed=1, start="2010-06")
    assert set(p.loc[p.QE == 1, "month"].dt.month) == {3, 6, 9, 12}
    pd.testing.assert_frame_equal(
        p, synth.planted_event_panel(24, b=0.1, c=-0.1, seed=1, start="2010-06"))


# ----------------------------------------------------------- calendar (optional)

def test_plant_on_real_event_schedule_if_calendar_available():
    try:
        from gqh import calendar as gcal
        sessions = gcal.xnys_sessions("2012-01-01", "2014-12-31")
        sched = gcal.event_schedule(gcal.SessionCalendar(sessions))
    except (ImportError, AttributeError, TypeError) as err:
        pytest.skip(f"gqh.calendar not usable yet: {err}")
    idx = pd.DatetimeIndex(sessions)
    ev = sched[sched["event_valid"].astype(bool)]
    assert len(ev) > 0
    base = synth.correlated_leg_returns(idx, seed=2)
    out = synth.plant_event_effect(base, ev, 0.01, entry_col="L_m4",
                                   exit_col="F1")
    x = (out.r_es - out.r_zn) - (base.r_es - base.r_zn)
    for _, row in ev.iterrows():
        win = (idx > row["L_m4"]) & (idx <= row["F1"])
        assert win.sum() == 5                    # L-4 -> F1 holds 5 returns
        assert x[win].sum() == pytest.approx(0.01, abs=1e-15)


def test_es_expiration_moves_off_exchange_holidays():
    xcals = pytest.importorskip("exchange_calendars")
    xnys = xcals.get_calendar("XNYS", start="2006-01-03", end="2027-12-31")
    days = pd.DatetimeIndex(xnys.sessions_in_range("2006-01-03", "2027-12-31"))
    assert synth.es_expiration(2008, 3, days) == pd.Timestamp("2008-03-20")  # Good Friday
    assert synth.es_expiration(2026, 6, days) == pd.Timestamp("2026-06-18")  # Juneteenth
    assert synth.es_expiration(2024, 9, days) == pd.Timestamp("2024-09-20")


# ----------------------------------------------------------- review regressions

@pytest.mark.parametrize("garch", [True, False])
def test_correlated_leg_returns_ar1_is_the_protocol_null(garch):
    # Regression: no generator produced correlated ES/ZN legs WITH AR(1), so the
    # frozen AR(1)-GARCH(1,1)-t5 null could not be run through the real pipeline.
    kw = dict(vol_es=0.011, vol_zn=0.004, rho=-0.6, seed=3, garch=garch, phi=0.3)
    if garch:
        kw.update(alpha=0.05, beta=0.90)          # finite 4th moment: tight checks
    df = synth.correlated_leg_returns(LONG, **kw)
    assert abs(acf1(df["r_es"]) - 0.3) < 0.02
    assert abs(acf1(df["r_zn"]) - 0.3) < 0.02
    assert abs(acf1(df["r_es"] - df["r_zn"]) - 0.3) < 0.02
    tol = 0.03 if garch else 0.02
    assert abs(df["r_es"].std() / 0.011 - 1) < tol   # (1 - phi^2) innovation scaling
    assert abs(df["r_zn"].std() / 0.004 - 1) < tol
    assert abs(df.corr().iloc[0, 1] - (-0.6)) < 0.015
    if garch:
        assert acf1(df["r_es"] ** 2) > 0.05
    # phi = 0 is the default and reproduces the white-noise legs exactly.
    pd.testing.assert_frame_equal(
        synth.correlated_leg_returns(LONG[:500], seed=4),
        synth.correlated_leg_returns(LONG[:500], seed=4, phi=0.0))
    with pytest.raises(ValueError):
        synth.correlated_leg_returns(LONG[:10], seed=0, phi=1.0)


def test_expiration_helpers_raise_when_days_do_not_cover_the_lookback():
    # Regression: negative positions wrapped to the END of `days`, returning
    # dates years in the future.
    days = pd.DatetimeIndex(pd.bdate_range("2014-03-03", "2016-12-30"))
    with pytest.raises(ValueError):
        synth.zn_first_position_day(2014, 3, days)    # needs 2 sessions before 03-03
    with pytest.raises(ValueError):
        synth.es_expiration(2013, 12, days)           # third Friday before the days
    with pytest.raises(ValueError):
        synth.es_expiration(2017, 3, days)            # third Friday after the days
    with pytest.raises(ValueError):
        synth.zn_expiration(2014, 3, days[:5])        # 7 sessions before 03-07 missing
    with pytest.raises(ValueError):
        synth.zn_expiration(2018, 3, days)            # month not in days at all
    assert synth.zn_first_position_day(2014, 6, days) == pd.Timestamp("2014-05-29")
    assert synth.es_expiration(2014, 3, days) == pd.Timestamp("2014-03-21")


def _zn_chain_on_xnys():
    from gqh import calendar as gcal
    sessions = gcal.xnys_sessions("2011-01-03", "2015-12-31")
    chain = synth.synthetic_contract_chain(sessions, root="ZN", multiplier=1000,
                                           basis_jump=0.05, seed=9)
    sched = gcal.event_schedule(gcal.SessionCalendar(sessions))
    return sessions, chain, sched[sched["event_valid"]]


def _fpd_rule(chain, on, f1):
    """Protocol ZN contract: nearest listed outright whose FPD is after F1."""
    listed = chain[(chain.date == on) & (chain.first_position_day > f1)]
    return int(listed.sort_values("expiration").instrument_id.iloc[0])


def test_zn_chain_rolls_inside_feb_may_aug_nov_event_windows():
    # Regression: ZN OI migration was keyed to the last trading day, so the
    # highest-OI switch landed 6-10 sessions AFTER the FPD and never inside an
    # event window; the FPD rule could not be told apart from a naive OI rule.
    _, ch, ev = _zn_chain_on_xnys()
    top = _highest_oi(ch)
    ids = top["instrument_id"].to_numpy()
    rolls = top.index[1:][ids[1:] != ids[:-1]]
    roll_months = ev[ev["month"].dt.month.isin([2, 5, 8, 11])]
    assert len(roll_months) >= 19
    for _, r in ev.iterrows():
        in_window = ((rolls > r["L_m8"]) & (rolls <= r["F1"])).any()
        oi_rule = int(top.loc[r["L_m8"], "instrument_id"])
        fpd_rule = _fpd_rule(ch, r["L_m8"], r["F1"])
        if r["month"].month in (2, 5, 8, 11):
            assert in_window, r["month"]
            assert oi_rule != fpd_rule, r["month"]
        else:
            assert not in_window and oi_rule == fpd_rule, r["month"]
    # The ZN switch sits a few sessions before the FPD of the contract it leaves.
    fpd = ch.drop_duplicates("instrument_id").set_index("instrument_id")["first_position_day"]
    sess = pd.Series(range(len(top)), index=top.index)
    for d in rolls:
        old = int(top["instrument_id"].shift(1).loc[d])
        assert 1 <= sess[fpd[old]] - sess[d] <= 10, d


def test_wrong_contract_gives_measurably_different_window_returns():
    # Regression: every contract shared one spot path, so the wrong ZN contract
    # changed an L-4 -> F1 return by at most ~2.6e-4 against ~6.5e-3 typical.
    _, ch, ev = _zn_chain_on_xnys()
    px = ch.pivot(index="date", columns="instrument_id", values="settle")
    top = _highest_oi(ch)
    diffs, sizes = [], []
    for _, r in ev[ev["month"].dt.month.isin([2, 5, 8, 11])].iterrows():
        good, bad = _fpd_rule(ch, r["L_m8"], r["F1"]), int(top.loc[r["L_m8"], "instrument_id"])
        y = lambda iid: np.log(px.loc[r["F1"], iid] / px.loc[r["L_m4"], iid])
        diffs.append(abs(y(good) - y(bad)))
        sizes.append(abs(y(good)))
    assert np.median(diffs) > 0.05 * np.median(sizes)   # was 0.008 with one common path
    # With basis_noise=0 the old, purely common path is recovered.
    flat = synth.synthetic_contract_chain(CHAIN_IDX, root="ZN", multiplier=1000, seed=9,
                                          basis_noise=0.0)
    rets = _within_contract_returns(flat)
    assert rets.sub(rets.mean(axis=1), axis=0).abs().max().max() < 0.05 / 50


def test_ar1_garch_t_variance_identity_is_tight():
    # Regression: dropping (1 - phi^2) from omega (Var(r) 5% too high at phi=0.3)
    # survived because the default GARCH has an infinite 4th moment and the old
    # check allowed 10%. alpha=0.05, beta=0.90 has a finite 4th moment.
    for seed in (11, 12, 13):
        r = synth.ar1_garch_t(400_000, phi=0.3, alpha=0.05, beta=0.90,
                              daily_vol=0.01, seed=seed)
        assert abs(r.std() / 0.01 - 1) < 0.02


def test_correlated_leg_cholesky_is_exact_without_garch():
    # Regression: z_zn = rho*t1 + (1 - rho^2)*t2 (missing sqrt) passed at rho=-0.2.
    df = synth.correlated_leg_returns(LONG, vol_es=0.011, vol_zn=0.004,
                                      rho=-0.6, seed=3, garch=False)
    assert abs(df["r_es"].std() / 0.011 - 1) < 0.02
    assert abs(df["r_zn"].std() / 0.004 - 1) < 0.02
    assert abs(df.corr().iloc[0, 1] - (-0.6)) < 0.015


def test_planted_panel_gamma_a_pseudo_and_unit_noise_variance():
    # Regression: gamma, a_pseudo and Var(u) = 1 were never exercised, so a
    # flipped gamma sign, gamma on pseudo rows, a dropped a_pseudo or a missing
    # sqrt(1 - ar^2) all passed.
    p = synth.planted_event_panel(40_000, b=0.08, c=-0.15, gamma=0.3, a=0.02,
                                  a_pseudo=-0.25, c_pseudo=0.05, seed=21)
    ev, ps = p[p.ME == 1], p[p.ME == 0]
    coef = _ols(ev.Y.to_numpy(), ev.dose, ev.QE, ev.A)       # H1 form + A
    assert coef[2] == pytest.approx(0.3, abs=0.04)             # gamma_hat
    assert coef[1] == pytest.approx(0.08, abs=0.03)
    ps_coef = _ols(ps.Y.to_numpy(), ps.dose, ps.QE, ps.A)
    assert ps_coef[2] == pytest.approx(0.0, abs=0.04)          # no QE effect on pseudo rows
    assert ps_coef[0] == pytest.approx(-0.25, abs=0.04)        # a_pseudo
    me = p.ME.to_numpy()
    st = _ols(p.Y.to_numpy() - 0.3 * me * p.QE.to_numpy(), me, p.dose, me * p.dose,
              p.A, me * p.A)
    assert st[1] == pytest.approx(0.02 - (-0.25), abs=0.05)    # a_E = a - a_pseudo
    # Var(u) = 1 at ar = 0.5 (with hetero scaling divided out).
    q = synth.planted_event_panel(40_000, b=0.0, c=0.0, ar=0.5, hetero=1.0,
                                  sigma=2.0, seed=4)
    for me_ in (0, 1):
        s = q[q.ME == me_]
        u = s.Y.to_numpy() / (2.0 * (1.0 + s.dose.to_numpy()))
        assert u.var() == pytest.approx(1.0, abs=0.06)


def test_protocol_nulls_generate_with_registered_settings():
    from gqh.synth import H2_REVERSAL_NULL, PROTOCOL_NULLS, protocol_null_legs

    sess = pd.bdate_range("2010-01-01", "2024-12-31")
    for name, spec in PROTOCOL_NULLS.items():
        df = protocol_null_legs(sess, name, seed=20261003)
        assert list(df.columns) == ["r_es", "r_zn"] and len(df) == len(sess)
        assert abs(df["r_es"].std() / spec["vol_es"] - 1) < 0.15
        assert abs(df.corr().iloc[0, 1] - spec["rho"]) < 0.08
    assert H2_REVERSAL_NULL["c_E"] == 0.0 and H2_REVERSAL_NULL["c"] == H2_REVERSAL_NULL["c_pseudo"]
