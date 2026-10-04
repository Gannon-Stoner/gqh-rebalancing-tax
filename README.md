# Paying for what is left: month-end rebalancing in ES/ZN

Does a known 60/40 rebalancing trade improve when we trade only if enough return remains after earlier price adjustment? This project tests that question with a pre-registered remaining-return gate, realistic costs, an exposure-matched control and mid-month placebo events.

**Result:** the gate failed in sample. Its net Sharpe was **−0.05**, versus **0.13** for always trading. The frozen rule improved out of sample (**0.91** versus **0.14**), but only 16 gate trades and two large winners drive that result. We report an unconfirmed hypothesis, not a deployable edge.

Start with the [Quant Note](note/note.pdf): five main pages, followed by references and an optional appendix. The [original hypothesis](HYPOTHESIS.md) and [frozen configuration](config/frozen.yaml) remain unchanged from `prereg-final`; [amendments](AMENDMENTS.md) record implementation facts, disclosures and later verification. See [Reading the frozen hypothesis](#reading-the-frozen-hypothesis) for wording clarifications.

## Judges: reproduce the headline results

Use **Python 3.11–3.14**. The final workflow was tested in a fresh Python 3.14.7 environment, without API keys or the full market-data history. The first installation needs internet; the replay and its summary work offline afterward.

```bash
git clone https://github.com/Gannon-Stoner/gqh-rebalancing-tax.git
cd gqh-rebalancing-tax
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
python scripts/webull_backtest.py --replay
```

On Windows, create the environment with `py -3.14 -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1` in PowerShell. Then use the same `python` commands.

**Open `reports/webull_backtest.html` in a browser.** It shows the verification verdict, the headline table and the portfolio equity curves. The terminal should end with:

```text
PASS: PG/P0 event P&Ls and all 28 checked sample metrics match results.json at 1x costs.
```

Expected note metrics, net of the registered 1× costs:

| Row | Sample | Trades | Return/year | Vol/year | Sharpe | Max drawdown | Turnover/year |
|---|---|---:|---:|---:|---:|---:|---:|
| PG: remaining-return gate | IS | 69 | -0.04% | 0.87% | -0.05 | 2.55% | 4.4× |
| P0: always-trade benchmark | IS | 104 | 0.20% | 1.52% | 0.13 | 2.23% | 9.1× |
| PG | OOS | 16 | 1.00% | 1.11% | 0.91 | 0.35% | 5.6× |
| P0 | OOS | 23 | 0.18% | 1.34% | 0.14 | 1.30% | 8.9× |

The generated report also checks worst month. The exact values and tolerances are in `reports/webull_backtest.json`; a mismatch exits with a nonzero status. Typical replay runtime is about one minute after installation. To keep verification outputs separate, add `--output-dir /path/to/reports`.

### What the Webull check establishes

The runner uses the track's [Webull starter kit](third_party/webull_kit/VENDORED.md), vendored without source changes: Backtrader Cerebro, its analyzers, metric functions and detailed HTML reports. ES/ZN settlements enter through `PandasData`; this path does not call Webull OpenAPI or require a Webull account.

- **Default `--replay`:** reads the frozen PG/P0 trade ledgers and held-contract settlement prices in `data/replay/`. Backtrader executes the scheduled orders, charges costs and checks all **85 PG and 127 P0 event P&Ls** within $0.01. It then checks seven metrics for each of two rows and two samples against `results.json` (28 comparisons).
- **Scope:** PG and P0 at **1× costs**, IS and OOS. Default replay checks accounting and fills at assumed settlement marks. Signal generation, contract selection and sizing come from the ledger. Trade counts and turnover use that ledger; return-based metrics use Backtrader P&L.
- **Outside this check:** PX bid/ask fills, the other strategy rows, 2× costs, inference, factors, risk and capacity. Those are produced by the full research pipeline below. Settlement fills are a modeling assumption, not evidence of execution at those prices.
- **Different metrics in the kit:** its detailed reports count individual leg trades and use daily equity. The note uses paired events and monthly returns at fixed $10M NAV, with no compounding. Their Sharpe ratios and trade counts are therefore not interchangeable.

The main summary works offline. The detailed `webull_kit_PG.html` and `webull_kit_P0.html` charts load Plotly from a CDN and need internet. No orders are sent to a broker.

## Optional: reconstruct signals from licensed settlements

This route rebuilds signals, gates, contract choices and sizes, then verifies that all replay inputs match the committed bundle before the Webull run. It needs a Databento account and licensed data access. The four definition/statistics requests were quoted at approximately **$0.83 on 2026-10-04**; check the current quote before purchasing.

```bash
cp .env.example .env
# Add DATABENTO_API_KEY locally; never commit .env.
python data/download.py --quote settlements
python data/download.py --pull settlements
python scripts/webull_backtest.py --data
```

Before CME published open interest, contract selection uses same-day volume ranks (amendment A14). `data/selection_ranks.csv` stores those ranks without volumes or prices. `--data` requires local settlement panels or all four raw files; it never silently falls back to replay. This remains a reproduction of the frozen rule, not a new opportunity to tune it.

## Full research reproduction

A Git clone with the protocol tags is required. Work in a clean clone used only for this project; unrelated raw files can enter the historical loader's broad batch patterns. Full data acquisition was quoted at approximately **$92 on 2026-10-03**, plus the publicly available factor files. Raw downloads and derived panels stay local.

```bash
python data/download.py --quote is
python data/download.py --quote oos
# After reviewing the current quotes:
python data/download.py --pull is
python data/download.py --pull oos
python data/download_factors.py
python -m gqh.reproduce --sample ALL --out reports/reproduced_results.json
```

This reconstructs all six strategy rows and the registered analysis. The committed results remain the submission record. Compare numerical results separately from `provenance`: a reproduction on another commit correctly records a different commit hash. Vendor or factor-file revisions may also change inputs; `data/manifest.json` records the original requests and hashes.

For an independent rebuild from already-downloaded, hash-verified project files:

```bash
scripts/fresh_clone_check.sh HEAD ALL
```

That check uses a temporary checkout of the specified **committed revision**, isolates manifest-listed raw inputs, requires the factor file, and compares the complete result content while reporting provenance separately. It does not validate uncommitted edits or overwrite official results.

Additional commands:

| Purpose | Command | Output |
|---|---|---|
| Tests, no credentials required | `python -m pytest -q` | Synthetic/unit checks; licensed pilot fixture skips if unavailable |
| Inference calibration | `python scripts/calibrate_inference.py` | `reports/inference_calibration.md` |
| IS / OOS data coverage | `python scripts/is_coverage.py` / `python scripts/oos_coverage.py` | Coverage reports |
| Supplementary submission audit | `python scripts/submission_audit.py` | Matched PG/PX reporting checks |
| Figures | `python scripts/build_figures.py` | `reports/figures/` |
| PDF from saved results | `python scripts/render_note.py results.json` | `note/note.pdf` |

Final clean-environment verification: **239 tests passed, 1 skipped** (the licensed pilot fixture). Both the offline replay and the settlement-based signal reconstruction matched PG/P0 at 1× costs. The separate full ALL rebuild matched every analytical result exactly, excluding only reported provenance.

PDF export additionally requires Pandoc and Google Chrome at the macOS path used by the renderer. Judges do **not** need these tools to run the Webull check or read the supplied PDF.

## Reading the frozen hypothesis

The central hypothesis has two parts: allocation drift predicts the remaining month-end spread return, and pre-entry progress predicts less remaining return specifically at month-end. The gate trades only when its forecast exceeds registered costs. The contribution is the application of this joint test; rebalancing pressure, placebos, exposure controls and preregistration are established ideas.

`HYPOTHESIS.md` preserves exactly what was registered, including predictions that failed. Later editorial clarifications are in [A22](AMENDMENTS.md#a22-submission-audit-and-editorial-clarifications-2026-10-04-after-results):

- “One contract per leg” means one **expiry**, with variable integer quantities.
- “A null is reported as an upper bound” is imprecise. Wide confidence intervals and non-rejection do not establish absence.
- PE targets every P0 event at reduced size, but integer rounding can make it untradable.
- Economic persistence is a proposed mechanism, not evidence that arbitrage cannot remove an edge.

The protocol sequence is `prereg-final` → `freeze-is` → `freeze-final`. Tags establish the recorded sequence; they are not a substitute for the prior-look disclosures.

## Disclosures and limits

- **Prior exposure:** `HYPOTHESIS.md` discloses a private 2010–2022 proxy study, at least 29 month-end and 45 trend/volatility variants, and partial exposure to Oct-2024–Dec-2025 through published extensions. The designated OOS evaluation used frozen trading rules, but the period was not wholly unseen.
- **Masked-run incident:** before `freeze-is`, a dry run revealed PG's trade count and two Sharpe signs (A16). Later research and all post-result diagnostic variants are disclosed in the note; none changed the strategy.
- **Capacity:** the recorded 93% one-lot pass rate includes five early-close events with unavailable regular-clock windows. All 64 regular-window PG events pass, but holiday capacity remains unverified. Volume feasibility does not establish profitable capacity when IS Sharpe is negative.
- **Execution comparison:** PX excludes early-close entries/exits. The supplemental audit reports PG on the same dates so the comparison does not confuse execution with event coverage.
- **Known saved-output defect:** OOS factor regressions in `results.json` include dates beyond the factor file's 2026-08-31 endpoint with zero-filled factor sums (A20). They are not used in the note and should not be interpreted. The official output is preserved rather than silently replaced.
- **Proposed controls:** governance pauses are prospective and were not applied to the backtest.

## Data and attribution

The full Databento history, `.env` and API keys are not committed. The small replay bundle contains **1,520 source settlement values**, the session calendar and derived trade ledgers. On 2026-10-04 the author confirmed explicit permission to redistribute this subset; that permission does not cover the full history. The track's separate rule against raw licensed data should be read alongside this permission when confirming submission eligibility.

Sources are cited in the note: Databento GLBX.MDP3, Kenneth French's Data Library, the research motivating the hypothesis, CME margin requirements and the Webull/Backtrader tooling. The vendored starter's source and ZIP checksum are in [VENDORED.md](third_party/webull_kit/VENDORED.md).

## Code map

| Path | Purpose |
|---|---|
| `src/gqh/calendar.py`, `contracts.py`, `panel.py` | Ex-ante sessions, expiry selection, settlement records |
| `src/gqh/signals.py`, `gate.py`, `strategy.py`, `engine.py` | Signal, past-event fitting, six rows, integer sizing and P&L |
| `src/gqh/stats.py`, `metrics.py` | Bootstrap, Holm, DSR, performance metrics |
| `src/gqh/risk.py`, `capacity.py`, `diagnostics.py` | Risk, volume feasibility and mechanism diagnostics |
| `scripts/webull_backtest.py` | Judge-facing Webull starter replay and reconciliation |
| `src/gqh/bt_replay.py` | Per-event second-engine check used by the research pipeline |
| `src/gqh/pipeline.py`, `reproduce.py` | Full analysis and provenance |
| `research/` | Separately labeled post-result research; not the submitted trading rule |
| `trials.jsonl` | Research run and prior-look record |

Submission requires the PDF and a **public GitHub link** on Devpost. The [live track page](https://www.gqhacks.com/tracks/systematic-trading) lists both submission and final code push at **11:00 AM Eastern, October 4, 2026** (checked that morning). Local edits must be committed and pushed to appear in the judge's clone.
