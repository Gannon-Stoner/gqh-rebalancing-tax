"""Post-result exploratory model diagnostics. Existing IS only; no frozen files changed.

Run from repository root: PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/model_relationships/analyze.py
"""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from gqh.config import frozen_config
from gqh.pipeline import prepare
from gqh.engine import size_events, run_row
from gqh.metrics import row_metrics
from gqh.reproduce import clean
from gqh.stats import holm

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CFG = frozen_config()
MONTHS = pd.period_range('2015-10', '2024-09', freq='M')
ERAS = {'all':('2015-10','2024-09'), '2015_18':('2015-10','2018-12'),
        '2019_20':('2019-01','2020-12'), '2021_24':('2021-01','2024-09'),
        '2019_24':('2019-01','2024-09')}


def features(panel, ref):
    f=panel.copy()
    corr=ref.r_es.rolling(63,min_periods=42).corr(ref.r_zn)
    f['long']=(f.s==1).astype(float)
    f['corr63']=f.dec.map(corr)
    f['log_vol']=np.log(f.sigma)
    f['common_move']=(np.log1p(f.R_E)+np.log1p(f.R_B))/(f.sigma*np.sqrt(f.n))
    for prefix,col in [('long','long'),('QE','QE'),('vol','log_vol'),('corr','corr63')]:
        f[prefix+'_dose']=f[col]*f.dose
        f[prefix+'_A']=f[col]*f.A
    f['dose2']=f.dose**2
    f['A2']=f.A**2
    f['dose_A']=f.dose*f.A
    return f


def walk(f, cols, penalty):
    X=f[cols].to_numpy(float)
    y=f.Y.to_numpy(float)
    valid=f.valid.to_numpy() & np.isfinite(X).all(axis=1) & np.isfinite(y)
    pred=np.full(len(f),np.nan)
    mean=np.full(len(f),np.nan)
    ntrain=np.zeros(len(f),int)
    for i,r in enumerate(f.itertuples()):
        if pd.isna(r.dec): continue
        train=valid & (f.exit<r.dec).to_numpy()
        ntrain[i]=train.sum()
        if train.sum()<60 or not np.isfinite(X[i]).all():continue
        xt=X[train]; yt=y[train]
        mu=xt.mean(axis=0); sd=xt.std(axis=0)
        sd=np.where(sd>1e-10,sd,1.)
        Z=np.column_stack([np.ones(len(xt)),(xt-mu)/sd])
        if penalty:
            P=np.diag([0.]+[penalty]*len(cols))
            coef=np.linalg.solve(Z.T@Z+P,Z.T@yt)
        else:coef=np.linalg.lstsq(Z,yt,rcond=None)[0]
        pred[i]=np.r_[1.,(X[i]-mu)/sd]@coef
        mean[i]=yt.mean()
    return pred,mean,ntrain


def monthly(ledger):
    return ledger.set_index('month').ret.reindex(MONTHS,fill_value=0.).to_numpy()


def sr(r):
    return float(np.mean(r)/np.std(r,ddof=1)*np.sqrt(12)) if np.std(r,ddof=1)>0 else np.nan


def robust_summary(r):
    omit={str(year):sr(r[MONTHS.year!=year]) for year in sorted(set(MONTHS.year))}
    best=int(np.argmax(r)); drop=r.copy();drop[best]=0
    return {'leave_year_out_sharpes':omit,'leave_year_out_min':min(omit.values()),
            'largest_winner_month':str(MONTHS[best]),'largest_winner_usd':r[best]*CFG.reference_nav,
            'without_largest_winner_sharpe':sr(drop),'without_largest_winner_net_usd':drop.sum()*CFG.reference_nav,
            'positive_years':int((pd.Series(r,index=MONTHS).groupby(MONTHS.year).sum()>0).sum()),
            'total_years':len(set(MONTHS.year))}


def bootstrap_family(returns, benchmark=None):
    """Paired moving-block uncertainty; max-t exploratory family correction.

    Null centered separately per candidate; shared draws preserve model dependence.
    Point/CI estimates are conditioned on generated historical forecasts. The model
    search and earlier all-IS inspection are not erased by this adjustment.
    """
    names=list(returns); X=np.column_stack([returns[n] for n in names])
    if benchmark is not None:X=X-benchmark[:,None]
    rng=np.random.default_rng(20261003)
    starts=rng.integers(0,len(X),size=(9999,int(np.ceil(len(X)/3))))
    idx=((starts[...,None]+np.arange(3)).reshape(9999,-1)[:,:len(X)])%len(X)
    draws=X[idx].mean(axis=1)
    se=draws.std(axis=0,ddof=1)
    obs=X.mean(axis=0)
    t=np.divide(obs,se,out=np.zeros_like(obs),where=se>0)
    null=np.divide(draws-obs,se,out=np.zeros_like(draws),where=se>0)
    max_t=np.max(null,axis=1)
    out={}
    for j,n in enumerate(names):
        out[n]={'mean_monthly':obs[j], 'ci90_mean_monthly':np.quantile(draws[:,j],[.05,.95]).tolist(),
                'p_positive_raw':float((1+np.sum(null[:,j]>=t[j]))/10000),
                'p_positive_max_t_family':float((1+np.sum(max_t>=t[j]))/10000)}
    return out


