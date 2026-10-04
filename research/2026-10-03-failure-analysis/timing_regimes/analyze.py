"""Bounded IS-only timing/leg/regime audit. Run with repo .venv/bin/python."""
from pathlib import Path
import json
import sys
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/gqh-timing-mpl')

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from gqh.config import frozen_config
from gqh.pipeline import prepare
from gqh.engine import size_events, side_cost
from gqh.strategy import run_strategy
from gqh.diagnostics import event_paths

OUT = Path(__file__).parent
CFG = frozen_config()
NBOOT = 4999
RNG = np.random.default_rng(2026100307)

def sr(x):
    x = np.asarray(x, float)
    return float(np.sqrt(12)*np.mean(x)/np.std(x, ddof=1)) if len(x)>2 and np.std(x)>0 else np.nan

def bootstrap_means(x):
    x = np.asarray(x, float)
    n = len(x)
    starts = RNG.integers(n, size=(NBOOT, (n+2)//3))
    idx = ((starts[...,None]+np.arange(3))%n).reshape(NBOOT,-1)[:,:n]
    return x[idx].mean(axis=1)

def stats(g):
    r, r2 = g.net.to_numpy()/CFG.reference_nav, g.net2.to_numpy()/CFG.reference_nav
    d = dict(months=len(g), trades=int(g.traded.sum()), net=float(g.net.sum()),
             gross=float(g.gross.sum()), costs=float(g.cost.sum()), sharpe=sr(r),
             sharpe_2x=sr(r2), mean_bp=float(r.mean()*1e4),
             positive_years=int((g.groupby('year').net.sum()>0).sum()),
             years=int(g.year.nunique()), worst_month=float(g.net.min()),
             best_month=float(g.net.max()), top3_months=float(g.net.nlargest(3).sum()),
             without_best3_net=float(g.net.sum()-g.net.nlargest(3).sum()))
    boot=bootstrap_means(r)*1e4
    d['mean_bp_ci90_lo'],d['mean_bp_ci90_hi']=map(float,np.quantile(boot,[.05,.95]))
    loo=[sr(g.loc[g.year!=y,'net']/CFG.reference_nav) for y in g.year.unique()]
    d['loo_year_sharpe_min'],d['loo_year_sharpe_max']=float(np.nanmin(loo)),float(np.nanmax(loo))
    return d

def era(m):
    return '2010-2015' if m.year<=2015 else ('2016-2020' if m.year<=2020 else '2021-2024')

def md(df):
    def f(v):
        return f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v)
    return '\n'.join(['| '+' | '.join(map(str,df.columns))+' |',
                       '| '+' | '.join(['---']*len(df.columns))+' |']+
                      ['| '+' | '.join(f(x) for x in r)+' |' for r in df.itertuples(index=False,name=None)])

def main():
    panels={leg:pd.read_parquet(ROOT/'data'/'derived'/f'settlements_{leg}.parquet',
                               filters=[('date','<=',CFG.is_end)]) for leg in ('ES','ZN')}
    assert all(p.date.max()<=CFG.is_end for p in panels.values())
    w=prepare(panels,start=CFG.is_start,end=CFG.is_end,cfg=CFG)
    run=run_strategy(w.events,w.pseudos,w.es,w.zn,cfg=CFG)
    sizes={k:size_events(v,w.es,w.zn,cfg=CFG) for k,v in [('event',w.events),('pseudo',w.pseudos)]}
    sch=w.sched.set_index('month')
    specs=[('baseline',-4,1,'both','event'),('exit_L',-4,0,'both','event'),
           ('last_day',-1,0,'both','event'),('F1_only',0,1,'both','event'),
           ('ES_only',-4,1,'es','event'),('ZN_only',-4,1,'zn','event'),
           ('midmonth',-13,-8,'both','pseudo')]
    rows=[]; paths=[]; daily=[]
    for kind, ev in [('event',w.events),('pseudo',w.pseudos)]:
        for i,r in ev.iterrows():
            if r['sample']!='IS': continue
            z=sizes[kind].loc[i]
            dates={k:w.sessions[w.sessions.get_loc(sch.loc[r.month,'L'])+k] for k in range(-13,2)
                   if 0<=w.sessions.get_loc(sch.loc[r.month,'L'])+k<len(w.sessions)}
            for name,ent,ext,legs,skind in specs:
                if skind!=kind: continue
                good=bool(r.valid and not z.below_one_lot and ent in dates and ext in dates)
                vals={}; gross=cost=0.
                for leg,panel in [('es',w.es),('zn',w.zn)]:
                    good_leg=good and (legs=='both' or legs==leg)
                    if good_leg:
                        entry_date=r.entry if ent in (-4,-13) else dates[ent]
                        exit_date=r.exit if ext in (1,-8) else dates[ext]
                        a=panel.price(int(r[f'{leg}_id']),entry_date); b=panel.price(int(r[f'{leg}_id']),exit_date)
                        if not np.isfinite(a+b): raise ValueError((r.month,name,leg))
                        q=int(z[f'n_{leg}'])*int(r.s)*(1 if leg=='es' else -1)
                        vals[leg]=q*CFG.multipliers[leg.upper()]*(b-a)
                        cost+=abs(q)*2*side_cost(leg.upper(),cfg=CFG)
                    else: vals[leg]=0.
                    gross+=vals[leg]
                rows.append(dict(variant=name,month=str(r.month),year=r.month.year,era=era(r.month),
                                 quarter=bool(r.QE),direction=int(r.s),common=r.month>=run.segment_start,
                                 traded=good,gross=gross,cost=cost,net=gross-cost,net2=gross-2*cost,
                                 es=vals['es'],zn=vals['zn'],dose=r.dose,sigma=r.sigma))
            if kind=='event' and bool(r.valid):
                out=dict(month=str(r.month),year=r.month.year,era=era(r.month),common=r.month>=run.segment_start,
                         s=int(r.s),dose=r.dose,sigma=r.sigma,quarter=bool(r.QE))
                # Paths are frozen L-5 direction and actual event contracts; normalized by daily sigma.
                for k,d in dates.items():
                    x=w.es.log_return(int(r.es_id),dates[-12],d)-w.zn.log_return(int(r.zn_id),dates[-12],d)
                    out[f'k{k:+d}']=int(r.s)*x/r.sigma
                for label,d in [('decision',r.dec),('entry',r.entry)]:
                    x=w.es.log_return(int(r.es_id),dates[-12],d)-w.zn.log_return(int(r.zn_id),dates[-12],d)
                    out[label]=int(r.s)*x/r.sigma
                paths.append(out)
                for p in range(w.sessions.get_loc(r.dec)+1,w.sessions.get_loc(r.exit)+1):
                    before=w.sessions[p-1]; after=w.sessions[p]
                    k=p-w.sessions.get_loc(sch.loc[r.month,'L'])
                    x=w.es.log_return(int(r.es_id),before,after)-w.zn.log_return(int(r.zn_id),before,after)
                    e=int(r.s)*int(z.n_es)*CFG.multipliers['ES']*(w.es.price(int(r.es_id),after)-w.es.price(int(r.es_id),before))
                    b=-int(r.s)*int(z.n_zn)*CFG.multipliers['ZN']*(w.zn.price(int(r.zn_id),after)-w.zn.price(int(r.zn_id),before))
                    daily.append(dict(month=str(r.month),year=r.month.year,era=era(r.month),common=r.month>=run.segment_start,
                                      offset=k,direction=int(r.s),quarter=bool(r.QE),signed_sigma=int(r.s)*x/r.sigma,
                                      es=e,zn=b,gross=e+b,dose=r.dose,held=after>r.entry,date=str(after.date())))
    allrows=pd.DataFrame(rows); df=allrows[allrows.month<='2024-09'].copy()
    df.to_csv(OUT/'monthly_variants.csv',index=False)
    # Exact baseline and additive accounting cross-checks.
    existing=run.ledgers[('P0',1.)].copy(); existing.month=existing.month.astype(str)
    a=df[(df.variant=='baseline')&df.common].set_index('month').net
    b=existing.set_index('month').pnl.reindex(a.index)
    assert np.allclose(a,b,atol=1e-6)
    piv=df.pivot(index='month',columns='variant',values='net')
    assert np.allclose(piv.baseline,piv.ES_only+piv.ZN_only,atol=1e-6)
    assert np.allclose(piv.baseline,piv.exit_L+piv.F1_only+df[df.variant=='baseline'].set_index('month').cost,atol=1e-6)
    summaries=[]
    for name,g in df.groupby('variant',sort=False):
        groups={'full_IS':g,'common':g[g.common]}
        groups.update({f'era_{e}':q for e,q in g.groupby('era')})
        groups.update({f'common_direction_{s}':g[g.common].assign(net=lambda q:np.where(q.direction==s,q.net,0),
                      net2=lambda q:np.where(q.direction==s,q.net2,0),gross=lambda q:np.where(q.direction==s,q.gross,0),
                      cost=lambda q:np.where(q.direction==s,q.cost,0),traded=lambda q:q.traded&(q.direction==s)) for s in [-1,1]})
        groups.update({f'common_quarter_{s}':g[g.common].assign(net=lambda q:np.where(q.quarter==s,q.net,0),
                      net2=lambda q:np.where(q.quarter==s,q.net2,0),gross=lambda q:np.where(q.quarter==s,q.gross,0),
                      cost=lambda q:np.where(q.quarter==s,q.cost,0),traded=lambda q:q.traded&(q.quarter==s)) for s in [False,True]})
        for label,q in groups.items():
            if len(q)>3: summaries.append(dict(variant=name,segment=label,**stats(q)))
    summ=pd.DataFrame(summaries);summ.to_csv(OUT/'variant_summary.csv',index=False)
    df.groupby(['variant','year']).agg(net=('net','sum'),net2=('net2','sum'),trades=('traded','sum'),es=('es','sum'),zn=('zn','sum')).to_csv(OUT/'annual.csv')
    daily=pd.DataFrame(daily);daily.to_csv(OUT/'daily_attribution.csv',index=False)
    paths=pd.DataFrame(paths);paths.to_csv(OUT/'actual_signal_paths.csv',index=False)
    old=event_paths(w.ref,w.sched,cfg=CFG);old.month=old.month.astype(str)
    overlap=paths.merge(old[['month','s','dose','k+0','k+1']],on='month',suffixes=('_actual','_early'))
    overlap['sign_changed']=overlap.s_actual!=overlap.s_early
    comp=[]
    for e,g in overlap.groupby('era'):
        comp.append(dict(era=e,n=len(g),sign_changed_n=int(g.sign_changed.sum()),sign_changed_frac=float(g.sign_changed.mean()),
                         old_L=float(np.average(g['k+0_early'],weights=g.dose_early)),
                         actual_L=float(np.average(g['k+0_actual'],weights=g.dose_actual)),
                         actual_predecision=float(np.average(g['decision'],weights=g.dose_actual)),
                         actual_held_L=float(np.average(g['k+0_actual']-g['entry'],weights=g.dose_actual)),
                         actual_held_F1=float(np.average(g['k+1_actual']-g['entry'],weights=g.dose_actual))))
    pd.DataFrame(comp).to_csv(OUT/'path_comparison.csv',index=False)
    # Exact registered PG failure attribution: omitted P0 events and selected daily legs.
    gate=run.ledgers[('PG',1.)].copy();gate.month=gate.month.astype(str)
    base=df[(df.variant=='baseline')&df.common].merge(gate[['month','traded']],on='month',suffixes=('','_pg'))
    base.groupby(['era','traded_pg','direction']).agg(n=('month','size'),net=('net','sum'),es=('es','sum'),zn=('zn','sum'),cost=('cost','sum')).to_csv(OUT/'gate_attribution.csv')
    # Annual uncertainty uses fixed calendar grouping; no alternate breakpoint sweep.
    dailycommon=daily[daily.common & daily.held]
    dailycommon.groupby(['era','offset']).agg(n=('month','size'),signed_sigma=('signed_sigma','mean'),es=('es','sum'),zn=('zn','sum'),gross=('gross','sum')).to_csv(OUT/'daily_by_era.csv')
    pair=[]
    common=df[df.common].pivot(index='month',columns='variant',values='net')
    for a,b in [('exit_L','baseline'),('last_day','baseline'),('F1_only','baseline'),('ES_only','baseline'),('ZN_only','baseline'),('baseline','midmonth')]:
        d=(common[a]-common[b])/CFG.reference_nav*1e4
        boots=bootstrap_means(d)
        pair.append(dict(a=a,b=b,mean_diff_bp=float(d.mean()),ci90_lo=float(np.quantile(boots,.05)),ci90_hi=float(np.quantile(boots,.95))))
    pd.DataFrame(pair).to_csv(OUT/'paired_comparisons.csv',index=False)
    # Plot postdecision paths, the only part of actual-signal figure usable as a forward path.
    fig,axs=plt.subplots(1,2,figsize=(12,4.5))
    for e,g in paths.groupby('era'):
        ks=np.arange(-5,2);ys=np.array([np.average((g['decision'] if k==-5 else g['entry'] if k==-4 else g[f'k{k:+d}'])-g['decision'],weights=g.dose) for k in ks])
        axs[0].plot(ks,ys,marker='o',label=f'{e} (n={len(g)})')
    axs[0].axhline(0,color='gray',lw=.7);axs[0].axvline(-4,color='gray',ls=':')
    axs[0].set(title='Actual L−5 signal: held-contract path',xlabel='Session offset from month-end L',ylabel='Dose-weighted signed daily-sigma units')
    axs[0].legend(fontsize=8)
    for name in ['baseline','exit_L','last_day','F1_only','ES_only','ZN_only','midmonth']:
        g=df[(df.variant==name)&df.common]
        axs[1].plot(pd.to_datetime(g.month),g.net.cumsum()/1000,label=name)
    axs[1].axhline(0,color='gray',lw=.7);axs[1].set(title='Every exploratory variant, original sizing, 1× costs',ylabel='Cumulative net P&L ($000)')
    axs[1].legend(fontsize=8,ncol=2)
    fig.suptitle('Exploratory IS analysis • Later data remain locked',fontsize=12);fig.tight_layout()
    fig.savefig(OUT/'timing_and_legs.png',dpi=180);plt.close(fig)
    report=['# Exploratory timing, leg, and regime decomposition','',
            'Only settlements dated through 2024-10-01 were loaded. Original sources/configuration/results were not changed. All seven variants in PLAN.md are reported. Baseline reconciles exactly to registered P0; ES-only + ZN-only reconciles to baseline. No OOS was loaded.','',
            'All variants use original ex-ante quantities; short windows and single legs are not relevered. Later entries keep L-5 direction, dose, quantities, and contracts. Net means registered fees and half-spreads; settlement clocks remain asynchronous. Chronological subsets are exploratory stability checks after prior IS inspection, not validation on an untouched holdout.','',
            '## Seven-variant common-period summary','',
            md(summ[summ.segment=='common']),'','## Fixed calendar era summaries','',
            md(summ[summ.segment.str.startswith('era_')][['variant','segment','trades','net','sharpe','sharpe_2x','mean_bp_ci90_lo','mean_bp_ci90_hi']]),'','## Actual versus early sign paths','',
            md(pd.DataFrame(comp)),'','## Paired mean differences','',
            md(pd.DataFrame(pair)),'','Confidence intervals are pointwise 90% circular three-month block bootstrap intervals (4,999 draws). They are not corrected for the exploratory family or prior searches. Detailed CSVs retain each monthly return, all years, direction and quarter-end subsets, daily attribution, and gate omitted-event attribution.','',
            'Reproduce: `.venv/bin/python research/2026-10-03-failure-analysis/timing_regimes/analyze.py`']
    (OUT/'REPORT.md').write_text('\n'.join(report)+'\n')
    print(summ[summ.segment=='common'][['variant','trades','net','sharpe','sharpe_2x','mean_bp_ci90_lo','mean_bp_ci90_hi','without_best3_net']].to_string(index=False))
    print(pd.DataFrame(comp).to_string(index=False))

if __name__=='__main__':main()
