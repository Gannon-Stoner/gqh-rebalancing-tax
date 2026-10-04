"""Post-observation F1 reversal and matched executable quote checks; IS only."""
from analyze import *
from gqh.quotes import QuoteBook
from gqh.calendar import is_early_close
from gqh.stats import holm

def main():
    f=pd.read_csv(OUT/'monthly_variants.csv')
    b=f[f.variant=='baseline'].set_index('month').copy()
    first=f[f.variant=='F1_only'].set_index('month')
    last=f[f.variant=='exit_L'].set_index('month')
    extras=[]
    for name in ['reverse_F1','flip_at_L','always_long_spread_F1','always_long_ES_F1']:
        g=b.copy();g['variant']=name
        if name=='reverse_F1':g['gross']=-first.gross;g['cost']=first.cost
        if name=='flip_at_L':g['gross']=last.gross-first.gross;g['cost']=last.cost+first.cost
        if name=='always_long_spread_F1':g['gross']=first.gross*first.direction;g['cost']=first.cost
        if name=='always_long_ES_F1':
            g['gross']=first.es*first.direction
            # Recover original ES round-trip fee from ES-only base decomposition.
            g['cost']=f[f.variant=='ES_only'].set_index('month').cost
        g['net']=g.gross-g.cost;g['net2']=g.gross-2*g.cost
        extras.append(g.reset_index())
    extra=pd.concat(extras,ignore_index=True);extra.to_csv(OUT/'followup_monthly.csv',index=False)
    ff=pd.concat([f,extra],ignore_index=True)
    summaries=[]
    for name,g in ff.groupby('variant',sort=False):
        for segment,q in [('common',g[g.common])]+[(f'era_{e}',q) for e,q in g.groupby('era')]:
            summaries.append(dict(variant=name,segment=segment,**stats(q)))
    pd.DataFrame(summaries).to_csv(OUT/'followup_summary.csv',index=False)
    bydir=[]
    for name in ['baseline','exit_L','F1_only','reverse_F1','flip_at_L','always_long_spread_F1','always_long_ES_F1']:
        g=ff[(ff.variant==name)&ff.common]
        for s in [-1,1]:
            q=g.copy()
            for c in ['net','net2','gross','cost']:q[c]=q[c].where(q.direction==s,0.)
            q.traded=q.traded&(q.direction==s)
            bydir.append(dict(variant=name,direction=s,**stats(q)))
    pd.DataFrame(bydir).to_csv(OUT/'followup_direction.csv',index=False)
    # Within-family adjustment of initial seven mean-return tests, not across all prior looks.
    t=[]
    for name,g in f[f.common].groupby('variant',sort=False):
        x=g.net.to_numpy()/CFG.reference_nav
        boots=bootstrap_means(x-x.mean())
        p=(1+np.sum(np.abs(boots)>=abs(x.mean())))/(NBOOT+1)
        t.append(dict(variant=name,mean_bp=x.mean()*1e4,p_two_sided=p))
    tests=pd.DataFrame(t);tests['holm_seven']=holm(tests.p_two_sided.to_numpy());tests.to_csv(OUT/'family_tests.csv',index=False)
    panels={leg:pd.read_parquet(ROOT/'data'/'derived'/f'settlements_{leg}.parquet',filters=[('date','<=',CFG.is_end)]) for leg in ('ES','ZN')}
    w=prepare(panels,start=CFG.is_start,end=CFG.is_end,cfg=CFG)
    z=size_events(w.events,w.es,w.zn,cfg=CFG)
    bbo=pd.read_parquet(ROOT/'data'/'derived'/'bbo_1m_close.parquet',filters=[('ts_et','<',CFG.oos_start)],columns=['ts_et','instrument_id','bid_px_00','ask_px_00'])
    assert bbo.ts_et.max()<CFG.oos_start
    book=QuoteBook(bbo);sched=w.sched.set_index('month')
    qs=[];elig=[]
    for i,r in w.events.iterrows():
        if r['sample']!='IS':continue
        m=str(r.month);zz=z.loc[i];good=bool(r.valid and not zz.below_one_lot)
        ds=[r.entry,sched.loc[r.month,'L'],r.exit]
        reason=''
        if not good:reason='invalid_or_below_one_lot'
        elif any(is_early_close(d) for d in ds):reason='early_close_any_endpoint'
        qq={}
        if not reason:
            for leg in ['es','zn']:
                for j,d in enumerate(ds):
                    v=book(int(r[f'{leg}_id']),d+pd.Timedelta(hours=15,minutes=59))
                    if v is None:reason='missing_or_stale_quote'
                    qq[(leg,j)]=v
        good=not reason
        elig.append(dict(month=m,eligible=good,reason=reason))
        for name,legs,sgn,segments in [('baseline','both',int(r.s),[(0,2,1)]),('exit_L','both',int(r.s),[(0,1,1)]),
                                      ('F1_only','both',int(r.s),[(1,2,1)]),('reverse_F1','both',int(r.s),[(1,2,-1)]),
                                      ('flip_at_L','both',int(r.s),[(0,1,1),(1,2,-1)]),
                                      ('always_long_spread_F1','both',1,[(1,2,1)]),
                                      ('always_long_ES_F1','es',1,[(1,2,1)])]:
            pnl=cost=extra_cost=0.
            for leg in ['es','zn']:
                if not good or (legs!='both' and leg!=legs):continue
                for a,bb,sg in segments:
                    q=sgn*sg*int(zz[f'n_{leg}'])*(1 if leg=='es' else -1)
                    pin=qq[(leg,a)][1 if q>0 else 0]
                    pout=qq[(leg,bb)][0 if q>0 else 1]
                    pnl+=q*CFG.multipliers[leg.upper()]*(pout-pin)
                    cost+=2*abs(q)*CFG.fee
                    extra_cost+=2*abs(q)*side_cost(leg.upper(),cfg=CFG)
            rec=b.loc[m]
            qs.append(dict(variant=name,month=m,year=rec.year,era=rec.era,common=rec.common,
                           direction=int(r.s),quarter=bool(r.QE),traded=good,gross=pnl,cost=cost,
                           net=pnl-cost,net2=pnl-cost-extra_cost))
    qdf=pd.DataFrame(qs);qdf.to_csv(OUT/'matched_quote_monthly.csv',index=False)
    eligibility=pd.DataFrame(elig);eligibility.to_csv(OUT/'matched_quote_eligibility.csv',index=False)
    out=[]
    for name,g in qdf.groupby('variant',sort=False):
        for segment,q in [('common',g[g.common])]+[(f'era_{e}',q) for e,q in g.groupby('era')]:
            out.append(dict(variant=name,segment=segment,**stats(q)))
    qsummary=pd.DataFrame(out);qsummary.to_csv(OUT/'matched_quote_summary.csv',index=False)
    matched=f.merge(eligibility,on='month');matched=matched[matched.common]
    sm=[]
    for name,g in matched.groupby('variant',sort=False):
        q=g.copy()
        for c in ['net','net2','gross','cost']:q[c]=q[c].where(q.eligible,0.)
        q.traded=q.traded&q.eligible
        sm.append(dict(variant=name,**stats(q)))
    matchedsummary=pd.DataFrame(sm);matchedsummary.to_csv(OUT/'matched_settlement_summary.csv',index=False)
    quote_pivot=qdf[qdf.common].pivot(index='month',columns='variant',values='net')
    contrasts=[]
    for aa,bb in [('exit_L','baseline'),('flip_at_L','baseline'),('reverse_F1','always_long_spread_F1')]:
        x=(quote_pivot[aa]-quote_pivot[bb])/CFG.reference_nav*1e4
        boot=bootstrap_means(x)
        contrasts.append(dict(a=aa,b=bb,mean_difference_bp=x.mean(),ci90_lo=np.quantile(boot,.05),ci90_hi=np.quantile(boot,.95)))
    pd.DataFrame(contrasts).to_csv(OUT/'matched_quote_contrasts.csv',index=False)
    rep=['# Post-observation timing follow-up (exploratory)','',
         'This family was declared after the F1 losses were observed. Reversal and flip strategies are new exploratory hypotheses; none is confirmed. No OOS was loaded. All executable comparisons jointly exclude early closes or unavailable quotes at entry, L and F1. Bid/ask crossing is included at each entry/exit; flipping doubles turnover. Doubled costs add one registered fee-plus-half-spread per contract per side.','',
         '## Common-period settlement results','',md(pd.DataFrame(summaries).query("segment=='common'")),'',
         '## Matched executable results','',md(qsummary.query("segment=='common'")),'',
         '## Settlement results on those same dates','',md(matchedsummary),'',
         '## Executable paired comparisons','',md(pd.DataFrame(contrasts)),'',
         '## Initial seven-variant family adjustment','',md(tests),'',
         'Holm adjustment here covers only seven newly examined decomposition rows, not the historic 80+ previous looks nor the additional follow-up family. Temporal split consistency and positive selected-sample confidence intervals do not remove selection bias.','',
         '## Direction conditional results','',md(pd.DataFrame(bydir)),'',
         'Reproduce after analyze.py: `.venv/bin/python research/2026-10-03-failure-analysis/timing_regimes/followup.py`']
    (OUT/'FOLLOWUP_REPORT.md').write_text('\n'.join(rep)+'\n')
    print(pd.DataFrame(summaries).query("segment=='common'")[['variant','net','sharpe','sharpe_2x','without_best3_net']].to_string(index=False))
    print(qsummary.query("segment=='common'")[['variant','trades','net','sharpe','sharpe_2x','mean_bp_ci90_lo','mean_bp_ci90_hi']].to_string(index=False))
    print(pd.DataFrame(bydir)[['variant','direction','trades','net','sharpe']].to_string(index=False))
    print(tests.to_string(index=False))

if __name__=='__main__':main()
