#!/usr/bin/env sh
# Start the whole product with a single command. If dependencies are missing
# they are installed first, so nothing else needs to be done by hand.
#
#   sh scripts/serve.sh          # → http://0.0.0.0:8000
#   PORT=8080 sh scripts/serve.sh
set -e
cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  echo "[serve] dependencies not found — running setup first"
  sh scripts/setup.sh
elif ! .venv/bin/python -c "import numpy, scipy, sympy, fastapi, uvicorn" >/dev/null 2>&1; then
  echo "[serve] dependencies incomplete — running setup first"
  sh scripts/setup.sh
fi

PORT="${PORT:-${API_PORT:-8000}}"
echo "[serve] DiffEQ Engine listening on http://0.0.0.0:$PORT (UI + API + 42-model engine)"
exec .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
