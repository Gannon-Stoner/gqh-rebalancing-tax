"""Independent same-contract, same-quantity audit of the original F1 holding increment."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
from gqh.pipeline import prepare
from gqh.strategy import run_strategy
from gqh.quotes import QuoteBook
from gqh.config import frozen_config
from gqh.reproduce import clean
from gqh.stats import sharpe

root=Path(__file__).resolve().parents[3];out=Path(__file__).resolve().parent;cfg=frozen_config()
panels={r:pd.read_parquet(root/f'data/derived/settlements_{r}.parquet',filters=[('date','<=',cfg.is_end)]) for r in ('ES','ZN')}
w=prepare(panels,start=cfg.is_start,end=cfg.is_end,cfg=cfg)
bbo=pd.read_parquet(root/'data/derived/bbo_1m_close.parquet',filters=[('ts_et','<',cfg.is_end+pd.Timedelta(days=1))])
q=QuoteBook(bbo);run=run_strategy(w.events,w.pseudos,w.es,w.zn,cfg=cfg)
pg=run.ledgers['PG',1.0];p0=run.ledgers['P0',1.0];sig=w.events.set_index('month');sched=w.sched.set_index('month')
recs=[]
for t in p0[p0.traded].itertuples():
    ev=sig.loc[t.month];L=sched.loc[t.month,'L'];F1=t.exit
    rec={'month':t.month,'s':t.s,'L':L,'F1':F1,'PG_selected':bool(pg[pg.month==t.month].traded.iloc[0]),'P0_pnl':t.pnl,
         'consecutive_qualifying_sessions':bool(w.sessions[w.sessions.get_loc(F1)-1]==L),'F1_following_calendar_month':bool(F1.to_period('M')==t.month+1)}
    for leg,p in [('es',w.es),('zn',w.zn)]:
        iid=int(ev[f'{leg}_id']);n=getattr(t,f'q_{leg}');mult=cfg.multipliers[leg.upper()]
        a,b=p.price(iid,L),p.price(iid,F1)
        rec.update({f'{leg}_id':iid,f'{leg}_symbol':p.meta.at[iid,'symbol'],f'{leg}_q':n,f'{leg}_L':a,f'{leg}_F1':b,f'{leg}_F1_gross':n*mult*(b-a),f'{leg}_tradable_F1':bool(p.tradable_through(iid,F1))})
        qa,qb=q(iid,L+pd.Timedelta(hours=15,minutes=59)),q(iid,F1+pd.Timedelta(hours=15,minutes=59))
        rec[f'{leg}_F1_mid_gross']=n*mult*((sum(qb)/2)-(sum(qa)/2)) if qa and qb else np.nan
        # Increment if closing the held signed position at L versus F1; both liquidations hit same side.
        close_a=qa[0] if n>0 and qa else qa[1] if qa else np.nan
        close_b=qb[0] if n>0 and qb else qb[1] if qb else np.nan
        rec[f'{leg}_F1_liquidation_gross']=n*mult*(close_b-close_a)
    rec['contracts_tradable_F1']=rec['es_tradable_F1'] and rec['zn_tradable_F1']
    rec['F1_gross']=rec['es_F1_gross']+rec['zn_F1_gross']
    rec['F1_mid_gross']=rec['es_F1_mid_gross']+rec['zn_F1_mid_gross']
    rec['F1_liquidation_gross']=rec['es_F1_liquidation_gross']+rec['zn_F1_liquidation_gross']
    rec['P0_exit_L_net']=t.pnl-rec['F1_gross']
    recs.append(rec)
df=pd.DataFrame(recs);months=pd.period_range(run.segment_start,w.events.month.max(),freq='M')
summary=lambda d:{'n':len(d),'F1_gross':d.F1_gross.sum(),'ES_F1_gross':d.es_F1_gross.sum(),'ZN_F1_gross':d.zn_F1_gross.sum(),'P0_net':d.P0_pnl.sum(),'same_positions_exit_L_net':d.P0_exit_L_net.sum(),'F1_positive_share':float((d.F1_gross>0).mean())}
matched=df[df.F1_mid_gross.notna()]
res={'all':summary(df),'by_direction':{str(s):summary(g) for s,g in df.groupby('s')},'PG_only':summary(df[df.PG_selected]),'quote_validation':{'matched_n':len(matched),'settlement_F1_gross_matched':matched.F1_gross.sum(),'simultaneous_1559_mid_F1_gross':matched.F1_mid_gross.sum(),'same_side_1559_liquidation_F1_gross':matched.F1_liquidation_gross.sum(),'corr_mid_vs_settlement':matched.F1_mid_gross.corr(matched.F1_gross),'unmatched_months':df[df.F1_mid_gross.isna()].month.tolist()},'invariants':{'all_dates_consecutive_qualifying':bool(df.consecutive_qualifying_sessions.all()),'all_F1_following_calendar_month':bool(df.F1_following_calendar_month.all()),'all_contracts_tradable_F1':bool(df.contracts_tradable_F1.all()),'same_contracts_and_original_quantities_used':True},'top_F1_losses':df.nsmallest(12,'F1_gross')[['month','s','es_symbol','zn_symbol','F1_gross','es_F1_gross','zn_F1_gross','F1_mid_gross']].to_dict('records'),'sharpe_original':sharpe(df.set_index('month').P0_pnl.reindex(months,fill_value=0)/cfg.reference_nav),'sharpe_same_position_exit_L':sharpe(df.set_index('month').P0_exit_L_net.reindex(months,fill_value=0)/cfg.reference_nav)}
df.assign(month=df.month.astype(str)).to_csv(out/'f1_event_audit.csv',index=False)
(out/'f1_audit_results.json').write_text(json.dumps(clean(res),indent=2)+'\n')
print(json.dumps(clean(res),indent=2))
