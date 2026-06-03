#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/2] compile baseline/*.py"
python3 - <<'PY'
from pathlib import Path
import py_compile

for path in sorted(Path("baseline").glob("*.py")):
    py_compile.compile(str(path), doraise=True)
print("compiled baseline python files")
PY

echo "[2/2] pytest"
python3 -m pytest -q
