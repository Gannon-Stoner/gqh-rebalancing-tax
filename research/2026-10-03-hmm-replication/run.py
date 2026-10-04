"""HMM (NBER w33554) Table 1 col. 1 replication on ES/ZN IS settlements. See SPEC.md (hash-locked)."""
from pathlib import Path
import sys, json, hashlib
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import pandas as pd
import statsmodels.api as sm
from gqh.config import frozen_config
from gqh.pipeline import prepare

OUT = Path(__file__).parent
CFG = frozen_config()
HMM_END = pd.Timestamp('2023-03-17')
DELTAS = np.round(np.arange(0, 0.02501, 0.001), 4)
COST_PER_DW = 1.3e-4
PROTECTED = ['HYPOTHESIS.md', 'AMENDMENTS.md', 'config/frozen.yaml', 'results_is.json']


def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def drift(w, rs, rb): return w * (1 + rs) / (w * (1 + rs) + (1 - w) * (1 + rb))


def signals(df):
    rs, rb = df.R_SP.fillna(0).to_numpy(), df.R_10Y.fillna(0).to_numpy()
    n = len(df)
    thr = np.zeros((n, len(DELTAS)))
    w = np.full(len(DELTAS), 0.6)
    for t in range(n):
        wp = drift(w, rs[t], rb[t])
        thr[t] = wp - 0.6
        w = np.where(np.abs(wp - 0.6) >= DELTAS, 0.6, wp)
    cal = np.zeros(n); wc = 0.6
    for t in range(n):
        wp = drift(wc, rs[t], rb[t]); cal[t] = wp - 0.6
        wc = 0.6 if df.is_L.iat[t] else wp
    ret = df.Ret.fillna(0)
    cum = ret.cumsum()
    def mom(ks): return np.mean([np.sign(cum - cum.shift(k)) for k in ks], axis=0)
    out = pd.DataFrame(index=df.index)
    out['Threshold'] = thr.mean(axis=1)
    out['Calendar'] = cal
    out['Momentum'] = (mom(range(11, 21)) + mom([21, 42, 63, 126, 252])) / 2
    return out


def fit(d, y='y', terms=('Threshold', 'Calendar', 'week4', 'Calendar_week4', 'Momentum', 'Ret'), cov='HC1'):
    d = d.dropna(subset=[y, *terms])
    X = sm.add_constant(d[list(terms)])
    kw = dict(cov_type='HAC', cov_kwds={'maxlags': 5}) if cov == 'NW5' else dict(cov_type='HC1')
    r = sm.OLS(d[y], X).fit(**kw)
    rows = {k: dict(coef=float(r.params[k]), se=float(r.bse[k]), t=float(r.tvalues[k]),
                    p_two=float(r.pvalues[k]),
                    p_one_neg=float(r.pvalues[k] / 2 if r.params[k] < 0 else 1 - r.pvalues[k] / 2))
            for k in terms}
    return dict(n=int(r.nobs), start=str(d.index.min().date()), end=str(d.index.max().date()),
                adj_r2=float(r.rsquared_adj), cov=cov, terms=rows)


def strat(d, flip):
    th = -d.Threshold / 0.015
    c = np.where(d.week4 == 1, np.sign(-d.Calendar), 0.0)
    if flip:
        c = np.where(d.is_L, np.sign(d.cal_Lm4), c)  # position held over L -> F1
    w = pd.Series(0.5 * th + 0.5 * c, index=d.index)
    gross = w * d.y
    net = gross - COST_PER_DW * w.diff().abs().fillna(w.abs())
    def stats(x):
        x = x.dropna()
        return dict(ann_ret_pct=float(x.mean() * 252 * 100), ann_vol_pct=float(x.std() * np.sqrt(252) * 100),
                    sharpe=float(x.mean() / x.std() * np.sqrt(252)), skew=float(x.skew()), days=int(len(x)))
    res = dict(gross=stats(gross), net=stats(net))
    ex = ~(((d.index >= '2020-02-15') & (d.index <= '2020-04-30')))
    res['net_ex_covid_feb_apr_2020'] = stats(net[ex])
    res['net_by_year'] = {str(y): float(v) for y, v in (net.groupby(net.index.year).sum() * 100).items()}
    return res


