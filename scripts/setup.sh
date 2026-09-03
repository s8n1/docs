#!/usr/bin/env sh
# Install every dependency the app needs into a local virtualenv.
# The user does not install anything by hand: this script does it.
#
#   sh scripts/setup.sh
#
# Requires only: python3 (the script downloads the rest).
set -e
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
echo "[setup] using $PY ($($PY --version 2>&1))"

if [ ! -x ".venv/bin/python" ]; then
  echo "[setup] creating virtualenv at .venv/ ..."
  "$PY" -m venv .venv
fi

echo "[setup] installing dependencies into .venv/ ..."
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt

echo "[setup] verifying the engine imports cleanly ..."
.venv/bin/python -c "import numpy, scipy, sympy; import api.solver_core as s; assert len(s.MODEL_NAMES) == 42; print('[setup] OK: 42 models ready, numpy', numpy.__version__, '| scipy', scipy.__version__, '| sympy', sympy.__version__)"
