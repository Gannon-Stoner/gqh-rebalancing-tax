"""Post-result correctness audit. Reads IS-only parquet filters; never calls reproduce or writes frozen artifacts."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from gqh.pipeline import prepare
from gqh.strategy import run_strategy
from gqh.quotes import QuoteBook
from gqh.config import frozen_config
from gqh.gate import ols
from gqh.metrics import monthly_returns
from gqh.stats import sharpe
from gqh.reproduce import clean
from gqh.calendar import is_early_close
from gqh.capacity import capacity_table, capacity_summary
from gqh.data import bar_volume

root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
cfg=frozen_config()
panels={r:pd.read_parquet(root/f'data/derived/settlements_{r}.parquet',filters=[('date','<=',cfg.is_end)]) for r in ('ES','ZN')}
end=cfg.is_end+pd.Timedelta(days=1)
bbo=pd.read_parquet(root/'data/derived/bbo_1m_close.parquet',filters=[('ts_et','<',end)])
ohlcv=pd.read_parquet(root/'data/derived/ohlcv_1m_close.parquet',filters=[('ts_et','<',end)])
assert all(p['date'].max()<=cfg.is_end for p in panels.values())
assert bbo.ts_et.max()<end and ohlcv.ts_et.max()<end
w=prepare(panels,start=cfg.is_start,end=cfg.is_end,cfg=cfg)
r=run_strategy(w.events,w.pseudos,w.es,w.zn,quote=QuoteBook(bbo),cfg=cfg)
months=pd.period_range(r.segment_start,w.events.month.max(),freq='M')
pg=r.ledgers['PG',1.0];px=r.ledgers['PX',1.0];p0=r.ledgers['P0',1.0]
metrics=lambda led:{'trades':int(led.traded.sum()),'pnl':float(led.pnl.sum()),'sharpe':sharpe(monthly_returns(led,months))}
res={'scope':{'max_market_date':str(max(p.date.max() for p in panels.values())),'last_month':str(w.events.month.max()),'segment_start':str(r.segment_start),'n_months':len(months)}}
# Matched sample comparison, retaining zero-return months.
matched=pg.copy()
excluded=pg.traded & ~px.traded
matched.loc[~px.traded,['pnl','ret','cost']]=0.
matched.loc[~px.traded,'traded']=False
res['matched_execution']={'PG_all':metrics(pg),'PG_on_PX_dates':metrics(matched),'PX':metrics(px),'excluded_PG':pg.loc[excluded,['month','entry','exit','pnl','pnl_es','pnl_zn','cost']].to_dict('records'),'matched_PX_minus_PG_pnl':float(px.pnl.sum()-matched.pnl.sum()),'matched_PX_minus_PG_sharpe':float(metrics(px)['sharpe']-metrics(matched)['sharpe'])}
# Last forecast model in JSON versus actual full completed-IS fit.
res['final_coefficients']={}
for name,panel,features in [('PG',w.events,['dose','A']),('PD',w.events,['dose']),('PP',w.pseudos,['dose','A'])]:
    q=panel[panel.valid & (panel.exit<=cfg.is_end)]
    b=ols(q[features].to_numpy(),q.Y.to_numpy())
    g=r.gates[name].dropna(subset=['yhat']).iloc[-1]
    old=g[[f'coef_{x}' for x in ['const',*features]]].to_numpy(dtype=float)
    res['final_coefficients'][name]={'last_forecast_n_train':int(g.n_train),'completed_IS_n':len(q),'last_forecast_coefficients':old.tolist(),'all_completed_IS_coefficients':b.tolist(),'last_completed_event':str(q.month.max())}
# Examine whether chosen final settlement marks were available by next-day entry.
late=[]
for kind,panel in [('event',w.events),('pseudo',w.pseudos)]:
  for e in panel[panel.valid].itertuples():
    deadline=(e.entry+pd.Timedelta(hours=15)).tz_localize('America/New_York').tz_convert('UTC')
    # At minimum, both held-contract decision settlements are needed for sizing and progress.
    for leg in ['ES','ZN']:
      p=panels[leg]
      h=p[(p.date==e.dec)&(p.instrument_id==getattr(e,f'{leg.lower()}_id'))].iloc[0]
      recv=pd.Timestamp(h.settle_ts_recv)
      if recv>deadline:
        late.append({'kind':kind,'month':e.month,'leg':leg,'use':'held_decision_price','mark_date':e.dec,'published':recv,'entry_15_ET':deadline,'hours_late':(recv-deadline).total_seconds()/3600})
    # Drift and sigma use all reference marks. Check every required reference mark in that month's drift.
    prevL=w.sched.set_index('month').loc[e.month,'prev_L']
    seg=w.ref[(w.ref.index>prevL)&(w.ref.index<=e.dec)]
    for dt,t in seg.iterrows():
      ix=w.sessions.get_loc(dt)
      prev=w.sessions[ix-1]
      for leg in ['ES','ZN']:
        iid=t[f'{leg.lower()}_id'];p=panels[leg]
        for mark in [dt,prev]:
          h=p[(p.date==mark)&(p.instrument_id==iid)]
          if len(h):
            recv=pd.Timestamp(h.iloc[0].settle_ts_recv)
            if recv>deadline:
              late.append({'kind':kind,'month':e.month,'leg':leg,'use':'reference_drift','mark_date':mark,'published':recv,'entry_15_ET':deadline,'hours_late':(recv-deadline).total_seconds()/3600})
res['settlement_availability']={'late_count':len(late),'late_records':late}
# Settlement capacity uses nonexistent regular clock on early closes; identify all zero volumes.
vol=bar_volume(ohlcv)
cap=capacity_table(pg,w.events,vol,mode='settle',cfg=cfg)
merge=cap.merge(pg[['month','entry','exit']],on='month')
merge['early_fill']=merge.entry.map(is_early_close)|merge.exit.map(is_early_close)
res['capacity_early_close']={'all':capacity_summary(cap),'excluding_early_closes':capacity_summary(merge[~merge.early_fill]),'early_rows':merge[merge.early_fill].to_dict('records'),'zero_capacity_rows':merge[merge.max_nav_1pct==0].to_dict('records')}
# Data and bookkeeping invariants: return sign and dates independently computed from held prices.
ev=w.events[w.events.valid].copy()
manual=np.log(ev.es_exit/ev.es_entry)-np.log(ev.zn_exit/ev.zn_entry)
res['invariants']={'events':len(ev),'valid_pseudos':int(w.pseudos.valid.sum()),'max_abs_Y_independent_error':float(np.max(np.abs(ev.Y-ev.s*manual/(ev.sigma*np.sqrt(5))))),'PG_pnl_sum':float(pg.pnl.sum()),'P0_pnl_sum':float(p0.pnl.sum()),'decision_before_entry':bool((ev.dec<ev.entry).all()),'entry_before_exit':bool((ev.entry<ev.exit).all())}
# Gate decomposition by selection, decision quarter, and direction as no-change factual diagnosis.
comp=w.events.copy()
for c in ['yhat','coef_const','coef_dose','coef_A','n_train','hurdle']:
  comp[c]=r.gates['PG'][c]
comp['P0_pnl']=p0.pnl;comp['PG_trade']=pg.traded;comp['P0_trade']=p0.traded
comp=comp[comp.month>=r.segment_start]
comp['forecast_intercept']=comp.coef_const
comp['forecast_dose']=comp.coef_dose*comp.dose
comp['forecast_progress']=comp.coef_A*comp.A
res['gate_selection']={'selected':{'n':int(comp.PG_trade.sum()),'pnl':float(comp.loc[comp.PG_trade,'P0_pnl'].sum()),'mean_Y':float(comp.loc[comp.PG_trade,'Y'].mean())},'rejected_tradable':{'n':int((~comp.PG_trade&comp.P0_trade).sum()),'pnl':float(comp.loc[~comp.PG_trade&comp.P0_trade,'P0_pnl'].sum()),'mean_Y':float(comp.loc[~comp.PG_trade&comp.P0_trade,'Y'].mean())},'forecast_correlations':{c:float(comp[c].corr(comp.Y)) for c in ['yhat','dose','A']},'coef_A_negative_share':float((comp.coef_A<0).mean()),'forecast_component_std':{c:float(comp[c].std()) for c in ['forecast_intercept','forecast_dose','forecast_progress']}}
comp.assign(month=comp.month.astype(str)).to_csv(out/'event_audit.csv',index=False)
(out/'audit_results.json').write_text(json.dumps(clean(res),indent=2)+'\n')
print(json.dumps(clean({k:v for k,v in res.items() if k not in ['capacity_early_close']}),indent=2))
print('CAPACITY EARLY',json.dumps(clean(res['capacity_early_close']),indent=2))
