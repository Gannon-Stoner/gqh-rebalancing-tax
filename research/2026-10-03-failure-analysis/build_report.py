"""Build an offline report from the preserved exploratory evidence."""
from pathlib import Path
import base64,json,html
import pandas as pd

OUT=Path(__file__).resolve().parent

def image(name):
    p=OUT/name
    return '<img alt="Evidence figure" src="data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()+'">'

def table(df):return df.to_html(index=False,escape=True,border=0,classes='data')

def main():
    score=pd.read_csv(OUT/'complete_exploratory_scorecard.csv')
    meta=json.loads((OUT/'search_inventory.json').read_text())
    q=pd.read_csv(OUT/'timing_regimes/matched_quote_summary.csv').query("segment=='common'").set_index('variant')
    order=['baseline','exit_L','reverse_F1','flip_at_L','always_long_ES_F1']
    labels=['Original P0: hold through F1','Same positions, exit at month-end','Reverse direction for F1 only','Trade into month-end, then reverse','Always long ES on F1; original ES quantities']
    qt=pd.DataFrame({'Rule':labels,'Trades':[int(q.at[k,'trades']) for k in order],
        'Net P&L':[f"${q.at[k,'net']:,.0f}" for k in order],
        'Sharpe':[f"{q.at[k,'sharpe']:.3f}" for k in order],
        'Sharpe at 2× costs':[f"{q.at[k,'sharpe_2x']:.3f}" for k in order],
        '2021–24 Sharpe':[f"{score.set_index('candidate').at['quotes_'+k,'sharpe_2021_24']:.3f}" for k in order],
        'Net without top 3 months':[f"${q.at[k,'without_best3_net']:,.0f}" for k in order]})
    alltable=score[['candidate','sharpe_1x','sharpe_2x','sharpe_2021_24','net_usd','pnl_without_top3','p_max_abs_t_all_candidates']].copy()
    alltable.columns=['Candidate','Sharpe 1×','Sharpe 2×','Sharpe 2021–24','Net USD','Net excluding best 3','Exploratory family p']
    for c in ['Sharpe 1×','Sharpe 2×','Sharpe 2021–24','Exploratory family p']:alltable[c]=alltable[c].map(lambda v:f'{v:.3f}')
    for c in ['Net USD','Net excluding best 3']:alltable[c]=alltable[c].map(lambda v:f'${v:,.0f}')
    source_links=''.join(f'<li><a href="{p}">{label}</a></li>' for p,label in [
        ('audit/REPORT.md','Independent correctness and data audit'),
        ('gate_attribution/REPORT.md','Gate attribution, forecast uncertainty and all ablations'),
        ('timing_regimes/FINDINGS.md','Timing and execution findings'),
        ('timing_regimes/FOLLOWUP_REPORT.md','Complete timing follow-up tables'),
        ('model_relationships/model_scorecard.csv','Every feature-model result'),
        ('complete_exploratory_scorecard.csv','Full combined search scorecard'),
        ('search_inventory.json','Search count and inference definitions'),
        ('gate_attribution/INDEPENDENT_REVIEW.md','Independent review of new model and horizon analysis')])
    body=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Why the strategy failed — evidence and next hypothesis</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f8f7f2;color:#202e35;font:17px/1.65 system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:54px 36px 80px}}h1{{font-size:43px;line-height:1.14;letter-spacing:-1.3px;max-width:900px;margin:15px 0 25px}}h2{{font-size:26px;line-height:1.3;margin:44px 0 12px}}h3{{font-size:20px;margin:25px 0 8px}}p{{max-width:940px;margin:12px 0}}a{{color:#126a73}}.eyebrow{{font-size:13px;text-transform:uppercase;letter-spacing:1.5px;color:#487077}}.lead{{font-size:21px;max-width:960px}}.badge{{display:inline-block;padding:5px 10px;background:#ece3cf;color:#6d5017;font-size:13px;font-weight:700;border-radius:4px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}}.card{{background:white;border:1px solid #dfe4de;padding:20px;border-radius:7px}}.card b{{display:block;font-size:31px;color:#217966}}.card small{{font-size:13px;color:#56656b}}img{{width:100%;height:auto;margin:22px 0}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px;line-height:1.45;background:white}}th,td{{padding:12px 13px;text-align:right;border-bottom:1px solid #e0e6e4;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}th{{background:#e5eeea;color:#244e4b}}.callout{{border-left:4px solid #287d69;padding:13px 22px;background:#eaf0e9;margin:24px 0}}.note{{font-size:14px;color:#5e696b}}code{{background:#e8ebe7;padding:2px 5px;font-size:13px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#e8ebe7;padding:18px;font-size:12px}}details{{margin:28px 0}}summary{{cursor:pointer;font-weight:700}}li{{margin:8px 0}}footer{{border-top:1px solid #dce2dc;margin-top:45px;padding-top:20px;font-size:13px;color:#5e696b}}@media(max-width:700px){{main{{padding:28px 18px}}h1{{font-size:33px}}.cards{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">GQH • forensic research • 3 October 2026</div>
