#!/usr/bin/env bash
# Rebuild a committed local revision in isolation; see --help for the comparison scope.
# Uses the active Python environment (or GQH_PYTHON), without downloading anything.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
exec "${GQH_PYTHON:-python3}" "$here/scripts/fresh_clone_check.py" "$@"
