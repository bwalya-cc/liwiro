#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LIWIRO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$LIWIRO_ROOT/.." && pwd)"
VERUN_ROOT="$REPO_ROOT/verun"
PYTHON="$LIWIRO_ROOT/backend/vvv/bin/python"
STORE_HELPER="$VERUN_ROOT/vdb/scripts/bson_store.py"
RUNTIME_DIR="$(mktemp -d /tmp/liwiro_lapis_e2e_XXXXXX)"
LOG_DIR="$RUNTIME_DIR/logs"

mkdir -p "$LOG_DIR"
export VERUN_VDB_ROOT="$RUNTIME_DIR/vdb"
export LIWIRO_VDB_AUTH_CONFIG="$RUNTIME_DIR/liwiro.vdb.auth.json"
export LIWIRO_ENV_LOCAL_PATH="$RUNTIME_DIR/backend.env.local"
export LIWIRO_GENERATED_SERVICE_RUNTIME_DIR="$RUNTIME_DIR/generated-service-runtime"
export VERSE_ROOT="$LIWIRO_ROOT/verse"
export VERSE_DATA_DIR="$RUNTIME_DIR/verse-data"

free_port() {
  "$PYTHON" -c 'import socket; sock = socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()'
}

VDB_PORT="${LIWIRO_E2E_VDB_PORT:-$(free_port)}"
BACKEND_PORT="${LIWIRO_E2E_BACKEND_PORT:-$(free_port)}"
VDB_URL="http://127.0.0.1:$VDB_PORT"
BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
export VDB_HTTP_PORT="$VDB_PORT"
export VDB_SERVER_URL="$VDB_URL"
export LIWIRO_BACKEND_URL="$BACKEND_URL"
export VDB_TRANSPORT="http"

demo_suffix="${PPID}_$VDB_PORT"
export LIWIRO_E2E_SUPER_ADMIN_USER="${LIWIRO_E2E_SUPER_ADMIN_USER:-e2eadmin_$demo_suffix}"
export LIWIRO_E2E_SUPER_ADMIN_PASS="${LIWIRO_E2E_SUPER_ADMIN_PASS:-Liwiro-E2E-${demo_suffix}-Root1!}"
export LIWIRO_E2E_VDB_APP_USER="${LIWIRO_E2E_VDB_APP_USER:-liwiro_e2e_$demo_suffix}"
export LIWIRO_E2E_VDB_APP_PASS="${LIWIRO_E2E_VDB_APP_PASS:-Liwiro-E2E-${demo_suffix}-App1!}"

VDB_PID=""
BACKEND_PID=""

cleanup() {
  status="$?"
  trap - EXIT INT TERM
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$VDB_PID" ] && kill -0 "$VDB_PID" >/dev/null 2>&1; then
    kill "$VDB_PID" >/dev/null 2>&1 || true
    wait "$VDB_PID" >/dev/null 2>&1 || true
  fi
  if [ "$status" -ne 0 ]; then
    if [ -f "$LOG_DIR/backend.log" ]; then
      echo "[E2E] Backend log tail:"
      tail -n 80 "$LOG_DIR/backend.log" || true
    fi
    if [ -f "$LOG_DIR/vdb.log" ]; then
      echo "[E2E] VDB log tail:"
      tail -n 80 "$LOG_DIR/vdb.log" || true
    fi
  fi
  rm -rf "$RUNTIME_DIR"
  exit "$status"
}
trap cleanup EXIT INT TERM

wait_http() {
  url="$1"
  timeout="${2:-60}"
  end=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "$end" ]; do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

run_lapis_preflight() {
  if [ "${LIWIRO_E2E_ALLOW_MISSING_EXTERNAL:-0}" = "1" ]; then
    "$PYTHON" "$LIWIRO_ROOT/backend/scripts/e2e_lapis_examples_live.py" --preflight --allow-missing-external
  else
    "$PYTHON" "$LIWIRO_ROOT/backend/scripts/e2e_lapis_examples_live.py" --preflight
  fi
}

run_lapis_live() {
  if [ "${LIWIRO_E2E_ALLOW_MISSING_EXTERNAL:-0}" = "1" ]; then
    "$PYTHON" "$LIWIRO_ROOT/backend/scripts/e2e_lapis_examples_live.py" --allow-missing-external
  else
    "$PYTHON" "$LIWIRO_ROOT/backend/scripts/e2e_lapis_examples_live.py"
  fi
}

echo "[E2E] Checking all LAPIS examples and external integration credentials..."
run_lapis_preflight

