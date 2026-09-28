#!/usr/bin/env bash
# Start the backend in the background. Idempotent: if it is already
# running on 8000, this does nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8000

if lsof -i :$PORT | grep -q LISTEN; then
  echo "already running on $PORT"
  curl -s "http://localhost:$PORT/health" && echo
  exit 0
fi

source venv/bin/activate
ENVIRONMENT="${ENVIRONMENT:-lab}" uvicorn app.main:app \
  --host 0.0.0.0 --port $PORT \
  > /tmp/fieldproof-backend.log 2>&1 &

echo "started pid $!"
sleep 3
curl -s "http://localhost:$PORT/health" && echo
