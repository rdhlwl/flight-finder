#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PORT=5050

# Kill anything already bound to our port (e.g. a previous run that didn't exit cleanly)
PIDS=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "Killing existing process(es) on port $PORT: $PIDS"
  kill -9 $PIDS 2>/dev/null || true
  sleep 1
fi

source myenv/bin/activate
export FLASK_APP=flightfinder.app
echo "Starting Flight Finder on http://127.0.0.1:$PORT"
python -m flightfinder.app
