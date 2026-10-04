# GQH 2026: paying for what is left of the month-end rebalancing move (ES/ZN)

Tests whether a month-end 60/40 rebalancing-flow trade on ES/ZN futures works better when it is
gated on how much of the expected move has already happened before we can trade.

- **Pre-registered.** [HYPOTHESIS.md](HYPOTHESIS.md) and `config/frozen.yaml` were committed and
  pushed under the tag `prereg-final` before any price data was loaded. They never change;
  corrections go in [AMENDMENTS.md](AMENDMENTS.md) (bug fixes, data facts, clarifications), each
  dated and made before the run it affects.
- **Protocol tags.** `prereg-final` (hypothesis) → `freeze-is` (code frozen; the in-sample run
  happens once) → `freeze-final` (fresh-clone reproduction passed; the out-of-sample data is
  loaded and evaluated once). `python -m gqh.reproduce` refuses to run before the matching tag.
- **One command rebuilds every number:** `python -m gqh.reproduce` writes `results_is.json`
  (or `results.json` with `--sample ALL`); two runs are byte-identical.

## For judges: check the note's headline numbers in about 5 minutes, no data or keys needed

Python 3.11+. Clone with git rather than downloading a ZIP (the full-pipeline guards check the protocol tags).

```bash
git clone https://github.com/Gannon-Stoner/gqh-rebalancing-tax.git && cd gqh-rebalancing-tax
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

python -m pytest -q                   # 223 tests on synthetic data: timing, leakage, rolls, accounting
python scripts/webull_backtest.py     # the strategy in the Webull starter kit, ~1 minute
```

`scripts/webull_backtest.py` runs PG (the strategy) and P0 (always trade) end to end in the track's
Webull starter kit, vendored unmodified in `third_party/webull_kit/`: its Backtrader Cerebro, the
analyzers its `main.py` adds, its metric code and its HTML report (amendment A21). The kit's Webull
OpenAPI feed has no ES/ZN futures, so settlements go in through `PandasData`. Every return,
volatility, Sharpe, max drawdown, worst month and turnover in the note's IS and OOS tables, for both
rows, is recomputed from Backtrader's own P&L and checked against `results.json`; the script exits
with an error on any mismatch. Reports: `reports/webull_backtest.md`, `reports/webull_kit_{PG,P0}.html`.

**What it runs on.** With no data on disk it replays `data/replay/`: the engine's per-event trade
ledger for PG and P0 (dates, contracts, sizes) and the settlement prices of the held contracts on
holding days only (1,520 prices; the market data is licensed, so the full history is not committed).
That replays the trades; it does not recompute the signals. To rerun the signals too:

```bash
cp .env.example .env                          # DATABENTO_API_KEY=... (new accounts get $125 free credit)
python data/download.py --pull settlements    # ES/ZN definition + statistics, about $0.83
python scripts/webull_backtest.py             # now reruns the frozen engine from the settlements and
                                              # checks it reproduces data/replay/ byte for byte
```

Contract selection before CME published open interest (2010–2015, A14) uses minute-bar volume;
`data/selection_ranks.csv` holds each contract's volume *rank* per day (no volumes or prices), which
picks the same contracts.

**Everything else** (confirmatory tests, ΔSR intervals, PX quote fills, capacity, risk) needs the full
Databento pull (about $92, inside the free credit; ~4 GB):
`python data/download.py --pull is && python data/download.py --pull oos && python -m gqh.reproduce --sample ALL`,
which rewrites `results.json` byte-identically (see [Pipeline](#pipeline)).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m pytest            # deterministic; no network, no market data
```

## Data (licensed data is never committed)

```bash
cp .env.example .env                      # add DATABENTO_API_KEY=...
python data/download.py                   # free cost check of every request
python data/download.py --pull is         # in-sample: definitions, statistics, outright 1-minute bars/quotes
python data/download.py --pull oos        # out of sample, only after the freeze-final tag (refused before it)
python data/download_factors.py           # Ken French daily FF3 + momentum (public)
python scripts/is_coverage.py             # data audit -> reports/is_coverage.md (aggregates only)
```

Every downloaded file is recorded with its request and SHA-256 in `data/manifest.json`. The
bbo-1m years from 2013 on, and the OOS bbo-1m, were bought as Databento batch jobs (`--batch-submit` / `--batch-fetch`,
recorded in `data/batch_jobs.json`) because streaming was throttled; the data is identical. `--batch-record JOB`
re-records a downloaded job from disk after checking every file against the vendor's own manifest.

## Pipeline

| Step | Command | Output |
|---|---|---|
| Inference calibration (synthetic) | `python scripts/calibrate_inference.py` | `reports/inference_calibration.md` |
| Masked plumbing run (no returns) | `python scripts/plumbing_run.py` | `reports/plumbing_p0.md`, `trials.jsonl` |
| In-sample run (after `freeze-is`) | `python -m gqh.reproduce` | `results_is.json` |
| Fresh-clone reproduction | `scripts/fresh_clone_check.sh` | byte-identical results check |
| OOS data audit (after `freeze-final`) | `python scripts/oos_coverage.py` | `reports/oos_coverage.md` |
| Out of sample (after `freeze-final`) | `python -m gqh.reproduce --sample ALL` | `results.json` |
| Webull starter kit run (after `freeze-final`) | `python scripts/webull_backtest.py` | `reports/webull_backtest.md` (PG/P0 in the kit's Backtrader harness; must equal `results.json`) |
| Figures and note | `python scripts/build_figures.py && python scripts/render_note.py results.json` | `reports/figures/`, `note/note.pdf` |

## Layout

| Path | Contents |
|---|---|
| `src/gqh/calendar.py` | sessions, L, F1, L−k, ex-ante decision dates, early closes |
| `src/gqh/contracts.py` | ES max-OI and ZN first-position-day selection, reference returns |
| `src/gqh/panel.py`, `data.py`, `quotes.py` | Databento settlements, derived panels, minute extracts, quote state |
| `src/gqh/signals.py` | drift, σ̂, dose, direction, progress A, outcome Y |
| `src/gqh/gate.py`, `strategy.py`, `engine.py` | walk-forward gate, the six rows, contract-level P&L and fills |
| `src/gqh/stats.py`, `metrics.py` | month-block bootstrap, Holm, DSR, ΔSR CIs; row metrics |
| `src/gqh/risk.py`, `capacity.py`, `diagnostics.py` | stress, factors, margin, survival, impact; capacity; §6 diagnostics |
| `scripts/webull_backtest.py`, `third_party/webull_kit/`, `data/replay/` | PG and P0 run end to end in the Webull starter kit's harness; the kit (vendored, unmodified) and the replay inputs (A21) |
| `src/gqh/bt_replay.py` | second engine: every trade replayed in Backtrader (the Webull starter kit's engine) |
| `src/gqh/pipeline.py`, `reproduce.py`, `report.py` | end-to-end run, one command, figures |
| `tests/` | 220+ tests, including impulse timing, truncation/leakage, roll accounting, reproducibility |

Every run is logged to `trials.jsonl`.
