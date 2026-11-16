#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-start}"
mkdir -p .cache/{tmp,pip,uv,pytest}
export TMPDIR="$ROOT/.cache/tmp" PIP_CACHE_DIR="$ROOT/.cache/pip" UV_CACHE_DIR="$ROOT/.cache/uv"
export PYTHONUTF8=1 PIP_DISABLE_PIP_VERSION_CHECK=1 STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
if [ ! -x .venv/bin/python ]; then
  PYTHON_COMMAND="${RADAR_PYTHON:-python3}"
  "$PYTHON_COMMAND" -c 'import sys;sys.exit(0 if (3,12)<=sys.version_info[:2]<(3,14) else 1)' || { echo 'Use Python 3.12 ou 3.13.'; exit 1; }
  "$PYTHON_COMMAND" -m venv .venv
fi
PYTHON="$ROOT/.venv/bin/python"
REQUIREMENTS=requirements.txt
if [ "$ACTION" = test ]; then REQUIREMENTS=requirements-dev.txt; fi
SIGNATURE="$("$PYTHON" -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('$REQUIREMENTS').read_bytes()+pathlib.Path('pyproject.toml').read_bytes()).hexdigest())")"
STAMP=".cache/dependencies-$ACTION.sha256"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$SIGNATURE" ]; then
  "$PYTHON" -m pip install -r "$REQUIREMENTS"
  "$PYTHON" -m pip install --no-deps -e .
  printf '%s' "$SIGNATURE" > "$STAMP"
fi
case "$ACTION" in
  start) exec "$PYTHON" -m streamlit run app.py --server.address=127.0.0.1 --server.headless=true --browser.gatherUsageStats=false ;;
  test) "$PYTHON" -m ruff check src tests app.py; exec "$PYTHON" -m pytest --basetemp=.cache/pytest ;;
  update) exec "$PYTHON" -m radar_inflacao update "${@:2}" ;;
  status) exec "$PYTHON" -m radar_inflacao status ;;
  setup) echo 'Ambiente preparado.' ;;
  *) echo 'Use start, test, update, status ou setup.'; exit 2 ;;
esac
