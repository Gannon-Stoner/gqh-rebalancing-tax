"""Post-observation horizon attribution. Execute only on existing IS."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm
from gqh.config import frozen_config
from gqh.pipeline import prepare
from gqh.engine import size_events,run_row
from gqh.reproduce import clean
from analyze import features,walk,MONTHS,ERAS,sr,robust_summary

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
CFG=frozen_config()

def main():
    panels={r:pd.read_parquet(ROOT/'data'/'derived'/f'settlements_{r}.parquet',filters=[('date','<=',CFG.is_end)]) for r in ('ES','ZN')}
    w=prepare(panels,start=CFG.is_start,end=CFG.is_end,cfg=CFG)
    e=w.events.copy();m=w.sched.set_index('month');z=size_events(e,w.es,w.zn,cfg=CFG)
    full=e.copy();pre=e.copy()
    pre['exit']=pre.month.map(m.L)
    for i,r in pre.iterrows():
        if pd.isna(r.es_id) or pd.isna(r.zn_id):continue
        pre.at[i,'es_exit']=w.es.price(int(r.es_id),r.exit)
        pre.at[i,'zn_exit']=w.zn.price(int(r.zn_id),r.exit)
    pre['Y']=pre.s*(np.log(pre.es_exit/pre.es_entry)-np.log(pre.zn_exit/pre.zn_entry))/(pre.sigma*np.sqrt(5))
    pre['X_hold']=pre.s*pre.Y*pre.sigma*np.sqrt(5)
    pre['valid']=pre.valid&np.isfinite(pre.Y)
    e['Y_pre']=pre.Y;e['Y_F1']=e.Y-pre.Y
    assert np.allclose((e.Y_pre+e.Y_F1)[e.valid],e.Y[e.valid])
    e.to_csv(OUT/'horizon_signal_panel.csv',index=False)
    coefs=[]
    for period,mask in [('all_IS',e.valid),('common',e.valid&e.month.isin(MONTHS)),
                        ('2021_24',e.valid&(e.month>=pd.Period('2021-01','M')))]:
        for y in ['Y','Y_pre','Y_F1']:
            for terms in [['dose','QE'],['dose','A','QE'],['dose','A','QE','s']]:
                g=e[mask].dropna(subset=[y]+terms)
                fit=sm.OLS(g[y].astype(float),sm.add_constant(g[terms].astype(float))).fit(cov_type='HC3')
                for term in fit.params.index:
                    coefs.append({'period':period,'target':y,'model':'+'.join(terms),'term':term,
                      'estimate':fit.params[term],'se_hc3':fit.bse[term],'p_two_sided':fit.pvalues[term],'n':len(g)})
    pd.DataFrame(coefs).to_csv(OUT/'horizon_coefficients.csv',index=False)
    f=features(pre,w.ref);ff=features(full,w.ref)
    pred_old,_,_=walk(ff,['dose','A'],0)
    pred_ols,_,_=walk(f,['dose','A'],0)
    pred_ridge,_,_=walk(f,['dose','A'],20)
    masks={'P0_exit_L':pre.valid.to_numpy(),
           'PG_original_decisions_exit_L':pred_old>z.hurdle.to_numpy(),
           'PG_refit_exit_L_OLS':pred_ols>z.hurdle.to_numpy(),
           'PG_refit_exit_L_ridge20':pred_ridge>z.hurdle.to_numpy()}
    out={};rets={};rets2={}
    for name,mask in masks.items():
        l=run_row(pre,z,mask&pre.month.isin(MONTHS).to_numpy(),row=name,cfg=CFG)
        l.to_csv(OUT/f'{name}_ledger.csv',index=False)
        r=l.set_index('month').ret.reindex(MONTHS,fill_value=0)
        r2=(l.set_index('month').pnl-l.set_index('month').cost).reindex(MONTHS,fill_value=0)/CFG.reference_nav
        rets[name]=r.to_numpy();rets2[name]=r2.to_numpy()
        out[name]={'net_usd':r.sum()*CFG.reference_nav,'sharpe':sr(r),'sharpe_2x':sr(r2),
                   'trades':int(l.traded.sum()),'robustness':robust_summary(r.to_numpy()),
                   'eras':{k:sr(r.loc[lo:hi]) for k,(lo,hi) in ERAS.items()}}
    pd.DataFrame(rets,index=MONTHS.astype(str)).to_csv(OUT/'horizon_monthly_1x.csv',index_label='month')
    pd.DataFrame(rets2,index=MONTHS.astype(str)).to_csv(OUT/'horizon_monthly_2x.csv',index_label='month')
    (OUT/'horizon_summary.json').write_text(json.dumps(clean(out),indent=2)+'\n')
    print(json.dumps(clean(out),indent=2))
    print(pd.DataFrame(coefs).query("model == 'dose+QE' and term == 'dose'").to_string(index=False))

if __name__=='__main__':main()