if [ "${LIWIRO_E2E_SKIP_QUALITY_GATES:-0}" != "1" ]; then
  echo "[E2E] Running quality gates..."
  (
    cd "$VERUN_ROOT"
    mvn test >"$LOG_DIR/maven-test.log" 2>&1
    mvn -pl vdb,vi -am -DskipTests package >"$LOG_DIR/maven-package.log" 2>&1
  )
  (
    cd "$LIWIRO_ROOT/backend"
    ./vvv/bin/python -m pytest -q >"$LOG_DIR/pytest.log" 2>&1
  )
  (
    cd "$LIWIRO_ROOT/frontend"
    npm run lint >"$LOG_DIR/frontend-lint.log" 2>&1
    npm run build >"$LOG_DIR/frontend-build.log" 2>&1
  )
fi

echo "[E2E] Creating isolated VDB users..."
mkdir -p "$VERUN_VDB_ROOT/__data__/sys/users"
if [ ! -s "$VERUN_ROOT/vdb/__data__/sys/mit-license-acceptance.bson" ]; then
  echo "[E2E] Existing MIT acceptance record is required before the isolated VDB can start." >&2
  exit 1
fi
mkdir -p "$VERUN_VDB_ROOT/__data__/sys"
cp "$VERUN_ROOT/vdb/__data__/sys/mit-license-acceptance.bson" "$VERUN_VDB_ROOT/__data__/sys/mit-license-acceptance.bson"

super_hash="$(E2E_PASSWORD="$LIWIRO_E2E_SUPER_ADMIN_PASS" python3 -c 'import bcrypt, os; print(bcrypt.hashpw(os.environ["E2E_PASSWORD"].encode(), bcrypt.gensalt()).decode().replace("$2b$", "$2a$", 1))')"
app_hash="$(E2E_PASSWORD="$LIWIRO_E2E_VDB_APP_PASS" python3 -c 'import bcrypt, os; print(bcrypt.hashpw(os.environ["E2E_PASSWORD"].encode(), bcrypt.gensalt()).decode().replace("$2b$", "$2a$", 1))')"
python3 "$STORE_HELPER" upsert-user "$VERUN_VDB_ROOT/__data__/sys/users/users.bson" \
  "$LIWIRO_E2E_SUPER_ADMIN_USER" "${LIWIRO_E2E_SUPER_ADMIN_USER}@local.test" SUPER_ADMIN "$super_hash" default liwiro
python3 "$STORE_HELPER" upsert-user "$VERUN_VDB_ROOT/__data__/sys/users/users.bson" \
  "$LIWIRO_E2E_VDB_APP_USER" "${LIWIRO_E2E_VDB_APP_USER}@local.test" APPLICATION "$app_hash" default liwiro

echo "[E2E] Starting isolated VDB on $VDB_URL..."
(
  cd "$VERUN_ROOT/vdb"
  exec ./scripts/serve.sh >"$LOG_DIR/vdb.log" 2>&1
) &
VDB_PID="$!"
wait_http "$VDB_URL/health" 90 || { echo "[E2E] VDB failed to start"; exit 1; }

echo "[E2E] Starting isolated backend on $BACKEND_URL..."
(
  cd "$LIWIRO_ROOT/backend"
  export VDB_USERNAME="$LIWIRO_E2E_VDB_APP_USER"
  export VDB_PASSWORD="$LIWIRO_E2E_VDB_APP_PASS"
  export LIWIRO_APP_USERNAME="$LIWIRO_E2E_VDB_APP_USER"
  export LIWIRO_APP_PASSWORD="$LIWIRO_E2E_VDB_APP_PASS"
  export VDB_SUPER_ADMIN_USERNAME="$LIWIRO_E2E_SUPER_ADMIN_USER"
  export VDB_SUPER_ADMIN_PASSWORD="$LIWIRO_E2E_SUPER_ADMIN_PASS"
  export LIWIRO_DOMAIN="liwiro"
  export LIWIRO_DB="config"
  export FLASK_APP="app.main:create_app"
  export FLASK_DEBUG="false"
  export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
  exec ./vvv/bin/python -m flask run --no-debugger --no-reload --host 127.0.0.1 --port "$BACKEND_PORT" >"$LOG_DIR/backend.log" 2>&1
) &
BACKEND_PID="$!"
wait_http "$BACKEND_URL/auth/status" 120 || { echo "[E2E] Backend failed to start"; exit 1; }

echo "[E2E] Generating all LAPIS examples and exercising every declared endpoint..."
run_lapis_live

echo "[E2E] Running backend endpoint sweep..."
(
  cd "$LIWIRO_ROOT/backend"
  ./vvv/bin/python scripts/e2e_backend_endpoints_live.py
)

echo "[E2E] PASS"
