#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/app/data}"

mkdir -p "$DATA_DIR"
chown app:app "$DATA_DIR"

BINDINGS_FILE="${BINDINGS_FILE:-${DATA_DIR}/bindings.json}"

if [ ! -f "$BINDINGS_FILE" ]; then
    echo '{"chat_id": 0, "topics": {}}' > "$BINDINGS_FILE"
fi

chown app:app "$BINDINGS_FILE"

exec su-exec app gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --threads 2 --access-logfile - --error-logfile - main:app
