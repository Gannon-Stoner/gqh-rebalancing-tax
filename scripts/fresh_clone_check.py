"""Rebuild a committed revision from verified, isolated licensed inputs.

This is a reproduction check, not a new strategy trial. Only the selected
revision's manifest-declared IS/OOS files are exposed to the scratch pipeline.
The source checkout's results, derived files, and trial log are never written.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def project_files(manifest: dict, sample: str) -> dict[Path, str]:
    """Unique approved raw paths and hashes, excluding pilot/unrelated requests."""
    prefixes = ("is_", "oos_") if sample == "ALL" else ("is_",)
    files: dict[Path, str] = {}
    for record in manifest["pulls"]:
        request = record.get("parent_request", record["request"])
        if not request.startswith(prefixes):
            continue
        rel = Path(record["file"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[:2] != ("data", "raw"):
            raise ValueError(f"manifest path is outside data/raw: {rel}")
        digest = record["sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"invalid SHA-256 for {rel}")
        if rel in files and files[rel] != digest:
            raise ValueError(f"conflicting manifest hashes for {rel}")
        files[rel] = digest
    if not files:
        raise ValueError(f"manifest has no {sample} project inputs")
    return files


def stage_inputs(source: Path, scratch: Path, manifest: dict, sample: str,
                 *, require_factors: bool) -> int:
    """Validate every selected hash before creating per-file links in scratch."""
    files = project_files(manifest, sample)
    for rel, expected in files.items():
        path = source / rel
        if not path.is_file():
            raise FileNotFoundError(f"missing licensed input: {rel}; use the documented data pull")
        if sha256(path) != expected:
            raise ValueError(f"SHA-256 mismatch: {rel}; refusing an unverified reproduction")
    factors = source / "data/factors/daily_factors.csv"
    if require_factors and not factors.is_file():
        raise FileNotFoundError("missing data/factors/daily_factors.csv; run data/download_factors.py")
    for rel in files:
        target = scratch / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to((source / rel).resolve())
    if factors.is_file():
        target = scratch / "data/factors/daily_factors.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(factors, target)
    return len(files)


def result_content(result: dict) -> dict:
    """Comparison excludes only the top-level run-location/provenance block."""
    return {key: value for key, value in result.items() if key != "provenance"}


def compare_results(expected: dict, actual: dict) -> bool:
    want, got = result_content(expected), result_content(actual)
    if want == got:
        print("MATCH: every result value and field outside top-level provenance is identical.")
        return True
    print("MISMATCH: result content differs (first 80 diff lines):")
    diff = difflib.unified_diff(json.dumps(want, indent=2, sort_keys=True).splitlines(),
                                json.dumps(got, indent=2, sort_keys=True).splitlines(),
                                fromfile="committed results", tofile="scratch rebuild", lineterm="")
    for i, line in enumerate(diff):
        if i >= 80:
            break
        print(line)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(
        "Rebuild a local committed revision from manifest-verified licensed data in a temporary clone. "
        "Compare all result content exactly, excluding only top-level provenance, which is reported separately. "
        "Uncommitted source edits are not included; source results and trial logs remain untouched."))
    parser.add_argument("commit", nargs="?", default="HEAD")
    parser.add_argument("sample", nargs="?", choices=("IS", "ALL"), default="IS")
    parser.add_argument("--inputs-only", action="store_true", help="verify and isolate inputs without running analysis")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "--verify", "--end-of-options",
                                         f"{args.commit}^{{commit}}"], cwd=source, text=True).strip()
    filename = "results_is.json" if args.sample == "IS" else "results.json"
    print(f"Checking committed revision {revision} ({args.sample}); uncommitted edits are excluded.", flush=True)
    with tempfile.TemporaryDirectory(prefix="gqh-reproduce-") as tmp:
        scratch = Path(tmp) / "repo"
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(source), str(scratch)], check=True)
        subprocess.run(["git", "checkout", "--quiet", revision], cwd=scratch, check=True)
        expected = json.loads((scratch / filename).read_text())
        manifest = json.loads((scratch / "data/manifest.json").read_text())
        count = stage_inputs(source, scratch, manifest, args.sample,
                             require_factors=bool(expected.get("inputs", {}).get("factors")))
        print(f"Verified SHA-256 and isolated {count} declared raw files; unrelated files are excluded.", flush=True)
        if args.inputs_only:
            print("Input checks passed. The analysis was not run.")
            return 0
        output = Path(tmp) / filename
        env = dict(os.environ, PYTHONPATH=str(scratch / "src"))
        subprocess.run([sys.executable, "-m", "gqh.reproduce", "--sample", args.sample,
                        "--rebuild", "--out", str(output)], cwd=scratch, env=env, check=True)
        actual = json.loads(output.read_text())
        matched = compare_results(expected, actual)
        print("Provenance is excluded from equality and shown separately:")
        print(json.dumps({"committed": expected.get("provenance"), "rebuilt": actual.get("provenance")}, indent=2, sort_keys=True))
        return 0 if matched else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Reproduction check failed: {exc}") from exc
