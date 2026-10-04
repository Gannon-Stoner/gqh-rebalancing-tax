"""Build every figure in the note: IS figures from results_is.json, OOS figures from results.json.

In an ALL run the stacked panel and the diagnostics pool IS and OOS events (A20), so
the IS figures are always drawn from the one-time IS run; the OOS figures read only the
OOS rows and the OOS entries of the PG action ledger.

Run:  python scripts/build_figures.py      -> reports/figures/*.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gqh.report import ROW_STYLE, _save, build, fig_equity, plt  # noqa: E402


def fig_oos_events(res: dict, out: Path) -> Path:
    """PG net P&L per OOS event (thousand USD); events the gate skipped are shown as gaps on a grey baseline."""
    al = res["diagnostics"]["action_ledger_PG"]
    idx = [i for i, s in enumerate(al["sample"]) if s == "OOS"]
    months = [al["month"][i] for i in idx]
    net = [al["net"][i] / 1e3 for i in idx]
    traded = [bool(al["traded"][i]) for i in idx]
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    ax.bar(range(len(idx)), net, color=[ROW_STYLE["PG"][0] if v >= 0 else "#c00000" for v in net], width=0.75)
    ax.scatter([k for k, t in enumerate(traded) if not t], [0] * traded.count(False), marker="|", color="#7f7f7f",
               s=30, label="not traded")
    ax.axhline(0, color="black", lw=0.5)
    ticks = [k for k, m in enumerate(months) if m.endswith(("-01", "-07"))]
    ax.set_xticks(ticks, [("Jan " if months[k].endswith("-01") else "Jul ") + months[k][:4] for k in ticks])
    ax.set_ylabel("PG net P&L per event, $ thousand")
    ax.legend(frameon=False, loc="upper left")
    ax.set_title(f"PG event by event, OOS {res['rows_OOS']['months'][0]} to {res['rows_OOS']['months'][1]}")
    return _save(fig, out)


def main() -> None:
    out = ROOT / "reports" / "figures"
    figs = build(ROOT / "results_is.json", out)
    oos = ROOT / "results.json"
    if oos.is_file():
        res = json.loads(oos.read_text())
        if res.get("rows_OOS", {}).get("months"):
            figs += [fig_equity(res, out / "equity_oos.png", sample="OOS"), fig_oos_events(res, out / "pg_oos_events.png")]
    for f in figs:
        print(f.relative_to(ROOT))


if __name__ == "__main__":
    main()
