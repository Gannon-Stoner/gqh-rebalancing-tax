"""IS raw OI publication metadata audit. Drop OOS trade dates before examining any value."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import databento as db
from gqh.pipeline import prepare
from gqh.config import frozen_config
from gqh.reproduce import clean

root=Path(__file__).resolve().parents[3]; out=Path(__file__).resolve().parent;cfg=frozen_config()
panels={r:pd.read_parquet(root/f'data/derived/settlements_{r}.parquet',filters=[('date','<=',cfg.is_end)]) for r in ('ES','ZN')}
w=prepare(panels,start=cfg.is_start,end=cfg.is_end,cfg=cfg)
iids=set(pd.concat([p.instrument_id for p in panels.values()]).unique())
parts=[]
for chunk in db.DBNStore.from_file(root/'data/raw/is_statistics.dbn.zst').to_df(count=500000,map_symbols=False):
    # Only inspect IS outright OI metadata. All dates on/after OOS boundary discarded first.
    chunk=chunk[chunk.ts_ref<cfg.oos_start.tz_localize('UTC')]
    chunk=chunk[(chunk.stat_type==9)&chunk.instrument_id.isin(iids)]
    if len(chunk):
        c=chunk[['instrument_id','ts_ref','quantity','update_action','sequence']].reset_index()
        c['date']=c.ts_ref.dt.tz_localize(None).dt.normalize()
        parts.append(c.drop(columns='ts_ref'))
st=pd.concat(parts,ignore_index=True).sort_values(['ts_recv','sequence'],kind='mergesort')
last=st.groupby(['date','instrument_id'],sort=False).tail(1)
# A last DELETE removes the key. Existing daily_quantity also handles DELETE after prior NEW.
last=last[last.update_action==1].set_index(['date','instrument_id'])
late=[];refs=[];changed=[]
for ix,dt in enumerate(w.sessions[1:],start=1):
    prev=w.sessions[ix-1]
    cutoff=(dt+pd.Timedelta(hours=15)).tz_localize('America/New_York').tz_convert('UTC')
    for leg in ['es','zn']:
        iid=w.ref.at[dt,f'{leg}_id']
        if pd.isna(iid) or (prev,int(iid)) not in last.index:continue
        v=last.loc[(prev,int(iid))]
        rec={'date':dt,'weight_date':prev,'leg':leg,'iid':int(iid),'published':v.ts_recv,'hours_after_15_ET':(v.ts_recv-cutoff).total_seconds()/3600}
        refs.append(rec)
        if v.ts_recv>cutoff:
            hist=st[(st.date==prev)&(st.ts_recv<=cutoff)]
            hs=hist.groupby('instrument_id',sort=False).tail(1)
            hs=hs[hs.update_action==1]
            panel=w.es if leg=='es' else w.zn
            eligible=panel.meta[(panel.meta.expiration>=dt) if leg=='es' else (panel.meta.first_position_day>dt)]
            hs=hs[hs.instrument_id.isin(eligible.index)]
            hs=hs[hs.instrument_id.isin(panel.settle.loc[prev].dropna().index)]
            if len(hs):
                cand=hs.sort_values('quantity',ascending=False).iloc[0]
                rec['available_iid']=int(cand.instrument_id);rec['changed_selection']=int(cand.instrument_id)!=int(iid)
            else:rec['available_iid']=None;rec['changed_selection']=None
            late.append(rec)
# Actual decision/entry as-of: feature selection entire reference history needs no OI revision after signal-use deadline.
feature_late=[]
for kind,ev in [('event',w.events),('pseudo',w.pseudos)]:
 for e in ev[ev.valid].itertuples():
    cutoff=(e.entry+pd.Timedelta(hours=15)).tz_localize('America/New_York').tz_convert('UTC')
    for rec in late:
      if rec['date']<=e.dec and rec['published']>cutoff:
        feature_late.append({'kind':kind,'month':e.month,**rec})
# Event ES OI at anchor must be known by actual decision/entry.
event_late=[]
for kind,ev in [('event',w.events),('pseudo',w.pseudos)]:
 for e in ev[ev.valid].itertuples():
    if (e.progress_start,int(e.es_id)) not in last.index:continue
    pub=last.loc[(e.progress_start,int(e.es_id))].ts_recv
    cutoff=(e.entry+pd.Timedelta(hours=15)).tz_localize('America/New_York').tz_convert('UTC')
    if pub>cutoff:event_late.append({'kind':kind,'month':e.month,'anchor':e.progress_start,'published':pub})
res={'OI_rows':len(st),'selected_reference_OI_records':len(refs),'after_next_15_ET_count':len(late),'after_next_15_ET_records':late,'late_for_actual_signal_use':feature_late,'event_contract_OI_late_for_use':event_late,'publication_hour_ET_quantiles':st.ts_recv.dt.tz_convert('America/New_York').dt.hour.quantile([0,.1,.5,.9,1]).to_dict()}
(out/'oi_publication_results.json').write_text(json.dumps(clean(res),indent=2)+'\n')
print(json.dumps(clean(res),indent=2))