def regressions(f):
    """All-sample explanatory coefficient audit with HC3 errors, post hoc."""
    f=f.loc[f.valid].copy()
    f['month_code']=f.month.astype(str)
    specs={
      'original':['dose','A'],
      'direction':['dose','A','long'],
      'direction_interactions':['dose','A','long','long_dose','long_A'],
      'quarter_interactions':['dose','A','QE','QE_dose','QE_A'],
      'volatility_interactions':['dose','A','log_vol','vol_dose','vol_A'],
      'correlation_interactions':['dose','A','corr63','corr_dose','corr_A'],
      'nonlinear':['dose','A','dose2','A2','dose_A']}
    rows=[]
    for name,cols in specs.items():
        g=f.dropna(subset=cols+['Y'])
        Z=sm.add_constant(g[cols].astype(float),has_constant='add')
        fit=sm.OLS(g.Y,Z).fit(cov_type='HC3')
        for c in fit.params.index:
            rows.append({'model':name,'term':c,'estimate':fit.params[c],'se_hc3':fit.bse[c],
                         'p_two_sided':fit.pvalues[c],'n':len(g),'r2':fit.rsquared})
    d=pd.DataFrame(rows)
    # Every reported term, including repeated terms, remains in this conservative family.
    d['p_holm_all_reported_terms']=holm(d.p_two_sided.to_numpy())
    return d


