"""Exploratory post-result IS attribution; never reads OOS or changes frozen files.

Run: .venv/bin/python research/2026-10-03-failure-analysis/gate_attribution/analyze.py
All six ablations below were specified before looking at their results. They are
diagnostics, not registered tests, validated strategies, or a replacement result.
"""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear
from scipy.stats import spearmanr
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from gqh.config import frozen_config
from gqh.pipeline import prepare
from gqh.strategy import run_strategy
from gqh.engine import size_events, run_row
from gqh.reproduce import clean

OUT = Path(__file__).resolve().parent


def sharpe(pnl):
    a = np.asarray(pnl, float)
    return np.sqrt(12) * a.mean() / a.std(ddof=1) if a.std(ddof=1) > 0 else np.nan


def group_summary(g):
    return {"n": len(g), "p0_trades": int(g.p0_traded.sum()), "pg_trades": int(g.pg_traded.sum()),
            "p0_net": g.p0_pnl.sum(), "pg_net": g.pg_pnl.sum(),
            "gate_minus_baseline": (g.pg_pnl-g.p0_pnl).sum(),
            "p0_gross": (g.p0_pnl+g.p0_cost).sum(), "pg_gross": (g.pg_pnl+g.pg_cost).sum(),
            "p0_cost": g.p0_cost.sum(), "pg_cost": g.pg_cost.sum(),
            "mean_Y": g.Y.mean(), "mean_forecast": g.yhat.mean(), "mean_dose":g.dose.mean(),
            "mean_A":g.A.mean(), "win_rate":(g.loc[g.p0_traded, "p0_pnl"]>0).mean(),
            "p0_es_pnl":g.p0_pnl_es.sum(), "p0_zn_pnl":g.p0_pnl_zn.sum()}


def describe(df, by):
    return {str(k):group_summary(g) for k,g in df.groupby(by, observed=True)}


def hac_reg(df, features, target="Y"):
    d = df.dropna(subset=[target,*features])
    fit = sm.OLS(d[target].astype(float), sm.add_constant(d[features].astype(float), has_constant="add")).fit(cov_type="HAC",cov_kwds={"maxlags":3})
    return {"n":len(d),"r2":fit.rsquared,"coef":fit.params.to_dict(),"p_two_sided_hac":fit.pvalues.to_dict(),"ci95_hac":fit.conf_int().to_dict(orient="index")}


def forecasts(events):
    names = ["historical_mean", "direction_mean", "direction_ols", "trailing60_ols", "constrained_ols", "no_progress"]
    pred = pd.DataFrame(np.nan, index=events.index, columns=names)
    all_valid = events.valid & events.Y.notna()
    for i, row in events.iterrows():
        hist = events[all_valid & (events.exit < row.dec)]
        if len(hist) < 60 or not row.valid:
            continue
        pred.loc[i,"historical_mean"] = hist.Y.mean()
        same = hist[hist.s==row.s]
        pred.loc[i,"direction_mean"] = same.Y.mean() if len(same)>=20 else hist.Y.mean()
        for name, feats, h in [("direction_ols",["dose","A","s"],hist),
                               ("trailing60_ols",["dose","A"],hist.tail(60)),
                               ("no_progress",["dose"],hist)]:
            x = np.column_stack([np.ones(len(h)),h[feats].astype(float).to_numpy()])
            coef = np.linalg.lstsq(x,h.Y.to_numpy(),rcond=None)[0]
            pred.loc[i,name] = np.r_[1.,row[feats].astype(float).to_numpy()]@coef
        x=np.column_stack([np.ones(len(hist)),hist[["dose","A"]].to_numpy()])
        coef=lsq_linear(x,hist.Y.to_numpy(),bounds=([-np.inf,0,-np.inf],[np.inf,np.inf,0])).x
        pred.loc[i,"constrained_ols"]=np.r_[1.,row[["dose","A"]].to_numpy()]@coef
    return pred


