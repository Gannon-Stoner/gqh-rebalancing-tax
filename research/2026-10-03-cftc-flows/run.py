"""CFTC TFF positioning test of month-end rebalancing flows. See SPEC.md (hash-locked)."""
from pathlib import Path
import sys, json, hashlib, importlib.util
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import pandas as pd
import statsmodels.api as sm
from gqh.config import frozen_config
from gqh.pipeline import prepare

OUT = Path(__file__).parent
CFG = frozen_config()
CATS = {'asset_mgr': ('asset_mgr_positions_long', 'asset_mgr_positions_short'),
        'dealer': ('dealer_positions_long_all', 'dealer_positions_short_all'),
        'lev_money': ('lev_money_positions_long', 'lev_money_positions_short'),
        'other_rept': ('other_rept_positions_long', 'other_rept_positions_short'),
        'nonrept': ('nonrept_positions_long_all', 'nonrept_positions_short_all')}
spec = importlib.util.spec_from_file_location('rep', ROOT / 'research/2026-10-03-hmm-replication/run.py')
rep = importlib.util.module_from_spec(spec); spec.loader.exec_module(rep)


def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tff(code):
    t = pd.read_csv(OUT / f'data/tff_{code}.csv')
    t['date'] = pd.to_datetime(t.report_date_as_yyyy_mm_dd).dt.tz_localize(None)
    t = t[(t.date >= '2010-06-08') & (t.date <= CFG.is_end)].set_index('date').sort_index()
    out = pd.DataFrame({'oi': t.open_interest_all.astype(float)}, index=t.index)
    for k, (l, s) in CATS.items():
        out[k] = t[l].astype(float) - t[s].astype(float)
    return out


def window_change(pos, start_before, end_on_or_after):
    d = pos.index
    i0 = d[d < start_before]; i1 = d[d >= end_on_or_after]
    if len(i0) == 0 or len(i1) == 0:
        return None
    a, b = pos.loc[i0.max()], pos.loc[i1.min()]
    return {**{k: (b[k] - a[k]) / a['oi'] for k in CATS}, 'start': i0.max(), 'end': i1.min(), 'oi0': a['oi']}


def ols(df, y, X, cov='HC1'):
    d = df.dropna(subset=[y, *X])
    r = sm.OLS(d[y], sm.add_constant(d[X])).fit(cov_type=cov)
    return dict(n=int(r.nobs), **{x: dict(coef=float(r.params[x]), t=float(r.tvalues[x]), p_two=float(r.pvalues[x]))
                                  for x in X})


def one_sided(coef, p_two, sign):
    return p_two / 2 if np.sign(coef) == sign else 1 - p_two / 2