def main():
    plan=json.loads((OUT/'analysis_plan.json').read_text())
    assert hashlib.sha256((ROOT/'results_is.json').read_bytes()).hexdigest()==plan['inputs']['results_is_sha256']
    panels={r:pd.read_parquet(ROOT/'data'/'derived'/f'settlements_{r}.parquet',filters=[('date','<=',CFG.is_end)]) for r in ('ES','ZN')}
    assert all(p.date.max()<=CFG.is_end for p in panels.values())
    w=prepare(panels,start=CFG.is_start,end=CFG.is_end,cfg=CFG)
    summary={};ret1={};ret2={}; pred_rows=[];stats_rows=[]
    for kind,raw in [('event',w.events),('pseudo',w.pseudos)]:
        f=features(raw,w.ref);size=size_events(raw,w.es,w.zn,cfg=CFG)
        f['hurdle']=size.hurdle
        f.to_csv(OUT/f'{kind}_features.csv',index=False)
        regressions(f).to_csv(OUT/f'{kind}_explanatory_regressions.csv',index=False)
        in_seg=f.month.isin(MONTHS).to_numpy()
        base=run_row(raw,size,f.valid.to_numpy()&in_seg,row=f'{kind}_always',cfg=CFG)
        key=f'{kind}_always';ret1[key]=monthly(base);ret2[key]=monthly(base.assign(ret=(base.pnl-base.cost)/CFG.reference_nav))
        summary[key]={}
        for era,(lo,hi) in ERAS.items():summary[key][era]=row_metrics(base,pd.period_range(lo,hi,freq='M'),CFG)
        summary[key]['robustness']=robust_summary(ret1[key])
        for name,spec in plan['models'].items():
            pred,mean,ntrain=walk(f,spec['features'],spec['penalty'])
            key=f'{kind}_{name}'
            decision=f.valid.to_numpy()&in_seg&np.isfinite(pred)&(pred>size.hurdle.to_numpy())
            led=run_row(raw,size,decision,row=key,cfg=CFG)
            led.to_csv(OUT/f'{key}_ledger.csv',index=False)
            ret1[key]=monthly(led)
            ret2[key]=monthly(led.assign(ret=(led.pnl-led.cost)/CFG.reference_nav))
            ok=in_seg&f.valid.to_numpy()&np.isfinite(pred)&np.isfinite(mean)
            y=f.Y.to_numpy()
            err=(y[ok]-pred[ok])**2; errmean=(y[ok]-mean[ok])**2
            summary[key]={'forecast':{'n':int(ok.sum()),'mse':err.mean(),'mean_baseline_mse':errmean.mean(),
                           'r2_vs_historical_mean':1-err.sum()/errmean.sum(),
                           'prediction_y_correlation':np.corrcoef(pred[ok],y[ok])[0,1],
                           'mean_prediction':pred[ok].mean(),'mean_realized_y':y[ok].mean()},
                          'robustness':robust_summary(ret1[key]),'sharpe_2x':sr(ret2[key])}
            for era,(lo,hi) in ERAS.items():
                summary[key][era]=row_metrics(led,pd.period_range(lo,hi,freq='M'),CFG)
                summary[key][era]['net_usd']=summary[key][era]['ann_return']*summary[key][era]['months']/12*CFG.reference_nav
            for i,r in f.iterrows():
                if not in_seg[i]:continue
                pred_rows.append({'kind':kind,'model':name,'month':str(r.month),'prediction':pred[i],
                    'historical_mean':mean[i],'Y':r.Y,'n_train':ntrain[i],'trade':decision[i],
                    'hurdle':size.hurdle.iloc[i]})
    # Exact reconstruction guard: original OLS must reproduce the registered ledger.
    frozen=json.loads((ROOT/'results_is.json').read_text())
    assert np.allclose(ret1['event_original_ols'],frozen['rows_IS']['monthly_returns_1x']['PG'],atol=1e-12)
    assert np.allclose(ret1['event_always'],frozen['rows_IS']['monthly_returns_1x']['P0'],atol=1e-12)
    pd.DataFrame(pred_rows).to_csv(OUT/'walk_forward_predictions.csv',index=False)
    pd.DataFrame(ret1,index=MONTHS.astype(str)).to_csv(OUT/'monthly_returns_1x.csv',index_label='month')
    pd.DataFrame(ret2,index=MONTHS.astype(str)).to_csv(OUT/'monthly_returns_2x.csv',index_label='month')
    candidates={k:v for k,v in ret1.items() if not k.endswith('_always')}
    boot={'positive_return_family_18':bootstrap_family(candidates),
          'improvement_over_original_PG_event_family_9':bootstrap_family({k:v for k,v in candidates.items() if k.startswith('event_')},ret1['event_original_ols']),
          'improvement_over_P0_event_family_9':bootstrap_family({k:v for k,v in candidates.items() if k.startswith('event_')},ret1['event_always'])}
    (OUT/'bootstrap.json').write_text(json.dumps(clean(boot),indent=2)+'\n')
    (OUT/'summary.json').write_text(json.dumps(clean(summary),indent=2)+'\n')
    for key,v in summary.items():
        stats_rows.append({'model':key,'trades':v['all']['trades'],'net_usd':ret1[key].sum()*CFG.reference_nav,
          'sharpe_1x':sr(ret1[key]),'sharpe_2x':sr(ret2[key]),
          'sharpe_2015_18':v['2015_18']['sharpe'],'sharpe_2019_20':v['2019_20']['sharpe'],
          'sharpe_2021_24':v['2021_24']['sharpe'],'sharpe_2019_24':v['2019_24']['sharpe'],
          'forecast_r2':v.get('forecast',{}).get('r2_vs_historical_mean'),
          'sharpe_without_top_winner':v['robustness']['without_largest_winner_sharpe'],
          'min_leave_year_out_sharpe':v['robustness']['leave_year_out_min'],
          'max_t_p':boot['positive_return_family_18'].get(key,{}).get('p_positive_max_t_family')})
    table=pd.DataFrame(stats_rows)
    table.to_csv(OUT/'model_scorecard.csv',index=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(11,7),layout='constrained')
    t=table[table.model.str.startswith('event_')].iloc[::-1]
    y=np.arange(len(t));ax.barh(y-.17,t.sharpe_1x,height=.32,label='Full walk-forward IS',color='#267b98')
    ax.barh(y+.17,t.sharpe_2021_24,height=.32,label='2021–Sep 2024',color='#c26b43')
    ax.set_yticks(y,t.model.str.replace('event_','',regex=False).str.replace('_',' ',regex=False))
    ax.axvline(0,color='#555',lw=.8);ax.set_xlabel('Annualized net Sharpe, 1× costs')
    ax.set_title('Exploratory models: a stronger fit must survive later years\nAll specifications reported; original out-of-sample period remains unopened',loc='left',fontweight='bold')
    ax.legend(loc='lower right');fig.savefig(OUT/'model_stability.png',dpi=170);plt.close(fig)
    print(table.round(4).to_string(index=False))
    print('Verified: original PG/P0 monthly returns reproduce frozen saved result; every predictor fit on past completed events.')


if __name__=='__main__':main()
