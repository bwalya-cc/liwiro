#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIWIRO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1090
. "$SCRIPT_DIR/runtime_common.sh"

liwiro_load_env_stack

FRONTEND_ROOT="$LIWIRO_ROOT/frontend"
FRONTEND_PORT="${LIWIRO_FRONTEND_PORT:-${PORT:-3000}}"
FRONTEND_HOST="${LIWIRO_FRONTEND_HOST:-127.0.0.1}"
NEXT_PUBLIC_LIWIRO_BACKEND="${NEXT_PUBLIC_LIWIRO_BACKEND:-${LIWIRO_BACKEND_URL:-http://127.0.0.1:5000}}"
FRONTEND_BUILD_CACHE_PATH="$LIWIRO_FRONTEND_BUILD_CACHE_PATH"
FRONTEND_DEPENDENCY_STAMP="node_modules/.liwiro-dependencies-ready"

if [ "${LIWIRO_AUTO_PORTS:-1}" = "1" ] && liwiro_is_port_open "$FRONTEND_PORT"; then
  NEXT_FRONTEND_PORT="$(liwiro_find_next_free_port "$FRONTEND_PORT")"
  if [ "$NEXT_FRONTEND_PORT" != "$FRONTEND_PORT" ]; then
    liwiro_ui_warn "Frontend port $FRONTEND_PORT is already in use. Switching to $NEXT_FRONTEND_PORT."
    FRONTEND_PORT="$NEXT_FRONTEND_PORT"
  fi
fi

cd "$FRONTEND_ROOT"

liwiro_ui_section "Liwiro Frontend"
liwiro_ui_kv "Host" "$FRONTEND_HOST"
liwiro_ui_kv "Port" "$FRONTEND_PORT"
liwiro_ui_kv "Backend" "$NEXT_PUBLIC_LIWIRO_BACKEND"
liwiro_ui_kv "Build Cache" "$FRONTEND_BUILD_CACHE_PATH"

if [ ! -x "node_modules/.bin/next" ] || [ ! -f "$FRONTEND_DEPENDENCY_STAMP" ] || [ "package.json" -nt "$FRONTEND_DEPENDENCY_STAMP" ]; then
  liwiro_ui_step "Installing frontend dependencies..."
  # react-day-picker v8 is still used by the current calendar component and its
  # peer range predates React 19. Keep npm's normal protections while allowing
  # that known, narrow peer-range mismatch until the calendar is migrated.
  if [ ! -d "node_modules" ] && [ -f "package-lock.json" ]; then
    npm ci --legacy-peer-deps --no-audit --no-fund
  else
    npm install --legacy-peer-deps --no-audit --no-fund
  fi
  touch "$FRONTEND_DEPENDENCY_STAMP"
else
  liwiro_ui_ok "Frontend dependencies already installed."
fi

liwiro_ui_step "Starting frontend..."
export PORT="$FRONTEND_PORT"
export LIWIRO_FRONTEND_PORT="$FRONTEND_PORT"
export NEXT_PUBLIC_LIWIRO_BACKEND

if [ "${LIWIRO_MANAGED_STARTUP:-0}" = "1" ]; then
  BUILD_SIGNATURE="$(liwiro_compute_frontend_build_signature "$FRONTEND_ROOT" "$NEXT_PUBLIC_LIWIRO_BACKEND" 2>/dev/null || true)"
  CACHED_BUILD_SIGNATURE="$(liwiro_read_frontend_build_signature "$FRONTEND_BUILD_CACHE_PATH" 2>/dev/null || true)"
  BUILD_REASON=""

  if [ ! -f ".next/BUILD_ID" ]; then
    BUILD_REASON="production build output is missing"
  elif [ -z "${BUILD_SIGNATURE:-}" ] || [ -z "${CACHED_BUILD_SIGNATURE:-}" ]; then
    BUILD_REASON="build signature cache is unavailable"
  elif [ "$BUILD_SIGNATURE" != "$CACHED_BUILD_SIGNATURE" ]; then
    BUILD_REASON="frontend sources or build inputs changed"
  fi

  if [ -n "$BUILD_REASON" ]; then
    liwiro_ui_status "start" "Frontend build" "$BUILD_REASON"
    npm run build
    if [ -n "${BUILD_SIGNATURE:-}" ]; then
      liwiro_write_frontend_build_signature "$BUILD_SIGNATURE" "$FRONTEND_BUILD_CACHE_PATH" "$FRONTEND_ROOT" "$NEXT_PUBLIC_LIWIRO_BACKEND"
    fi
  else
    liwiro_ui_status "reuse" "Frontend build" "reusing cached production build"
  fi
  exec npm run start -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT"
fi

exec npm run dev -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT"
