"""Figures build from a results dict alone (gqh.report), on synthetic data."""

from __future__ import annotations

import json

from gqh import report
from gqh.reproduce import dumps


def test_figures_build_from_results(tmp_path):
    import test_pipeline as T

    panels, bbo, ohlcv = T._world_inputs()
    world = T.prepare(panels, cfg=T.CFG)
    res = T.evaluate(world, bbo, ohlcv, cfg=T.CFG, draws=99)
    path = tmp_path / "results.json"
    path.write_text(dumps(res))
    figs = report.build(path, tmp_path / "figs")
    assert len(figs) == 5 and all(f.stat().st_size > 5_000 for f in figs)
    assert json.loads(path.read_text())["stacked_panel"]["ME"]