def main():
    lock = json.loads((OUT / 'spec_lock.json').read_text())
    assert digest(OUT / 'SPEC.md') == lock['sha256'], 'SPEC.md changed after lock'
    panels = {l: pd.read_parquet(ROOT / 'data/derived' / f'settlements_{l}.parquet',
                                 filters=[('date', '<=', CFG.is_end)]) for l in ['ES', 'ZN']}
    w = prepare(panels, start=CFG.is_start, end=CFG.is_end, cfg=CFG)
    ref = w.ref
    df = pd.DataFrame(index=ref.index)
    df['R_SP'] = np.expm1(ref.r_es.astype(float)); df['R_10Y'] = np.expm1(ref.r_zn.astype(float))
    df['Ret'] = df.R_SP - df.R_10Y
    m = df.index.to_period('M'); pos = df.groupby(m).cumcount(ascending=False)
    df['is_L'] = pos == 0
    df = df.join(rep.signals(df)[['Calendar']])
    es_px = (panels['ES'].sort_values('open_interest').groupby('date').tail(1).set_index('date').settle.sort_index())
    pos_es, pos_zn = tff('13874A'), tff('043602')
    rows = []
    for month, g in df.groupby(m):
        if month == m[0] or len(g) < 15:  # first month starts mid-month: no prior L reset
            continue
        s = g.index
        L, Lm4, Lm10, Lm14 = s[-1], s[-5], s[-11], s[-15]
        for kind, t0, t1, dsig in (('ME', Lm4, L, g.Calendar.loc[L]), ('MID', Lm14, Lm10, g.Calendar.loc[Lm10])):
            for leg, p in (('ES', pos_es), ('ZN', pos_zn)):
                c = window_change(p, t0, t1)
                if c is None:
                    continue
                rows.append(dict(month=str(month), kind=kind, leg=leg, D=dsig, QE=int(month.month in (3, 6, 9, 12)),
                                 es_px=float(es_px.asof(L)), **c))
    ev = pd.DataFrame(rows)
    third_fri = {}
    for mo in ev.month.unique():
        p = pd.Period(mo)
        if p.month in (3, 6, 9, 12):
            f = pd.date_range(p.start_time, p.end_time, freq='W-FRI')[2]
            sess = df.index[df.index < f]
            third_fri[mo] = (sess[-7], f)
    ev['roll'] = [int(r.month in third_fri and not (r.end < third_fri[r.month][0] or r.start > third_fri[r.month][1]))
                  for r in ev.itertuples()]
    ev.to_csv(OUT / 'windows.csv', index=False)
    me = ev[ev.kind == 'ME']
    res = {'spec_sha256': lock['sha256'], 'months': int(me.month.nunique()),
           'note_signal_source': 'Calendar recomputed with the replication signals() on all IS sessions, so it starts '
                                 '2010-07 rather than the 2011-06 start of daily_panel.csv; same definition.'}
    F = {}
    for name, leg, sign in (('F1_ES', 'ES', -1), ('F2_ZN', 'ZN', +1)):
        r = ols(me[me.leg == leg], 'asset_mgr', ['D'])
        F[name] = dict(**r['D'], n=r['n'], p_one=one_sided(r['D']['coef'], r['D']['p_two'], sign))
    p = [F['F1_ES']['p_one'], F['F2_ZN']['p_one']]; o = np.argsort(p); run = 0
    for i, j in enumerate(o):
        run = max(run, min(1, (2 - i) * p[j])); F[['F1_ES', 'F2_ZN'][j]]['p_holm'] = run
    for k in F: F[k]['confirmed'] = bool(F[k]['p_holm'] < .05)
    res['confirmatory'] = F
    sec = {}
    for leg in ('ES', 'ZN'):
        e = ev[ev.leg == leg].copy(); e['ME'] = (e.kind == 'ME').astype(int); e['ME_D'] = e.ME * e.D
        sub = e[e.kind == 'ME'].copy(); sub['QE_D'] = sub.QE * sub.D
        sec[leg] = {
            'month_end_by_category': {k: ols(sub, k, ['D']) for k in CATS},
            'mid_month_by_category': {k: ols(e[e.kind == 'MID'], k, ['D']) for k in CATS},
            'pooled_ME_difference_asset_mgr': ols(e, 'asset_mgr', ['ME', 'D', 'ME_D']),
            'quarter_end_asset_mgr': ols(sub, 'asset_mgr', ['D', 'QE', 'QE_D']),
            'roll_control_asset_mgr': ols(sub, 'asset_mgr', ['D', 'roll']),
            'sub_2010_2015_asset_mgr': ols(sub[sub.month < '2015-10'], 'asset_mgr', ['D']),
            'sub_2015_2024_asset_mgr': ols(sub[sub.month >= '2015-10'], 'asset_mgr', ['D']),
        }
    es_me = me[me.leg == 'ES']
    b = F['F1_ES']['coef']
    sec['implied_rebalanced_assets_usd'] = float(-b * (es_me.oi0 * 50 * es_me.es_px).median())
    res['secondary'] = sec
    (OUT / 'results.json').write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps(res['confirmatory'], indent=1))


if __name__ == '__main__':
    main()
