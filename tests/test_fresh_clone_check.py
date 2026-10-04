"""The reproduction wrapper must isolate files and never mask result changes."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("fresh_clone_check", Path(__file__).resolve().parents[1] / "scripts/fresh_clone_check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def entry(path="data/raw/is_statistics.dbn.zst", content=b"approved", request="is_statistics"):
    return {"request": request, "file": path, "sha256": hashlib.sha256(content).hexdigest()}


def test_only_declared_matching_inputs_are_exposed(tmp_path):
    source, scratch = tmp_path / "source", tmp_path / "scratch"
    for name in ("is_statistics", "oos_statistics", "unrelated"):
        path = source / f"data/raw/{name}.dbn.zst"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"approved")
    manifest = {"pulls": [entry(), entry("data/raw/oos_statistics.dbn.zst", request="oos_statistics")]}
    assert check.stage_inputs(source, scratch, manifest, "IS", require_factors=False) == 1
    assert (scratch / "data/raw/is_statistics.dbn.zst").read_bytes() == b"approved"
    assert not (scratch / "data/raw/oos_statistics.dbn.zst").exists()
    assert not (scratch / "data/raw/unrelated.dbn.zst").exists()


def test_hash_mismatch_stops_before_linking(tmp_path):
    source, scratch = tmp_path / "source", tmp_path / "scratch"
    path = source / "data/raw/is_statistics.dbn.zst"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        check.stage_inputs(source, scratch, {"pulls": [entry()]}, "IS", require_factors=False)
    assert not scratch.exists()


def test_required_factors_cannot_be_silently_omitted(tmp_path):
    source, scratch = tmp_path / "source", tmp_path / "scratch"
    path = source / "data/raw/is_statistics.dbn.zst"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"approved")
    with pytest.raises(FileNotFoundError, match="daily_factors.csv"):
        check.stage_inputs(source, scratch, {"pulls": [entry()]}, "IS", require_factors=True)


@pytest.mark.parametrize("path", ["/tmp/elsewhere", "data/raw/../../elsewhere", "data/factors/x.csv"])
def test_manifest_cannot_escape_raw_directory(path):
    with pytest.raises(ValueError, match="outside data/raw"):
        check.project_files({"pulls": [entry(path)]}, "ALL")


def test_conflicting_manifest_records_are_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        check.project_files({"pulls": [entry(), entry(content=b"different")]}, "ALL")


def test_comparison_exempts_only_provenance():
    expected = {"rows_IS": {"sharpe": 0.1}, "provenance": {"commit": "old"}}
    actual = {"rows_IS": {"sharpe": 0.1}, "provenance": {"commit": "new"}}
    assert check.compare_results(expected, actual)
    actual["rows_IS"]["sharpe"] = 0.2
    assert not check.compare_results(expected, actual)
    actual["rows_IS"]["sharpe"] = 0.1
    actual["extra"] = True
    assert not check.compare_results(expected, actual)
