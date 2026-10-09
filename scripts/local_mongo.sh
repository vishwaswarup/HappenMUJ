#!/usr/bin/env bash
# Docker-free alternative: run mongod as a single-node replica set (default port 27018,
# override with PORT=...). Needs mongod (brew install mongodb-community). Data: ./.mongo-data
set -euo pipefail
PORT="${PORT:-27018}"
cd "$(dirname "$0")/.."
mkdir -p .mongo-data
if ! pgrep -f "mongod.*--port ${PORT}" >/dev/null; then
  mongod --replSet rs0 --dbpath .mongo-data --port "${PORT}" --bind_ip localhost \
    --fork --logpath .mongo-data/mongod.log
fi
PORT="${PORT}" python3 - <<'PY'
import os
from pymongo import MongoClient
port = int(os.environ["PORT"])
c = MongoClient("localhost", port, directConnection=True)
try:
    c.admin.command("replSetGetStatus")
except Exception:
    c.admin.command("replSetInitiate", {"_id": "rs0", "members": [{"_id": 0, "host": f"localhost:{port}"}]})
PY
echo "mongod replica set rs0 ready on localhost:${PORT}"
