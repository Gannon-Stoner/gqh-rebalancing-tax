#!/usr/bin/env bash
# Fresh-clone reproduction (run order step 7): clone the pushed repo at a commit into a
# temporary directory, link the licensed raw data (never committed), rebuild every number
# from scratch, and compare the results file byte for byte with this checkout's.
#
# Usage: scripts/fresh_clone_check.sh [COMMIT] [IS|ALL]
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
commit="${1:-$(git -C "$here" rev-parse HEAD)}"
sample="${2:-IS}"
out_name=$([ "$sample" = "IS" ] && echo results_is.json || echo results.json)
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone --quiet "$(git -C "$here" remote get-url origin)" "$tmp/repo"
git -C "$tmp/repo" checkout --quiet "$commit"
git -C "$tmp/repo" fetch --quiet --tags
ln -s "$here/data/raw" "$tmp/repo/data/raw"                      # licensed Databento files
mkdir -p "$tmp/repo/data/factors"
cp "$here/data/factors/daily_factors.csv" "$tmp/repo/data/factors/" 2>/dev/null || true   # public, re-downloadable

(cd "$tmp/repo" && PYTHONPATH=src python3 -m gqh.reproduce --sample "$sample" --rebuild --out "$tmp/$out_name")
a="$(shasum -a 256 "$here/$out_name" | cut -d' ' -f1)"
b="$(shasum -a 256 "$tmp/$out_name" | cut -d' ' -f1)"
echo "checkout:    $a  $out_name"
echo "fresh clone: $b  $out_name (commit $commit)"
[ "$a" = "$b" ] && echo "IDENTICAL" || { echo "DIFFERENT"; diff <(python3 -m json.tool "$here/$out_name") <(python3 -m json.tool "$tmp/$out_name") | head -40; exit 1; }
