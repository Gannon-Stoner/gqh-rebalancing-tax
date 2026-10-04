"""Full exploratory search inventory, robust summaries and evidence figures.

Run after the three analyst scripts and model_relationships scripts. Outputs are
confined to this directory; raw data, frozen files and OOS are not touched.
"""
from pathlib import Path
import json,hashlib,os
os.environ.setdefault('MPLCONFIGDIR','/tmp/gqh-root-mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
MONTHS=pd.period_range('2015-10','2024-09',freq='M').astype(str)
NAV=1e7

def sr(r):
    r=np.asarray(r,float)
    return float(np.mean(r)/np.std(r,ddof=1)*np.sqrt(12)) if np.std(r,ddof=1)>0 else np.nan

def main():
    one={};two={};sources={}
    def put(k,r,r2,source):
        r=pd.Series(r,index=MONTHS).astype(float);r2=pd.Series(r2,index=MONTHS).astype(float)
        assert len(r)==108 and r.notna().all() and r2.notna().all(),k
        one[k]=r.to_numpy();two[k]=r2.to_numpy();sources[k]=source
    frozen=json.loads((ROOT/'results_is.json').read_text())
    # Original 2x rows can be rebuilt from the constant extra cost in original
    # ledgers for PG/P0; for others the original results supply only summary.
    for k,r in frozen['rows_IS']['monthly_returns_1x'].items():
        put('registered_'+k,r,r,'Registered result; 2x Sharpe taken from saved summary')
    a=pd.read_csv(OUT/'model_relationships/monthly_returns_1x.csv',index_col='month').reindex(MONTHS)
    b=pd.read_csv(OUT/'model_relationships/monthly_returns_2x.csv',index_col='month').reindex(MONTHS)
    for k in a:put('model_'+k,a[k].to_numpy(),b[k].to_numpy(),'Nine feature specifications plus always-trade controls, event/pseudo')
    a=pd.read_csv(OUT/'gate_attribution/all_candidate_monthly_returns.csv',index_col='month').reindex(MONTHS)
    for k in a:
        if k.endswith('@1x'):put(k[:-3],a[k].to_numpy(),a[k[:-3]+'@2x'].to_numpy(),'Ablation or explicitly post-observation sign partition')
    a=pd.read_csv(OUT/'model_relationships/horizon_monthly_1x.csv',index_col='month').reindex(MONTHS)
    b=pd.read_csv(OUT/'model_relationships/horizon_monthly_2x.csv',index_col='month').reindex(MONTHS)
    for k in a:put('horizon_'+k,a[k].to_numpy(),b[k].to_numpy(),'Post-observation endpoint and target refit')
    for f,prefix in [('monthly_variants.csv','timing_'),('followup_monthly.csv','followup_'),('matched_quote_monthly.csv','quotes_')]:
        d=pd.read_csv(OUT/'timing_regimes'/f)
        d=d[d.month.isin(MONTHS)]
        for k,g in d.groupby('variant'):
            g=g.set_index('month').reindex(MONTHS)
            put(prefix+k,(g.net/NAV).to_numpy(),(g.net2/NAV).to_numpy(),f)
    X=np.column_stack(list(one.values()));names=list(one)
    # Original registered summary rows do not provide monthly doubled costs here;
    # use their saved true summary when reporting, not the temporary copy.
    rng=np.random.default_rng(2026100311)
    starts=rng.integers(0,108,size=(19999,36))
    idx=((starts[...,None]+np.arange(3)).reshape(19999,-1))%108
    # Aggregate with month counts, avoiding a B*T*K three-dimensional materialization.
    counts=np.zeros((len(idx),108),dtype=float)
    np.add.at(counts,(np.repeat(np.arange(len(idx)),108),idx.ravel()),1.)
    means=counts@X/108
    mu=X.mean(axis=0);se=means.std(axis=0,ddof=1)
    null=(means-mu)/se;t=mu/se
    maxima=np.max(np.abs(null),axis=1)
    base=one['registered_P0'];delta=X-base[:,None]
    delta_means=counts@delta/108;dm=delta.mean(axis=0);ds=delta_means.std(axis=0,ddof=1)
    dt=np.divide(dm,ds,out=np.zeros_like(dm),where=ds>1e-15)
    dn=np.divide(delta_means-dm,ds,out=np.zeros_like(delta_means),where=ds>1e-15)
    dmax=np.max(np.abs(dn),axis=1)
    rows=[]
    for j,k in enumerate(names):
        r=one[k]; order=np.argsort(r)[::-1];rr=r.copy();rr[order[:3]]=0
        dropyear=[sr(r[np.array([int(m[:4]) for m in MONTHS])!=y]) for y in range(2015,2025)]
        vals=dict(candidate=k,source=sources[k],net_usd=r.sum()*NAV,sharpe_1x=sr(r),sharpe_2x=sr(two[k]),
                  sharpe_2021_24=sr(r[np.asarray(MONTHS>='2021-01')]),
                  mean_bp=mu[j]*1e4,mean_ci90_lo=np.quantile(means[:,j],.05)*1e4,
                  mean_ci90_hi=np.quantile(means[:,j],.95)*1e4,
                  p_two_sided=float((1+np.sum(np.abs(null[:,j])>=abs(t[j])))/20000),
                  p_max_abs_t_all_candidates=float((1+np.sum(maxima>=abs(t[j])))/20000),
                  improvement_vs_P0_bp=dm[j]*1e4,
                  improvement_ci90_lo=np.quantile(delta_means[:,j],.05)*1e4,
                  improvement_ci90_hi=np.quantile(delta_means[:,j],.95)*1e4,
                  improvement_p_max_abs_t_all=float((1+np.sum(dmax>=abs(dt[j])))/20000),
                  pnl_without_top3=rr.sum()*NAV,min_leave_year_out_sharpe=np.nanmin(dropyear))
        if k.startswith('registered_'):
            vals['sharpe_2x']=frozen['rows_IS']['rows'][k.replace('registered_','')+'@2x']['sharpe']
        rows.append(vals)
    score=pd.DataFrame(rows)
    score.to_csv(OUT/'complete_exploratory_scorecard.csv',index=False)
    pd.DataFrame(one,index=MONTHS).to_csv(OUT/'complete_monthly_returns_1x.csv',index_label='month')
    unique=[]
    for k,r in one.items():
        if not any(np.allclose(r,s,rtol=0,atol=1e-11) for s in unique):unique.append(r)
    meta={'status':'Post-result exploration; all original IS data already seen. No OOS.',
          'listed_return_series':len(one),'distinct_return_series':len(unique),
          'inference':'19999 circular three-month paired bootstrap draws; centered mean statistics standardized by bootstrap SE; two-sided max-absolute-t across every listed series, duplicates retained harmlessly. Does not correct all historical decisions or research selection. Pointwise CIs are not familywise.',
          'comparison':'Two-sided mean-return differences vs registered P0 on common108 months. This is not a Sharpe test and exposures differ.',
          'registered_sha256':hashlib.sha256((ROOT/'results_is.json').read_bytes()).hexdigest()}
    (OUT/'search_inventory.json').write_text(json.dumps(meta,indent=2)+'\n')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.titleweight':'bold','figure.facecolor':'#faf9f5','axes.facecolor':'#faf9f5'})
    fig,axes=plt.subplots(2,2,figsize=(14,9.5),layout='constrained')
    ax=axes[0,0]
    vals=np.array([852015.625,-610953.125,-57537.5,183525.])
    bottoms=[0,852015.625,241062.5,0]
    colors=['#267d6a','#c35145','#b59053','#4b607b']
    for i,(v,bot,c) in enumerate(zip(vals,bottoms,colors)):
        ax.bar(i,v,bottom=bot,color=c,width=.62)
        top=bot+v
        ax.text(i,top+(18000 if v>=0 else -33000),f'{v/1000:+,.0f}k',ha='center',va='bottom' if v>=0 else 'top',fontweight='bold')
    ax.set_xticks(range(4),['Before month-end\ngross','First new-month\nsession, gross','Round-trip\ncosts','Original P0\nnet'],fontsize=10)
    ax.set_ylim(-65000,1e6);ax.set_ylabel('Cumulative USD on fixed $10M NAV')
    ax.set_title('1. One session gives back most of the gain',loc='left')
    ax.axhline(0,color='#777',lw=.6)
    ax=axes[0,1]
    for k,label,col in [('registered_PG','Original gate PG','#c35145'),('registered_P0','Original P0','#7d8797'),
                        ('timing_exit_L','Same P0 positions, exit month-end','#267d6a')]:
        ax.plot(pd.to_datetime(MONTHS),np.cumsum(one[k])*100,label=label,lw=2,color=col)
    ax.axhline(0,color='#777',lw=.6);ax.set_ylabel('Cumulative return, % of fixed NAV')
    ax.set_title('2. Timing matters more than the original gate',loc='left');ax.legend(fontsize=9)
    ax=axes[1,0]
    labels=['Baseline','Exit at\nmonth-end','Reverse for\nfirst session','Two stages:\nflip at month-end','Always long ES\nfirst session']
    keys=['baseline','exit_L','reverse_F1','flip_at_L','always_long_ES_F1']
    q=pd.read_csv(OUT/'timing_regimes/matched_quote_summary.csv').query("segment=='common'").set_index('variant')
    ii=np.arange(len(keys));ax.bar(ii-.17,[q.at[k,'sharpe'] for k in keys],.32,color='#267d6a',label='Normal costs')
    ax.bar(ii+.17,[q.at[k,'sharpe_2x'] for k in keys],.32,color='#b59053',label='Doubled costs')
    ax.set_xticks(ii,labels,fontsize=9);ax.set_ylim(0,1.08);ax.set_ylabel('Annualized Sharpe')
    ax.set_title('3. Improvement survives matched bid/ask fills',loc='left');ax.legend(fontsize=9)
    ax.text(.01,.98,'Same 95 events; all 108 months retained',transform=ax.transAxes,va='top',fontsize=9,color='#666')
    ax=axes[1,1]
    # Profit decomposition of gate decisions, independent of endpoint experiment.
    x=np.arange(2);keep=np.array([121061.25,-158040.]);reject=np.array([273132.5,-52628.75])
    ax.bar(x-.18,keep/1000,.34,label='Kept by gate',color='#4b607b')
    ax.bar(x+.18,reject/1000,.34,label='Rejected by gate',color='#c35145')
    ax.set_xticks(x,['Long ES / short ZN','Short ES / long ZN']);ax.axhline(0,color='#777',lw=.6)
    ax.set_ylabel('Net P&L, USD thousands');ax.set_title('4. The gate missed profitable large trades',loc='left');ax.legend(fontsize=9)
    fig.suptitle('Why the strategy failed — and the timing hypothesis worth testing\nExploratory IS evidence, Oct 2015–Sep 2024. Future-period validation remains unopened.',fontsize=17,fontweight='bold')
    fig.savefig(OUT/'failure_diagnosis.png',dpi=170);plt.close(fig)
    focus=score[score.candidate.isin(['registered_P0','registered_PG','timing_exit_L','timing_F1_only','followup_flip_at_L',
                                    'followup_always_long_ES_F1','quotes_exit_L','quotes_flip_at_L','model_event_quarter_interactions'])]
    print(meta)
    print(focus.to_string(index=False))

if __name__=='__main__':main()