def main():
    lock = json.loads((OUT / 'spec_lock.json').read_text())
    assert digest(OUT / 'SPEC.md') == lock['sha256'], 'SPEC.md changed after lock'
    before = {p: digest(ROOT / p) for p in PROTECTED}
    panels = {l: pd.read_parquet(ROOT / 'data/derived' / f'settlements_{l}.parquet',
                                 filters=[('date', '<=', CFG.is_end)]) for l in ['ES', 'ZN']}
    assert all(p.date.max() <= CFG.is_end for p in panels.values())
    w = prepare(panels, start=CFG.is_start, end=CFG.is_end, cfg=CFG)
    ref = w.ref.copy()
    assert ref.index.max() <= CFG.is_end
    df = pd.DataFrame(index=ref.index)
    df['R_SP'] = np.expm1(ref.r_es.astype(float)); df['R_10Y'] = np.expm1(ref.r_zn.astype(float))
    df['Ret'] = df.R_SP - df.R_10Y
    m = df.index.to_period('M')
    pos_from_end = df.groupby(m).cumcount(ascending=False)
    df['is_L'] = pos_from_end == 0
    df['week4'] = (pos_from_end <= 4).astype(float)
    df['week4_exL'] = ((pos_from_end <= 4) & (pos_from_end >= 1)).astype(float)
    df = df.join(signals(df))
    df['Calendar_week4'] = df.Calendar * df.week4
    df['Calendar_week4_exL'] = df.Calendar * df.week4_exL
    df['cal_Lm4'] = df.Calendar.where(pos_from_end == 4).groupby(m).transform('max')
    df['y'] = df.Ret.shift(-1)
    df['y_sp'] = df.R_SP.shift(-1); df['y_negbond'] = -df.R_10Y.shift(-1)
    df.loc[df.R_SP.isna() | df.R_10Y.isna(), ['Threshold', 'Calendar', 'Momentum', 'Ret']] = np.nan
    d = df.iloc[252:]
    res = {'spec_sha256': lock['sha256'], 'data_end': str(df.index.max().date()),
           'missing_return_days': int((df.R_SP.isna() | df.R_10Y.isna()).sum()),
           'signal_summary': {k: dict(mean=float(d[k].mean()), sd=float(d[k].std()))
                              for k in ['Threshold', 'Calendar', 'Momentum']},
           'corr_threshold_calendar_momentum': d[['Threshold', 'Calendar', 'Momentum']].corr().round(3).to_dict()}
    prim = fit(d)
    res['primary'] = prim
    p = [prim['terms']['Threshold']['p_one_neg'], prim['terms']['Calendar_week4']['p_one_neg']]
    order = np.argsort(p); holm = [None, None]; run = 0
    for i, j in enumerate(order):
        run = max(run, min(1, (2 - i) * p[j])); holm[j] = run
    res['confirmatory'] = {'R1_threshold': dict(p_one=p[0], p_holm=holm[0], replicated=bool(holm[0] < .05)),
                           'R2_calendar_week4': dict(p_one=p[1], p_holm=holm[1], replicated=bool(holm[1] < .05))}
    post = d[d.index > HMM_END]; recent = d[d.index >= '2015-10-01']
    res['secondary'] = {
        'post_HMM_sample': fit(post),
        'from_2015_10': fit(recent),
        'primary_NW5': fit(d, cov='NW5'),
        'no_momentum': fit(d, terms=('Threshold', 'Calendar', 'week4', 'Calendar_week4', 'Ret')),
        'week4_excluding_L': fit(d, terms=('Threshold', 'Calendar', 'week4_exL', 'Calendar_week4_exL', 'Momentum', 'Ret')),
        'leg_SP': fit(d, y='y_sp'),
        'leg_negative_bond': fit(d, y='y_negbond'),
    }
    res['strategy'] = {'no_first_session_flip': strat(d, False), 'with_first_session_flip': strat(d, True),
                       'cost_per_unit_dw_bp': COST_PER_DW * 1e4}
    after = {p: digest(ROOT / p) for p in PROTECTED}
    res['protected_unchanged'] = before == after
    (OUT / 'results.json').write_text(json.dumps(res, indent=2, default=float))
    d[['Ret', 'Threshold', 'Calendar', 'Momentum', 'week4', 'y']].to_csv(OUT / 'daily_panel.csv')
    print(json.dumps({k: res[k] for k in ['confirmatory', 'protected_unchanged', 'data_end']}, indent=1))


if __name__ == '__main__':
    main()