def main():
    cfg=frozen_config()
    frozen = [ROOT / p for p in ["results_is.json","trials.jsonl","HYPOTHESIS.md","config/frozen.yaml"]]
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen}
    # Read no minute/factor/OOS data. Restrict settlement parquet scans by date.
    panels={r:pd.read_parquet(ROOT/f"data/derived/settlements_{r}.parquet",filters=[("date","<=",cfg.is_end)]) for r in ("ES","ZN")}
    assert all(d.date.max()<=cfg.is_end for d in panels.values())
    w=prepare(panels,start=cfg.is_start,end=cfg.is_end,cfg=cfg)
    assert set(w.events["sample"])=={"IS"}
    run=run_strategy(w.events,w.pseudos,w.es,w.zn,cfg=cfg)
    sizes=size_events(w.events,w.es,w.zn,cfg=cfg)
    d=w.events.copy().join(run.gates["PG"])
    for key in ["notional","cost_1x","cap_bound","below_one_lot"]:
        d[key]=sizes[key]
    for name in ["P0","PG","PD","PE"]:
        led=run.ledgers[name,1.]
        for c in ["traded","pnl","cost","pnl_es","pnl_zn","rounding","ret"]:
            d[f"{name.lower()}_{c}"]=led[c]
    d["risk_usd"]=d.notional*d.sigma*np.sqrt(5)
    d["expected_gross_usd"]=d.risk_usd*d.yhat
    d["expected_net_usd"]=d.expected_gross_usd-d.cost_1x
    d["year"]=pd.PeriodIndex(d.month).year
    d["era"]=np.where(d.year<=2020,"through_2020","2021_2024")
    d["direction"]=np.where(d.s==1,"long_ES","short_ES")
    d["decision"]=np.where(d.pg_traded,"kept",np.where(d.p0_traded,"rejected","untradeable"))
    d["dose_bin"]=pd.cut(d.dose,[-.001,.5,1,1.5,2.001])
    d["A_bin"]=pd.cut(d.A,[-np.inf,-1,0,1,np.inf])
    d["margin"]=d.yhat-d.hurdle
    d["margin_bin"]=pd.cut(d.margin,[-np.inf,-.1,0,.1,np.inf])
    d["prev_mean"]=np.nan
    for i,row in d.iterrows():
        hist=d[d.valid & (d.exit<row.dec)]
        if len(hist)>=60:d.loc[i,"prev_mean"]=hist.Y.mean()
    all_events=d.copy()
    d=d[d.month>=run.segment_start].copy()
    t=d[d.p0_traded].copy()
    pred=forecasts(w.events).loc[d.index]
    d=d.join(pred.add_prefix("alternative_"))
    saved=json.loads((ROOT/"results_is.json").read_text())
    assert abs(sharpe(d.pg_pnl)-saved["rows_IS"]["rows"]["PG@1x"]["sharpe"])<1e-9
    assert abs(sharpe(d.p0_pnl)-saved["rows_IS"]["rows"]["P0@1x"]["sharpe"])<1e-9
    result={"scope":"Exploratory attribution of existing IS only; no OOS read/unlock; no source or frozen file change.",
            "registered_result_reproduced":True,"n_months":len(d),"dates":[str(d.month.min()),str(d.month.max())],
            "overall":group_summary(d),"decision":describe(t,"decision"),
            "direction_decision":describe(t,["direction","decision"]),"era_decision":describe(t,["era","decision"]),
            "year":describe(d,"year"),"dose_decision":describe(t,["dose_bin","decision"]),
            "progress_decision":describe(t,["A_bin","decision"]),"quarter_decision":describe(t,["QE","decision"]),
            "margin_bins":describe(t,"margin_bin"),
            "coefficient_summary":{c:{"min":t[c].min(),"max":t[c].max(),"mean":t[c].mean(),"positive_share":(t[c]>0).mean(),"negative_share":(t[c]<0).mean(),"first":t.iloc[0][c],"last":t.iloc[-1][c]} for c in ["coef_const","coef_dose","coef_A"]},
            "coefficient_yearly_mean":t.groupby("year")[["coef_const","coef_dose","coef_A","yhat","hurdle"]].mean().to_dict(orient="index")}
    y=t.Y.to_numpy();p=t.yhat.to_numpy();mean=t.prev_mean.to_numpy()
    result["forecast_skill"]={"mean_yhat":p.mean(),"mean_Y":y.mean(),"std_yhat":p.std(ddof=1),"std_Y":y.std(ddof=1),
        "pearson":np.corrcoef(p,y)[0,1],"spearman":spearmanr(p,y).statistic,"mse":np.mean((p-y)**2),
        "historical_mean_mse":np.mean((mean-y)**2),"r2_vs_past_mean":1-np.sum((p-y)**2)/np.sum((mean-y)**2),
        "r2_vs_zero":1-np.sum((p-y)**2)/np.sum(y*y),"calibration_hac":hac_reg(t,["yhat"]),
        "expected_selected_net":t.loc[t.pg_traded,"expected_net_usd"].sum(),"actual_selected_net":t.pg_pnl.sum(),
        "expected_rejected_net":t.loc[~t.pg_traded,"expected_net_usd"].sum(),"actual_rejected_net":t.loc[~t.pg_traded,"p0_pnl"].sum()}
    result["forecast_population_reconciliation"]={"all_valid_evaluation_events":{"n":len(d),"correlation":d[["Y","yhat"]].corr().iloc[0,1]},
        "baseline_tradable_events":{"n":len(t),"correlation":t[["Y","yhat"]].corr().iloc[0,1]},
        "gate_traded_events":{"n":int(t.pg_traded.sum()),"correlation":t.loc[t.pg_traded,["Y","yhat"]].corr().iloc[0,1]},
        "reason":"Four valid events round below one contract in one leg. All 108 valid events include these; 104 tradable events exclude them."}
    result["regressions"]={"all_valid_IS":hac_reg(all_events[all_events.valid],["dose","A"]),
        "trading_segment":hac_reg(t,["dose","A"]),"with_direction":hac_reg(t,["dose","A","s"]),
        **{f"segment_{era}":hac_reg(g,["dose","A"]) for era,g in t.groupby("era")}}
    first_train=all_events[all_events.valid & (all_events.exit<t.iloc[0].dec)]
    result["regressions"]["first_decision_training"]=hac_reg(first_train,["dose","A"])
    result["feature_correlations"]=t[["dose","A","s","sigma","Y","yhat","risk_usd"]].corr().to_dict()
    uncertainty=[]
    for i,row in t.iterrows():
        h=all_events[all_events.valid & (all_events.exit<row.dec)]
        x=sm.add_constant(h[["dose","A"]],has_constant="add")
        fit=sm.OLS(h.Y,x).fit(cov_type="HAC",cov_kwds={"maxlags":3})
        xi=np.r_[1.,row[["dose","A"]].to_numpy(dtype=float)]
        se=float(np.sqrt(xi@fit.cov_params().to_numpy()@xi))
        uncertainty.append({"month":str(row.month),"mean_forecast_se_hac":se,"forecast":row.yhat,
                            "hurdle":row.hurdle,"z_to_hurdle":(row.yhat-row.hurdle)/se,
                            "mean_ci90_low":row.yhat-1.645*se,"mean_ci90_high":row.yhat+1.645*se})
    u=pd.DataFrame(uncertainty)
    u.to_csv(OUT/"forecast_uncertainty.csv",index=False)
    result["forecast_estimation_uncertainty"]={"method":"HAC lag3 covariance of contemporaneous expanding regression; descriptive normal approximation, not registered inference",
          "median_mean_forecast_se":u.mean_forecast_se_hac.median(),"median_cost_hurdle":u.hurdle.median(),
          "ci90_entirely_above_cost_n":int((u.mean_ci90_low>u.hurdle).sum()),
          "ci90_entirely_below_cost_n":int((u.mean_ci90_high<u.hurdle).sum()),
          "ci90_crosses_cost_n":int(((u.mean_ci90_low<=u.hurdle)&(u.mean_ci90_high>=u.hurdle)).sum())}
    result["normalization"]={}
    for selected,g in t.groupby("decision"):
        result["normalization"][selected]={"n":len(g),"equal_risk_Y_sum":g.Y.sum(),"equal_risk_mean":g.Y.mean(),
            "risk_weighted_mean_Y":np.average(g.Y,weights=g.risk_usd),"mean_risk_usd":g.risk_usd.mean(),
            "mean_cost_hurdle":g.hurdle.mean(),"cap_bound_n":int(g.cap_bound.sum()),"rounding_sum":g.p0_rounding.sum()}
    leave=[]
    for year in sorted(d.year.unique()):
        g=d[d.year!=year]
        leave.append({"excluded_year":int(year),"pg_pnl":g.pg_pnl.sum(),"p0_pnl":g.p0_pnl.sum(),"pg_sr":sharpe(g.pg_pnl),"p0_sr":sharpe(g.p0_pnl),"delta_sr":sharpe(g.pg_pnl)-sharpe(g.p0_pnl)})
    result["leave_one_year_out"]=leave
    leave_event=[]
    for i in t.index:
        g=d.drop(index=i)
        leave_event.append({"excluded_month":str(d.loc[i,"month"]),"pg_pnl":g.pg_pnl.sum(),"p0_pnl":g.p0_pnl.sum(),"delta_sr":sharpe(g.pg_pnl)-sharpe(g.p0_pnl)})
    le=pd.DataFrame(leave_event)
    result["leave_one_event_out"]={"min_delta_sr":le.delta_sr.min(),"max_delta_sr":le.delta_sr.max(),"share_pg_better":(le.delta_sr>0).mean(),"pg_pnl_range":[le.pg_pnl.min(),le.pg_pnl.max()]}
    le.to_csv(OUT/"leave_one_event_out.csv",index=False)
    rejected=t[t.decision=="rejected"]
    details=["month","direction","dose","A","Y","yhat","hurdle","p0_pnl","p0_cost","risk_usd","coef_const","coef_dose","coef_A"]
    result["missed_winners"]=rejected.nlargest(8,"p0_pnl")[details].to_dict(orient="records")
    result["avoided_losers"]=rejected.nsmallest(8,"p0_pnl")[details].to_dict(orient="records")
    result["selected_losses"]=t[t.pg_traded].nsmallest(8,"p0_pnl")[details].to_dict(orient="records")
    result["concentration"]={}
    for name in ["p0","pg"]:
        v=d[f"{name}_pnl"]
        result["concentration"][name]={"best_month":str(d.loc[v.idxmax(),"month"]),"best_pnl":v.max(),"worst_month":str(d.loc[v.idxmin(),"month"]),"worst_pnl":v.min(),
            "net_without_best":v.sum()-v.max(),"net_without_top3":v.sum()-v.nlargest(3).sum(),"net_without_worst":v.sum()-v.min(),
            "top3_positive_share":v.nlargest(3).sum()/v[v>0].sum()}
    result["ablations"]={}
    candidate_returns=pd.DataFrame({"month":d.month.astype(str)},index=d.index)
    for name in pred:
        yhat=pred[name]
        mask=d.p0_traded & (yhat>d.hurdle)
        pnl=d.p0_pnl.where(mask,0)
        candidate_returns[f"ablation_{name}@1x"]=pnl/cfg.reference_nav
        candidate_returns[f"ablation_{name}@2x"]=(pnl-d.p0_cost.where(mask,0))/cfg.reference_nav
        result["ablations"][name]={"trades":int(mask.sum()),"pnl":pnl.sum(),"sharpe":sharpe(pnl),"2x_cost_sharpe":sharpe(pnl-d.p0_cost.where(mask,0)),
            "delta_sr_vs_p0":sharpe(pnl)-sharpe(d.p0_pnl),"pearson":np.corrcoef(yhat.loc[t.index],t.Y)[0,1],
            "by_era":{era:{"trades":int(mask.loc[g.index].sum()),"pnl":pnl.loc[g.index].sum(),"sharpe":sharpe(pnl.loc[g.index])} for era,g in d.groupby("era")}}
    # Gate-as-classifier confusion counts, not a trading alternative.
    result["selection_confusion"]={"kept_winners":int((t.pg_traded&(t.p0_pnl>0)).sum()),"kept_losers":int((t.pg_traded&(t.p0_pnl<=0)).sum()),
         "missed_winners":int((~t.pg_traded&(t.p0_pnl>0)).sum()),"avoided_losers":int((~t.pg_traded&(t.p0_pnl<=0)).sum())}
    result["nested_PD_PG"]={str(k):group_summary(g) for k,g in t.groupby(["pg_traded","pd_traded"])}
    # Requested follow-up diagnostic after seeing the negative-progress group.
    # Explicitly post-observation: all complementary groups included; no selection.
    ps_size=size_events(w.pseudos,w.es,w.zn,cfg=cfg)
    ps_ledger=run_row(w.pseudos,ps_size,w.pseudos.valid & (w.pseudos.month>=run.segment_start),row="pseudo_baseline",cfg=cfg)
    ps=w.pseudos.copy()
    for c in ["pnl","cost","traded"]:ps[f"p0_{c}"]=ps_ledger[c]
    ps["risk_usd"]=ps_size.notional*ps.sigma*np.sqrt(5)
    ps["year"]=pd.PeriodIndex(ps.month).year
    ps["era"]=np.where(ps.year<=2020,"through_2020","2021_2024")
    ps=ps[ps.month>=run.segment_start].copy()
    result["post_observation_progress_sign"]={"status":"Post-observation diagnostic after inspecting the first attribution output; all complements reported, not preregistered or validated."}
    for sample,frame in [("month_end",d),("mid_month",ps)]:
        result["post_observation_progress_sign"][sample]={}
        for name,mask in [("A_negative",frame.A<0),("A_nonnegative",frame.A>=0),
                          ("long_A_negative",(frame.s==1)&(frame.A<0)),("long_A_nonnegative",(frame.s==1)&(frame.A>=0)),
                          ("short_A_negative",(frame.s==-1)&(frame.A<0)),("short_A_nonnegative",(frame.s==-1)&(frame.A>=0))]:
            selected=mask & frame.p0_traded
            candidate_returns[f"posthoc_{sample}_{name}@1x"]=frame.p0_pnl.where(selected,0)/cfg.reference_nav
            candidate_returns[f"posthoc_{sample}_{name}@2x"]=(frame.p0_pnl-frame.p0_cost).where(selected,0)/cfg.reference_nav
            def cell(g):
                sel=mask.loc[g.index]&g.p0_traded
                selected=g[sel]
                pnl=g.p0_pnl.where(sel,0)
                best=pnl.idxmax()
                return {"n_calendar_months":len(g),"trades":len(selected),"net_usd":pnl.sum(),"sharpe":sharpe(pnl),
                     "mean_Y":selected.Y.mean(),"mean_dose":selected.dose.mean(),
                     "risk_weighted_mean_Y":np.average(selected.Y,weights=selected.risk_usd) if len(selected) else np.nan,
                     "best_event_month":str(g.loc[best,"month"]),"best_event_pnl":pnl.max(),
                     "net_without_best":pnl.sum()-pnl.max(),"net_without_best3":pnl.sum()-pnl.nlargest(3).sum(),
                     "sharpe_without_best":sharpe(pnl.drop(index=best)),
                     "2x_cost_sharpe":sharpe(pnl-g.p0_cost.where(sel,0))}
            result["post_observation_progress_sign"][sample][name]={"all":cell(frame),"by_era":{era:cell(g) for era,g in frame.groupby("era")}}
        frame.to_csv(OUT/f"progress_sign_{sample}.csv",index=False)
    candidate_returns.to_csv(OUT/"all_candidate_monthly_returns.csv",index=False)
    result["candidate_inventory"]={"return_file":"all_candidate_monthly_returns.csv","n_rules":len(pred.columns)+12,
        "n_cost_columns":len(candidate_returns.columns)-1,"note":"Six model ablations plus six complementary sign groups at each of month-end and mid-month; same rows at both 1x and 2x costs. PD is an exact duplicate of registered dose-only; root should deduplicate identical candidates."}
    # Sampling uncertainty of paired, fixed historical decisions, descriptive only.
    rng=np.random.default_rng(cfg.seed)
    pairs=d[["pg_pnl","p0_pnl"]].to_numpy()
    boot=[]
    for _ in range(9999):
        starts=rng.integers(0,len(d),size=int(np.ceil(len(d)/3)))
        ix=((starts[:,None]+np.arange(3))%len(d)).ravel()[:len(d)]
        p0,pg=pairs[ix,1],pairs[ix,0]
        boot.append([sharpe(pg)-sharpe(p0),(pg-p0).sum()])
    result["paired_block_bootstrap"]={"draws":9999,"block_months":3,"delta_sharpe_ci90":np.quantile(np.array(boot)[:,0],[.05,.95]).tolist(),"delta_pnl_ci90":np.quantile(np.array(boot)[:,1],[.05,.95]).tolist()}
    after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen}
    assert before==after
    result["frozen_hashes_unchanged"]=before
    result["data_latest_date"]={r:str(p.date.max()) for r,p in panels.items()}
    (OUT/"analysis.json").write_text(json.dumps(clean(result,12),indent=2)+"\n")
    d.to_csv(OUT/"event_ledger.csv",index=False)
    all_events.to_csv(OUT/"all_is_event_features.csv",index=False)
    print(json.dumps(clean({k:result[k] for k in ["overall","decision","forecast_skill","coefficient_summary","ablations","concentration","selection_confusion","leave_one_event_out"]},8),indent=2))


if __name__=="__main__":main()