<h1>The strategy held across a change in the return pattern.</h1>
<span class="badge">Post-result exploratory analysis • original out-of-sample period unopened</span>
<p class="lead">The failed registered result is real. A deeper decomposition reveals a more specific failure: the positions earn into month-end and surrender much of that gain on the first session of the new month. The original gate then makes noisy selection decisions against a target that mixes those two phases.</p>
<div class="cards"><div class="card"><b>−$611k</b>Gross return on the extra F1 session<small>Same 104 original P0 positions</small></div><div class="card"><b>0.12 → 0.66</b>Sharpe from exiting at month-end<small>Matched 95 events, actual bid/ask fills</small></div><div class="card"><b>+$220k</b>Net profit in trades the gate rejected<small>35 rejected trades versus 69 retained</small></div></div>
<p class="note">Dollar values use the original fixed $10 million NAV, no compounding. Common period: October 2015–September 2024, 108 calendar months including flat months. One-leg controls retain original contract counts; shorter windows are not relevered.</p>
{image('failure_diagnosis.png')}
<h2>1. The exit date is the strongest explanation.</h2>
<p>With the original signals, quantities and held contracts, gross profit from entry through month-end is <b>$852,016</b>. The next session contributes <b>−$610,953</b>. Deducting the unchanged <b>$57,538</b> of round-trip costs leaves the original P0 result of <b>$183,525</b>. Exiting at month-end instead leaves <b>$794,478</b>, with Sharpe <b>0.634</b> and <b>0.589 at doubled costs</b>.</p>
<p>This is more than an attractive aggregate curve. The earlier exit earns in both original directions: <b>$409,309</b> in short-ES/long-ZN events and <b>$385,169</b> in long-ES/short-ZN events. It remains positive in every fixed era, including 2021–September 2024. Its common-period profit remains <b>$306,226</b> after deleting its three largest winning months; deleting any one calendar year leaves Sharpe between <b>0.462 and 0.814</b>.</p>
<p>An independent audit verified the dates are consecutive, contracts do not change, prices use the same contracts, and no roll gap or order-sign mistake explains the F1 loss. On 101 dates with fresh L/F1 quotes, simultaneous midquotes also show a large adverse F1 move; event-level quote and settlement P&L have correlation <b>0.979</b>.</p>
<h2>2. Real quotes support the timing result.</h2>
<p>These comparisons require fresh 15:59 bid/ask quotes at entry, month-end and F1 on the same 95 dates. All 108 months remain in the Sharpe denominator. Bid/ask crossing is paid at every transaction; reversing at month-end pays the additional round trip.</p>
<div class="scroll">{table(qt)}</div>
<p>For exit-at-month-end, the matched quote improvement over the original exit is <b>5.55 basis points per calendar month</b>, with a pointwise 90% block-bootstrap interval of <b>[2.22, 9.12]</b>. Removing the three best quote-executed months leaves <b>$315,615</b>; leave-one-year-out Sharpe remains <b>0.580–0.813</b>.</p>
<p class="note">The recent slice is weaker and less secure: removing the three best 2021–2024 months turns its quote-executed result slightly negative. Quote presence is not a fill guarantee for unlimited size; impact and new endpoint capacity still require validation.</p>
<h2>3. The failed forecast target cancels two different dose relationships.</h2>
<p>Using exactly the original sqrt(5) normalization and the same H1 regression design, the all-IS dose coefficient decomposes into <b>+0.146 before month-end</b> and <b>−0.156 on F1</b>, summing to the original <b>−0.0095</b>. These are descriptive coefficient decompositions; their exploratory p-values are not new confirmatory evidence.</p>
<p>Refitting the original dose/progress model only to the return ending at month-end makes <b>all 104 eligible events pass its cost hurdle</b>. A second implementation independently reproduced every trade and dollar. The minimum forecast margin above costs is +0.0508 risk units. Fixed ridge shrinkage gives the same decisions. In this sample, correcting the endpoint removes the model's reason to filter.</p>
<div class="callout"><b>Interpretation:</b> the original model was estimating “pressure into month-end plus the next session,” then treating that combined forecast as the value of the rebalancing opportunity. The empirical failure is a horizon mismatch plus weak trade selection. A separately tested earlier-exit hypothesis is better supported than adding complexity to the old target.</div>
<h2>4. The gate learned the wrong ranking.</h2>
<p>The 69 retained trades lost <b>$36,979</b>; 35 rejected trades earned <b>$220,504</b>. The gate was already negative before costs. It rejected 13 of 14 trades with dose above 1.5, because the fitted dose coefficient was negative at every tradable decision. The first 60-event fit had coefficient −0.355; the expanding window retained that sign.</p>
<p>Rejecting eight long-ES events sacrificed <b>$273,133</b>. Avoiding 27 short-ES events saved only <b>$52,629</b>. Approximate 90% intervals for the forecast mean cross the cost hurdle in <b>103 of 104 decisions</b>. The model's uncertainty is much larger than the small forecast edge driving its yes/no decisions.</p>
<p>The progress variable itself improved the dose-only filter by <b>$80,958</b>. So “progress caused the failure” is not supported. Forecast correlation is −0.147 across all 108 evaluation events and −0.067 across 104 tradable events. Underperformance versus P0 survives deletion of any single event or any single year.</p>
<h2>5. Other relationships were tested, including failures.</h2>
<p>Nine fixed feature specifications were evaluated on both month-end and midmonth panels: original OLS, shrinkage, direction interactions, quarter-end interactions, volatility interactions, stock/bond correlation interactions, nonlinear dose/progress terms, common market movement, and combined state variables. Each forecast trains only on completed past events, with train-only scaling and a fixed shrinkage penalty. Every specification is retained.</p>
<p>The quarter-interaction model had the strongest feature-model Sharpe, <b>0.525</b>, rising to 0.800 in 2021–2024. However, its forecast squared error still underperformed the historical-mean benchmark, and its apparent positive return does not survive the exploratory family correction. Direction-aware models also improved historical returns; correlation conditioning and a shorter training window made results worse.</p>
<p>A simple post-observation partition is informative: month-end events with <b>A&lt;0</b>—price still moving against the intended trade—earned <b>$444,473</b>, versus <b>−$260,948</b> for A≥0. The analogous midmonth A&lt;0 group lost $338,159. But removing the best three month-end A&lt;0 events leaves only <b>$1,501</b>. It is a secondary research lead, with substantial concentration.</p>
{image('model_relationships/model_stability.png')}
<h2>6. A reversal trade needs a generic calendar control.</h2>
<p>The F1 loss is almost entirely concentrated in short-ES positions. A post-observation two-stage rule—hold the original position into month-end, then reverse for F1—has matched-quote Sharpe <b>0.930</b>, or <b>0.858 at doubled costs</b>. That is a potentially useful candidate, but its second stage does not establish drift-specific reversal: <b>always holding long ES on F1 has Sharpe 0.897 on the same quote dates</b>, compared with 0.833 for the reversed spread alone.</p>
<p>The difference between drift-conditioned reversal and always-long spread on F1 has a 90% interval spanning zero. Generic positive first-session equity returns are therefore a serious competing explanation. “Always long” here means direction is fixed; quantities still come from the original ex-ante sizing and require further equal-risk controls.</p>
<p>The source literature already discusses temporary rebalancing pressure and a separate reversal treatment around the new month. This analysis diagnoses our implementation's holding window; it does not claim discovery of a new calendar anomaly. See <a href="https://afajof.org/management/viewp.php?n=144452">Harvey, Mazzoleni and Melone, December 2025 manuscript, introduction and Section 4</a>.</p>
<h2>7. The stronger research result is still exploratory.</h2>
<p>The combined inventory contains <b>{meta['listed_return_series']} listed return series and {meta['distinct_return_series']} distinct series</b>, including registered benchmarks, control groups, failed models, timing variants and execution checks. These are correlated variants, not independent experiments. A centered, paired three-month-block bootstrap with 19,999 draws applies a two-sided maximum-statistic adjustment over this whole recorded family. <b>The leading positive candidates do not reach 5% after that broad adjustment.</b> Earlier research choices create additional selection exposure.</p>
<p>This does not make the accounting decomposition disappear: F1 mechanically explains $610,953 of the original P0 result. It limits what we can claim about future expected profit. Chronological refitting and era stability help, but all these IS years had already been inspected. The untouched original OOS period remains the necessary next evaluation.</p>
<p>The previous “effect has been competed away” account also needs correction. The published diagnostic freezes direction at L−12, while trades use L−5; the direction changes in approximately 13–18% of months. Actual-signal entry-to-L paths remain positive in each era. Recent weakening is observed; competition as the cause is unproven.</p>
<h2>8. Correctness findings and the next fixed comparison.</h2>
<p><b>121 existing tests passed; one was skipped.</b> Independent checks reproduced original signals and P&L, examined settlement and open-interest publication timing, reconciled actual quotes, and reviewed the new horizon/refit code. No demonstrated sign, roll, or decision-level leakage bug explains the original losses.</p>
<p>Three reporting defects were identified: PG/PX lacked the promised eligible-date match; settlement capacity used nonexistent regular clocks on early closes; the field labeled final gate coefficients was one completed event stale. None changes the historical primary P&L. Corrected supplementary figures are in the audit report.</p>
<p>The clean next comparison is to preserve the original PG/P0 result, declare <b>same original P0 positions with exit at L</b> as the primary exploratory follow-up, and retain <b>the two-stage rule and always-long F1 controls</b> as secondary comparisons. Lock exact dates, quotes, costs, sizes, capacity assumptions and evaluation criteria before opening the original OOS sample. Report all outcomes once. This report does not unlock or evaluate that sample.</p>
<details><summary>Full search scorecard — all {len(score)} listed series</summary><p class="note">Family p-values concern mean return, not Sharpe. Repeated controls are intentionally retained. Two-cost scenarios use identical decisions. Pointwise intervals in source tables are not simultaneous confidence bands.</p><div class="scroll">{table(alltable)}</div></details>
<h2>Evidence and reproduction</h2><ul>{source_links}</ul>
<p class="note">The HTML embeds its two figures for offline reading. Linked source files live beside it. All exploratory outputs are isolated under this research directory. Original results hash: <code>{meta['registered_sha256']}</code>.</p>
<details><summary>Rebuild the analysis</summary><pre>PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/audit/audit.py
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/audit/oi_publication_audit.py
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/audit/f1_audit.py
.venv/bin/python research/2026-10-03-failure-analysis/gate_attribution/analyze.py
.venv/bin/python research/2026-10-03-failure-analysis/timing_regimes/analyze.py
.venv/bin/python research/2026-10-03-failure-analysis/timing_regimes/followup.py
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/model_relationships/analyze.py
PYTHONPATH=src .venv/bin/python research/2026-10-03-failure-analysis/model_relationships/horizon_followup.py
.venv/bin/python research/2026-10-03-failure-analysis/combine.py
.venv/bin/python research/2026-10-03-failure-analysis/build_report.py</pre></details>
<footer>Evidence labels: original result = registered historical evaluation; all new return variants = post-result exploratory analysis. Contract quantities, costs, fixed-NAV accounting, invalid-event exclusions and statistical scope are retained in the source files.</footer>
</main></body></html>'''
    (OUT/'failure_analysis.html').write_text(body)
    print(OUT/'failure_analysis.html')

if __name__=='__main__':main()
