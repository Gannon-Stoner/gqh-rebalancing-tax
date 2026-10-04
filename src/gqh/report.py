"""Figures for the note, built from a results JSON only (``python -m gqh.report results_is.json``).

Every figure is deterministic given the results file, so the note can be rebuilt and
checked against it. Saved as PNG (200 dpi) under reports/figures/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gqh.config import repo_root  # noqa: E402

ROW_STYLE = {"PG": ("#1f4e79", 2.2, "-"), "P0": ("#7f7f7f", 1.6, "-"), "PD": ("#c55a11", 1.3, "--"),
             "PE": ("#548235", 1.3, ":"), "PX": ("#2e75b6", 1.3, "-."), "PP": ("#bf9000", 1.3, "--")}
plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 200})


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", dpi=200)
    plt.close(fig)
    return path


def fig_key(res: dict, out: Path) -> Path:
    """Remaining return Y against pre-entry progress A (quintile bins): month-end events vs pseudo-events."""
    st = pd.DataFrame(res["stacked_panel"])
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    for me, color, label in ((1, "#1f4e79", "month-end events"), (0, "#bf9000", "mid-month pseudo-events")):
        g = st[st["ME"] == me]
        bins = pd.qcut(g["A"], 5, labels=False, duplicates="drop")
        agg = g.groupby(bins).agg(A=("A", "mean"), Y=("Y", "mean"), sd=("Y", "std"), n=("Y", "size"))
        se = agg["sd"] / np.sqrt(agg["n"])
        ax.errorbar(agg["A"], agg["Y"], yerr=1.645 * se, fmt="o", color=color, ms=3.5, capsize=2, lw=1, label=label)
        b = np.polyfit(g["A"], g["Y"], 1)
        xs = np.linspace(g["A"].quantile(0.02), g["A"].quantile(0.98), 50)
        ax.plot(xs, np.polyval(b, xs), color=color, lw=1.2, alpha=0.8)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("pre-entry progress A (σ units, signed toward the flow)")
    ax.set_ylabel("remaining return Y (σ units)")
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.22), fontsize=7)
    ax.set_title("Remaining return vs progress (bin means, 90% CI)")
    return _save(fig, out)


def fig_equity(res: dict, out: Path, sample: str = "IS") -> Path:
    """Cumulative net return (% of NAV, uncompounded) of the six rows at 1x costs on the comparison segment."""
    sec = res[f"rows_{sample}"]
    months = pd.period_range(sec["months"][0], sec["months"][1], freq="M")
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    for row, r in sec["monthly_returns_1x"].items():
        color, lw, ls = ROW_STYLE.get(row, ("black", 1, "-"))
        ax.plot(months.to_timestamp(), np.cumsum(r) * 100, color=color, lw=lw, ls=ls, label=row)
    ax.axhline(0, color="black", lw=0.5)
    import matplotlib.dates as mdates

    ax.xaxis.set_major_locator(mdates.YearLocator(base=2 if len(months) > 60 else 1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("cumulative net return, % of NAV")
    ax.set_title(f"Strategy rows, {sample} {sec['months'][0]} to {sec['months'][1]} (1x costs)")
    h, lab = ax.get_legend_handles_labels()                      # legend below the axes: never covers a line
    order = [lab.index(r) for r in ("PG", "P0", "PD", "PE", "PX", "PP") if r in lab]
    ax.legend([h[i] for i in order], [lab[i] for i in order], frameon=False, ncol=6, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), handlelength=1.8, columnspacing=1.0)
    ax.set_title(f"Strategy rows, {sample} {sec['months'][0]} to {sec['months'][1]} (1× costs)")
    return _save(fig, out)


def fig_path(res: dict, out: Path) -> Path:
    """Dose-weighted mean signed spread path from L-12 to F1+5 by era (sign and dose frozen at L-12)."""
    prof = res["diagnostics"]["event_path_by_era"]
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    colors = {"2010-15": "#9dc3e6", "2016-20": "#2e75b6", "2021-24": "#1f4e79", "OOS": "#c00000"}
    for era, row in prof.items():
        ks = sorted((int(k[1:]), v) for k, v in row.items() if k.startswith("k"))
        ax.plot([k for k, _ in ks], [v for _, v in ks], marker="o", ms=2.5, lw=1.2, color=colors.get(era, "gray"),
                label=f"{era} (n={int(row['events'])})")
    for x, txt in ((-8, "L-8"), (-5, "L-5"), (-4, "L-4"), (0, "L"), (1, "F1")):
        ax.axvline(x, color="gray", lw=0.4, ls=":")
        ax.text(x, ax.get_ylim()[1], txt, fontsize=6, ha="center", va="bottom")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("sessions relative to L")
    ax.set_ylabel("signed cumulative spread (σ units)")
    ax.set_title("Event-time path by era", pad=10)
    ax.legend(frameon=False)
    return _save(fig, out)


def fig_timeline(out: Path) -> Path:
    """Schematic of one month: pseudo-event window, event decision, entry, hold and exit."""
    fig, ax = plt.subplots(figsize=(7.0, 1.1))
    ax.set_xlim(-18.5, 2.5)
    ax.set_ylim(-1, 2.2)
    ax.axis("off")
    ax.plot([-18, 2], [0, 0], color="black", lw=0.8)
    for k in range(-17, 2):
        ax.plot([k, k], [-0.08, 0.08], color="black", lw=0.6)
    spans = [(-17, -14, 1.55, "#f2dcb3", "pseudo progress"), (-13, -8, 1.55, "#ffd966", "pseudo hold (PP)"),
             (-8, -5, 0.75, "#bdd7ee", "progress A"), (-4, 1, 0.75, "#9dc3e6", "hold: L-4 settle -> F1 settle")]
    for a, b, y, c, t in spans:
        ax.add_patch(plt.Rectangle((a, y - 0.25), b - a, 0.5, color=c))
        ax.text((a + b) / 2, y, t, ha="center", va="center", fontsize=7)
    for k, t, ha in ((-14, "L-14\npseudo decision", "center"), (-5, "L-5  \ndecide (D, z, A, Ŷ vs C)  ", "right"),
                     (-4, "  L-4\n  enter", "left"), (0, "L", "center"), (1, "F1\nexit", "center")):
        ax.text(k, -0.25, t, ha=ha, va="top", fontsize=6.5)
    return _save(fig, out)


def fig_impact(res: dict, out: Path) -> Path:
    """Net Sharpe of PG against NAV under square-root impact (Y = 1): a scenario, not a backtest."""
    rows = res.get("risk_IS", {}).get("impact_PG", [])
    fig, ax = plt.subplots(figsize=(3.4, 2.2))
    if rows:
        nav = [r["nav"] for r in rows]
        ax.semilogx(nav, [r["sharpe"] for r in rows], marker="o", color="#1f4e79")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("NAV (USD)")
    ax.set_ylabel("net Sharpe (annualized)")
    ax.set_title("PG net Sharpe vs NAV, square-root impact")
    return _save(fig, out)


def build(results_path: Path, out_dir: Path | None = None) -> list[Path]:
    res = json.loads(Path(results_path).read_text())
    out_dir = out_dir or repo_root() / "reports" / "figures"
    figs = [fig_key(res, out_dir / "key_y_vs_a.png"), fig_equity(res, out_dir / "equity_is.png"),
            fig_path(res, out_dir / "event_path.png"), fig_timeline(out_dir / "timeline.png"),
            fig_impact(res, out_dir / "impact.png")]
    if res.get("rows_OOS", {}).get("months"):
        figs.append(fig_equity(res, out_dir / "equity_oos.png", sample="OOS"))
    return figs


if __name__ == "__main__":
    for f in build(Path(sys.argv[1])):
        print(f)
