#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIWIRO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$LIWIRO_ROOT/.." && pwd)"
VERUN_ROOT="$(cd "$REPO_ROOT/verun" && pwd)"
AUTH_CONFIG_PATH_DEFAULT="$LIWIRO_ROOT/backend/.runtime/liwiro.vdb.auth.json"
TOOLS_CACHE_PATH="$REPO_ROOT/tmp/runtime-tools.json"

# shellcheck disable=SC1090
. "$SCRIPT_DIR/runtime_common.sh"

liwiro_load_env_stack

AUTH_CONFIG_PATH="${LIWIRO_VDB_AUTH_CONFIG:-${LIWIRO_AUTH_PATH:-$AUTH_CONFIG_PATH_DEFAULT}}"
RUNTIME_LOG_DIR="$REPO_ROOT/tmp/runtime-logs"
VDB_WORKDIR="${LIWIRO_VDB_WORKDIR:-$RUNTIME_LOG_DIR/vdb-workdir}"
VDB_HTTP_LOG_PATH="$RUNTIME_LOG_DIR/vdb-http.log"
VDB_NAMEDPIPE_LOG_PATH="$RUNTIME_LOG_DIR/vdb-namedpipe.log"
VDB_UNIXSOCKET_LOG_PATH="$RUNTIME_LOG_DIR/vdb-unixsocket.log"
BACKEND_LOG_PATH="$RUNTIME_LOG_DIR/backend.log"
FRONTEND_LOG_PATH="$RUNTIME_LOG_DIR/frontend.log"
STARTED_SERVICE_NAMES=()
STARTED_SERVICE_PIDS=()
STARTED_SERVICE_PGIDS=()
STARTED_SERVICE_ENDPOINT_KINDS=()
STARTED_SERVICE_ENDPOINT_VALUES=()
REUSED_SERVICE_NAMES=()
REUSED_SERVICE_ENDPOINT_KINDS=()
REUSED_SERVICE_ENDPOINT_VALUES=()
CURRENT_SHELL_PGID="$(liwiro_process_group_id "$$" 2>/dev/null || true)"
CLEANUP_DONE=0
LAST_STARTED_PID=""

mkdir -p "$RUNTIME_LOG_DIR"
mkdir -p "$VDB_WORKDIR"

liwiro_runtime_service_panel() {
  local title="$1"
  local target="$2"
  local log_path="${3:-}"
  liwiro_ui_newline
  liwiro_ui_section "$title"
  liwiro_ui_kv "Target" "$target"
  if [ -n "$log_path" ]; then
    liwiro_ui_kv "Log" "$log_path"
  fi
}

liwiro_register_started_service() {
  local name="$1"
  local pid="$2"
  local pgid="${3:-}"
  local endpoint_kind="${4:-}"
  local endpoint_value="${5:-}"
  STARTED_SERVICE_NAMES+=("$name")
  STARTED_SERVICE_PIDS+=("$pid")
  STARTED_SERVICE_PGIDS+=("$pgid")
  STARTED_SERVICE_ENDPOINT_KINDS+=("$endpoint_kind")
  STARTED_SERVICE_ENDPOINT_VALUES+=("$endpoint_value")
}

liwiro_register_reused_service() {
  local name="$1"
  local endpoint_kind="$2"
  local endpoint_value="$3"
  local index

  for index in "${!REUSED_SERVICE_ENDPOINT_VALUES[@]}"; do
    if [ "${REUSED_SERVICE_ENDPOINT_KINDS[$index]}" = "$endpoint_kind" ] && [ "${REUSED_SERVICE_ENDPOINT_VALUES[$index]}" = "$endpoint_value" ]; then
      return 0
    fi
  done

  REUSED_SERVICE_NAMES+=("$name")
  REUSED_SERVICE_ENDPOINT_KINDS+=("$endpoint_kind")
  REUSED_SERVICE_ENDPOINT_VALUES+=("$endpoint_value")
}

liwiro_launch_logged_service() {
  local name="$1"
  local working_dir="$2"
  local log_path="$3"
  local endpoint_kind="${4:-}"
  local endpoint_value="${5:-}"
  shift 5

  : >"$log_path"
  if command -v setsid >/dev/null 2>&1; then
    (
      cd "$working_dir"
      exec setsid "$@"
    ) >>"$log_path" 2>&1 &
  else
    (
      cd "$working_dir"
      exec "$@"
    ) >>"$log_path" 2>&1 &
  fi

  local pid="$!"
  LAST_STARTED_PID="$pid"
  local pgid
  pgid="$(liwiro_process_group_id "$pid" 2>/dev/null || true)"
  if [ -n "$CURRENT_SHELL_PGID" ] && [ "$pgid" = "$CURRENT_SHELL_PGID" ]; then
    pgid=""
  fi
  liwiro_register_started_service "$name" "$pid" "$pgid" "$endpoint_kind" "$endpoint_value"
  if [ -n "$pgid" ]; then
    liwiro_ui_status "info" "$name" "tracking pid $pid (pgid $pgid)"
  else
    liwiro_ui_status "info" "$name" "tracking pid $pid"
  fi
}

liwiro_cleanup_started_endpoint() {
  local name="$1"
  local endpoint_kind="${2:-}"
  local endpoint_value="${3:-}"
  case "$endpoint_kind" in
    tcp)
      if [ -n "$endpoint_value" ] && liwiro_is_port_open "$endpoint_value"; then
        liwiro_ui_warn "$name left a listener on port $endpoint_value after shutdown. Cleaning the managed endpoint."
        liwiro_kill_port_listeners "$endpoint_value"
      fi
      ;;
    unixsocket)
      if [ -n "$endpoint_value" ] && { [ -S "$endpoint_value" ] || [ -n "$(liwiro_socket_pids "$endpoint_value")" ]; }; then
        liwiro_ui_warn "$name left a listener on socket $endpoint_value after shutdown. Cleaning the managed endpoint."
        liwiro_kill_unix_socket_listeners "$endpoint_value"
      fi
      ;;
  esac
}

liwiro_cleanup_reused_endpoint() {
  local name="$1"
  local endpoint_kind="${2:-}"
  local endpoint_value="${3:-}"
  case "$endpoint_kind" in
    tcp)
      if [ -n "$endpoint_value" ] && liwiro_is_port_open "$endpoint_value"; then
        liwiro_ui_status "stop" "$name" "closing reused listener on port $endpoint_value"
        liwiro_kill_port_listeners "$endpoint_value"
      fi
      ;;
    unixsocket)
      if [ -n "$endpoint_value" ] && { [ -S "$endpoint_value" ] || [ -n "$(liwiro_socket_pids "$endpoint_value")" ]; }; then
        liwiro_ui_status "stop" "$name" "closing reused listener on socket $endpoint_value"
        liwiro_kill_unix_socket_listeners "$endpoint_value"
      fi
      ;;
  esac
}

cleanup() {
  if [ "$CLEANUP_DONE" -eq 1 ]; then
    return 0
  fi
  CLEANUP_DONE=1
  liwiro_ui_newline
  liwiro_ui_section "Stopping Services"
  if [ "${#STARTED_SERVICE_PIDS[@]}" -eq 0 ] && [ "${#REUSED_SERVICE_ENDPOINT_VALUES[@]}" -eq 0 ]; then
    liwiro_ui_status "info" "Cleanup" "no local services require cleanup"
    liwiro_ui_ok "All services stopped."
    return 0
  fi

  local index
  local name
  local pid
  local pgid
  local endpoint_kind
  local endpoint_value
  local target_pid
  local survivors

  for index in "${!STARTED_SERVICE_PIDS[@]}"; do
    name="${STARTED_SERVICE_NAMES[$index]}"
    pid="${STARTED_SERVICE_PIDS[$index]}"
    pgid="${STARTED_SERVICE_PGIDS[$index]}"

    if [ -n "$pgid" ]; then
      liwiro_ui_status "stop" "$name" "sending TERM to process group $pgid"
      kill -TERM -- "-$pgid" >/dev/null 2>&1 || true
    elif liwiro_pid_running "$pid"; then
      liwiro_ui_status "stop" "$name" "sending TERM to pid $pid"
      kill -TERM "$pid" >/dev/null 2>&1 || true
    fi
  done

  if [ "${#STARTED_SERVICE_PIDS[@]}" -gt 0 ]; then
    sleep 2
  fi

  for index in "${!STARTED_SERVICE_PIDS[@]}"; do
    name="${STARTED_SERVICE_NAMES[$index]}"
    pid="${STARTED_SERVICE_PIDS[$index]}"
    pgid="${STARTED_SERVICE_PGIDS[$index]}"
    endpoint_kind="${STARTED_SERVICE_ENDPOINT_KINDS[$index]}"
    endpoint_value="${STARTED_SERVICE_ENDPOINT_VALUES[$index]}"

    survivors="$(liwiro_process_group_members "$pgid" 2>/dev/null | awk -v self="$$" 'NF && $1 != self')"
    if [ -n "$survivors" ]; then
      liwiro_ui_warn "$name still has running process-group members: $(printf '%s' "$survivors" | tr '\n' ' ')"
      while IFS= read -r target_pid; do
        [ -n "$target_pid" ] || continue
        kill -KILL "$target_pid" >/dev/null 2>&1 || true
      done <<<"$survivors"
    fi

    if liwiro_pid_running "$pid"; then
      liwiro_ui_warn "$name root pid $pid ignored TERM. Force killing it."
      kill -KILL "$pid" >/dev/null 2>&1 || true
    fi

    while IFS= read -r target_pid; do
      [ -n "$target_pid" ] || continue
      if liwiro_pid_running "$target_pid"; then
        liwiro_ui_warn "$name descendant pid $target_pid ignored TERM. Force killing it."
        kill -KILL "$target_pid" >/dev/null 2>&1 || true
      fi
    done < <(liwiro_descendant_pids "$pid" 2>/dev/null || true)

    liwiro_cleanup_started_endpoint "$name" "$endpoint_kind" "$endpoint_value"
  done

  for index in "${!REUSED_SERVICE_ENDPOINT_VALUES[@]}"; do
    liwiro_cleanup_reused_endpoint \
      "${REUSED_SERVICE_NAMES[$index]}" \
      "${REUSED_SERVICE_ENDPOINT_KINDS[$index]}" \
      "${REUSED_SERVICE_ENDPOINT_VALUES[$index]}"
  done

  wait || true
  liwiro_ui_ok "All services stopped."
}

trap cleanup INT TERM EXIT

load_saved_vdb_connection() {
  if [ ! -f "$AUTH_CONFIG_PATH" ] || ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi

  while IFS='=' read -r key value; do
    value="${value%$'\r'}"
    case "$key" in
      VDB_TRANSPORT) [ -z "${VDB_TRANSPORT:-}" ] && [ -n "${value:-}" ] && export VDB_TRANSPORT="$value" ;;
      VDB_SERVER_URL) [ -z "${VDB_SERVER_URL:-}" ] && [ -n "${value:-}" ] && export VDB_SERVER_URL="$value" ;;
      VDB_UNIX_SOCKET_PATH) [ -z "${VDB_UNIX_SOCKET_PATH:-}" ] && [ -n "${value:-}" ] && export VDB_UNIX_SOCKET_PATH="$value" ;;
      VDB_NAMED_PIPE_PATH) [ -z "${VDB_NAMED_PIPE_PATH:-}" ] && [ -n "${value:-}" ] && export VDB_NAMED_PIPE_PATH="$value" ;;
      VDB_USERNAME) [ -z "${VDB_USERNAME:-}" ] && [ -n "${value:-}" ] && export VDB_USERNAME="$value" ;;
      LIWIRO_DOMAIN) [ -z "${LIWIRO_DOMAIN:-}" ] && [ -n "${value:-}" ] && export LIWIRO_DOMAIN="$value" ;;
      LIWIRO_DB) [ -z "${LIWIRO_DB:-}" ] && [ -n "${value:-}" ] && export LIWIRO_DB="$value" ;;
    esac
  done < <(
    python3 - "$AUTH_CONFIG_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

mapping = {
    "VDB_TRANSPORT": data.get("vdb_transport"),
    "VDB_SERVER_URL": data.get("vdb_server_url"),
    "VDB_UNIX_SOCKET_PATH": data.get("vdb_unix_socket_path"),
    "VDB_NAMED_PIPE_PATH": data.get("vdb_named_pipe_path"),
    "VDB_USERNAME": data.get("vdb_username"),
    "LIWIRO_DOMAIN": data.get("liwiro_domain"),
    "LIWIRO_DB": data.get("liwiro_db"),
}
for key, value in mapping.items():
    text = str(value or "").strip()
    if text:
        print(f"{key}={text}")
PY
  )
  return 0
}

load_saved_vdb_connection

HOST_PLATFORM="$(liwiro_detect_host_platform)"
HOST_SCRIPT_FAMILY="$(liwiro_platform_family "$HOST_PLATFORM")"
REQUESTED_VDB_TRANSPORT="${VDB_TRANSPORT:-}"
VDB_SOCKET_PATH="$(liwiro_resolve_vdb_socket_path)"
VDB_NAMED_PIPE_PATH="$(liwiro_resolve_vdb_named_pipe_path)"
VDB_TRANSPORT="$(liwiro_normalize_vdb_transport "$REQUESTED_VDB_TRANSPORT" "$HOST_PLATFORM")"
VDB_HTTP_URL="$(liwiro_resolve_vdb_http_url "${VDB_SERVER_URL:-}")"

if [ "$VDB_TRANSPORT" != "unixsocket" ] && liwiro_is_local_http_url "$VDB_HTTP_URL"; then
  DEFAULT_VDB_HTTP_PORT="$(liwiro_http_url_port "$VDB_HTTP_URL")"
  if liwiro_is_http_healthy "$(liwiro_http_url_with_port "$VDB_HTTP_URL" "$DEFAULT_VDB_HTTP_PORT")/health"; then
    VDB_HTTP_PORT="$DEFAULT_VDB_HTTP_PORT"
  elif liwiro_is_port_open "$DEFAULT_VDB_HTTP_PORT"; then
    VDB_HTTP_PORT="$(liwiro_find_next_free_port "${VDB_HTTP_PORT:-$DEFAULT_VDB_HTTP_PORT}")"
  else
    VDB_HTTP_PORT="$DEFAULT_VDB_HTTP_PORT"
  fi
  VDB_HTTP_URL="$(liwiro_http_url_with_port "$VDB_HTTP_URL" "$VDB_HTTP_PORT")"
else
  VDB_HTTP_PORT="$(liwiro_http_url_port "$VDB_HTTP_URL")"
fi
VDB_HTTP_HEALTH_URL="${VDB_HTTP_URL%/}/health"

DEFAULT_BACKEND_PORT="${FLASK_PORT:-${LIWIRO_BACKEND_PORT:-5000}}"
DEFAULT_FRONTEND_PORT="${LIWIRO_FRONTEND_PORT:-${PORT:-3000}}"
LIWIRO_CLOSE_PREVIOUS_INSTANCES="${LIWIRO_CLOSE_PREVIOUS_INSTANCES:-1}"
VDB_ACTIVE_LOG_PATH=""

liwiro_ui_banner "Liwiro Runtime" "Managed startup for VDB, backend, and frontend"
liwiro_ui_kv "Host OS" "$HOST_PLATFORM"
liwiro_ui_kv "Family" "$HOST_SCRIPT_FAMILY"
liwiro_ui_kv "Transport" "$VDB_TRANSPORT"
liwiro_ui_kv "Auth Cache" "$AUTH_CONFIG_PATH"
liwiro_ui_kv "Platform Cache" "$LIWIRO_PLATFORM_CACHE_PATH"
liwiro_ui_kv "Tools Cache" "$TOOLS_CACHE_PATH"
liwiro_ui_kv "Runtime Logs" "$RUNTIME_LOG_DIR"
if [ -n "$REQUESTED_VDB_TRANSPORT" ] && [ "$REQUESTED_VDB_TRANSPORT" != "$VDB_TRANSPORT" ]; then
  liwiro_ui_warn "Adjusted VDB transport from $REQUESTED_VDB_TRANSPORT to $VDB_TRANSPORT for host platform $HOST_PLATFORM."
fi

if [ "$LIWIRO_CLOSE_PREVIOUS_INSTANCES" = "1" ]; then
  liwiro_ui_newline
  liwiro_ui_section "Preflight"
  if [ "$VDB_TRANSPORT" = "http" ] && liwiro_is_local_http_url "$VDB_HTTP_URL"; then
    if liwiro_is_http_healthy "$VDB_HTTP_HEALTH_URL"; then
      liwiro_ui_status "reuse" "VDB HTTP" "keeping existing healthy listener at $VDB_HTTP_URL"
    elif liwiro_is_port_open "$(liwiro_http_url_port "$VDB_HTTP_URL")"; then
      liwiro_ui_status "start" "Cleanup" "removing stale VDB HTTP listener on port $(liwiro_http_url_port "$VDB_HTTP_URL")"
      liwiro_kill_port_listeners "$(liwiro_http_url_port "$VDB_HTTP_URL")"
    else
      liwiro_ui_status "info" "Cleanup" "no stale VDB HTTP listener detected"
    fi
  elif [ "$VDB_TRANSPORT" = "unixsocket" ]; then
    if liwiro_is_unix_socket_healthy "$VDB_SOCKET_PATH"; then
      liwiro_ui_status "reuse" "VDB socket" "keeping existing healthy socket at $VDB_SOCKET_PATH"
    elif [ -S "$VDB_SOCKET_PATH" ] || [ -n "$(liwiro_socket_pids "$VDB_SOCKET_PATH")" ]; then
      liwiro_ui_status "start" "Cleanup" "removing stale VDB Unix socket at $VDB_SOCKET_PATH"
      liwiro_kill_unix_socket_listeners "$VDB_SOCKET_PATH"
    else
      liwiro_ui_status "info" "Cleanup" "no stale VDB Unix socket detected"
    fi
  fi
fi

if liwiro_is_http_healthy "http://127.0.0.1:$DEFAULT_BACKEND_PORT/auth/status"; then
  BACKEND_PORT="$DEFAULT_BACKEND_PORT"
elif liwiro_is_port_open "$DEFAULT_BACKEND_PORT"; then
  BACKEND_PORT="$(liwiro_find_next_free_port "$DEFAULT_BACKEND_PORT")"
else
  BACKEND_PORT="$DEFAULT_BACKEND_PORT"
fi
if liwiro_is_http_healthy "http://127.0.0.1:$DEFAULT_FRONTEND_PORT/login"; then
  FRONTEND_PORT="$DEFAULT_FRONTEND_PORT"
elif liwiro_is_port_open "$DEFAULT_FRONTEND_PORT"; then
  FRONTEND_PORT="$(liwiro_find_next_free_port "$DEFAULT_FRONTEND_PORT")"
else
  FRONTEND_PORT="$DEFAULT_FRONTEND_PORT"
fi
BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"

export VDB_UNIX_SOCKET_PATH="$VDB_SOCKET_PATH"
export VDB_NAMED_PIPE_PATH="$VDB_NAMED_PIPE_PATH"
export VDB_TRANSPORT="$VDB_TRANSPORT"
export VDB_SERVER_URL="$VDB_HTTP_URL"
export VDB_HTTP_PORT="$VDB_HTTP_PORT"
export FLASK_PORT="$BACKEND_PORT"
export LIWIRO_BACKEND_PORT="$BACKEND_PORT"
export LIWIRO_BACKEND_URL="$BACKEND_URL"
export LIWIRO_FRONTEND_PORT="$FRONTEND_PORT"
export LIWIRO_FRONTEND="$FRONTEND_URL"
export NEXT_PUBLIC_LIWIRO_BACKEND="$BACKEND_URL"
export LIWIRO_VDB_AUTH_CONFIG="$AUTH_CONFIG_PATH"
export LIWIRO_AUTH_PATH="$AUTH_CONFIG_PATH"
export LIWIRO_RUNTIME_LOG_DIR="$RUNTIME_LOG_DIR"

bash "$VERUN_ROOT/vdb/scripts/ensure_mit_acceptance.sh" "start_all"

liwiro_start_vdb_http() {
  VDB_ACTIVE_LOG_PATH="$VDB_HTTP_LOG_PATH"
  liwiro_runtime_service_panel "VDB HTTP" "$VDB_HTTP_URL" "$VDB_HTTP_LOG_PATH"
  if liwiro_is_http_healthy "$VDB_HTTP_HEALTH_URL"; then
    liwiro_ui_status "reuse" "VDB HTTP" "already healthy at $VDB_HTTP_URL"
    if [ "$LIWIRO_CLOSE_PREVIOUS_INSTANCES" = "1" ]; then
      liwiro_register_reused_service "VDB HTTP" "tcp" "$VDB_HTTP_PORT"
    fi
    return 0
  fi
  liwiro_ui_status "start" "VDB HTTP" "launching local server on port $VDB_HTTP_PORT"
  liwiro_launch_logged_service "VDB HTTP" "$VDB_WORKDIR" "$VDB_HTTP_LOG_PATH" "tcp" "$VDB_HTTP_PORT" env VDB_HTTP_PORT="$VDB_HTTP_PORT" bash "$VERUN_ROOT/vdb/scripts/serve.sh"
  liwiro_wait_for_http_health "VDB HTTP" "$VDB_HTTP_HEALTH_URL" "${LIWIRO_VDB_STARTUP_TIMEOUT:-60}" "$VDB_HTTP_LOG_PATH" "$LAST_STARTED_PID"
}

liwiro_stop_failed_vdb_ipc() {
  local pid="${LAST_STARTED_PID:-}"
  if [ -n "$pid" ] && liwiro_pid_running "$pid"; then
    kill -TERM "$pid" >/dev/null 2>&1 || true
    sleep 1
    liwiro_pid_running "$pid" && kill -KILL "$pid" >/dev/null 2>&1 || true
  fi
  if [ "$VDB_TRANSPORT" = "unixsocket" ] && { [ -S "$VDB_SOCKET_PATH" ] || [ -n "$(liwiro_socket_pids "$VDB_SOCKET_PATH")" ]; }; then
    liwiro_kill_unix_socket_listeners "$VDB_SOCKET_PATH"
  fi
}

if [ "$VDB_TRANSPORT" = "http" ]; then
  if liwiro_is_local_http_url "$VDB_HTTP_URL"; then
    liwiro_start_vdb_http
  else
    liwiro_runtime_service_panel "VDB HTTP" "$VDB_HTTP_URL"
    liwiro_ui_status "info" "VDB HTTP" "using remote target"
  fi
elif [ "$VDB_TRANSPORT" = "namedpipe" ]; then
  VDB_ACTIVE_LOG_PATH="$VDB_NAMEDPIPE_LOG_PATH"
  liwiro_runtime_service_panel "VDB Named Pipe" "namedpipe://$VDB_NAMED_PIPE_PATH" "$VDB_NAMEDPIPE_LOG_PATH"
	  if liwiro_is_named_pipe_healthy "$VDB_NAMED_PIPE_PATH"; then
	    liwiro_ui_status "reuse" "VDB pipe" "already healthy at $VDB_NAMED_PIPE_PATH"
	  else
	    liwiro_ui_status "start" "VDB pipe" "launching local named-pipe interface"
	    liwiro_launch_logged_service "VDB pipe" "$VDB_WORKDIR" "$VDB_NAMEDPIPE_LOG_PATH" "namedpipe" "$VDB_NAMED_PIPE_PATH" env VDB_NAMED_PIPE_PATH="$VDB_NAMED_PIPE_PATH" bash "$VERUN_ROOT/vdb/scripts/namedpipe.sh"
	    if ! liwiro_wait_for_named_pipe_health "VDB named pipe" "$VDB_NAMED_PIPE_PATH" "${LIWIRO_VDB_STARTUP_TIMEOUT:-60}" "$VDB_NAMEDPIPE_LOG_PATH" "$LAST_STARTED_PID"; then
	      liwiro_ui_warn "VDB IPC failed; reverting to the HTTP server."
      liwiro_stop_failed_vdb_ipc
      VDB_TRANSPORT="http"
      export VDB_TRANSPORT
      if liwiro_is_local_http_url "$VDB_HTTP_URL"; then
        liwiro_start_vdb_http
      else
        liwiro_ui_error "VDB IPC failed and no local HTTP fallback is configured ($VDB_HTTP_URL)."
        exit 1
      fi
	    fi
	  fi
	else
  VDB_ACTIVE_LOG_PATH="$VDB_UNIXSOCKET_LOG_PATH"
  liwiro_runtime_service_panel "VDB Unix Socket" "unix://$VDB_SOCKET_PATH" "$VDB_UNIXSOCKET_LOG_PATH"
	  if liwiro_is_unix_socket_healthy "$VDB_SOCKET_PATH"; then
	    liwiro_ui_status "reuse" "VDB socket" "already healthy at $VDB_SOCKET_PATH"
	    if [ "$LIWIRO_CLOSE_PREVIOUS_INSTANCES" = "1" ]; then
	      liwiro_register_reused_service "VDB socket" "unixsocket" "$VDB_SOCKET_PATH"
	    fi
	  else
	    liwiro_ui_status "start" "VDB socket" "launching local unix-socket interface"
	    liwiro_launch_logged_service "VDB socket" "$VDB_WORKDIR" "$VDB_UNIXSOCKET_LOG_PATH" "unixsocket" "$VDB_SOCKET_PATH" env VDB_UNIX_SOCKET_PATH="$VDB_SOCKET_PATH" bash "$VERUN_ROOT/vdb/scripts/socket.sh"
	    if ! liwiro_wait_for_unix_socket_health "VDB Unix socket" "$VDB_SOCKET_PATH" "${LIWIRO_VDB_STARTUP_TIMEOUT:-60}" "$VDB_UNIXSOCKET_LOG_PATH" "$LAST_STARTED_PID"; then
	      liwiro_ui_warn "VDB IPC failed; reverting to the HTTP server."
      liwiro_stop_failed_vdb_ipc
      VDB_TRANSPORT="http"
      export VDB_TRANSPORT
      if liwiro_is_local_http_url "$VDB_HTTP_URL"; then
        liwiro_start_vdb_http
      else
        liwiro_ui_error "VDB IPC failed and no local HTTP fallback is configured ($VDB_HTTP_URL)."
        exit 1
      fi
	    fi
	  fi
	fi

liwiro_runtime_service_panel "Liwiro Backend" "$BACKEND_URL" "$BACKEND_LOG_PATH"
if liwiro_is_http_healthy "$BACKEND_URL/auth/status"; then
  liwiro_ui_status "reuse" "Backend" "already healthy at $BACKEND_URL"
  if [ "$LIWIRO_CLOSE_PREVIOUS_INSTANCES" = "1" ]; then
    liwiro_register_reused_service "Backend" "tcp" "$BACKEND_PORT"
  fi
else
  liwiro_ui_status "start" "Backend" "launching Flask backend on port $BACKEND_PORT"
  liwiro_launch_logged_service "Backend" "$LIWIRO_ROOT/backend" "$BACKEND_LOG_PATH" "tcp" "$BACKEND_PORT" env LIWIRO_MANAGED_STARTUP=1 FLASK_HOST=127.0.0.1 LIWIRO_FRONTEND="$FRONTEND_URL" bash ./scripts/backend-start.sh
  liwiro_wait_for_http_health "Backend" "$BACKEND_URL/auth/status" "${LIWIRO_BACKEND_STARTUP_TIMEOUT:-300}" "$BACKEND_LOG_PATH" "$LAST_STARTED_PID"
fi

liwiro_runtime_service_panel "Liwiro Frontend" "$FRONTEND_URL" "$FRONTEND_LOG_PATH"
if liwiro_is_http_healthy "$FRONTEND_URL/login"; then
  liwiro_ui_status "reuse" "Frontend" "already healthy at $FRONTEND_URL"
  if [ "$LIWIRO_CLOSE_PREVIOUS_INSTANCES" = "1" ]; then
    liwiro_register_reused_service "Frontend" "tcp" "$FRONTEND_PORT"
  fi
else
  liwiro_ui_status "start" "Frontend" "launching Next.js frontend on port $FRONTEND_PORT"
  liwiro_launch_logged_service "Frontend" "$LIWIRO_ROOT" "$FRONTEND_LOG_PATH" "tcp" "$FRONTEND_PORT" env LIWIRO_MANAGED_STARTUP=1 bash "./scripts/$HOST_SCRIPT_FAMILY/start_front.sh"
  liwiro_wait_for_http_health "Frontend" "$FRONTEND_URL/login" "${LIWIRO_FRONTEND_STARTUP_TIMEOUT:-1800}" "$FRONTEND_LOG_PATH" "$LAST_STARTED_PID"
fi

if [ "${LIWIRO_PLATFORM_CACHE_STATUS:-miss}" != "hit" ]; then
  liwiro_write_platform_cache "$HOST_PLATFORM"
  liwiro_ui_ok "Cached detected host platform: $HOST_PLATFORM ($LIWIRO_PLATFORM_CACHE_PATH)"
fi

liwiro_ui_newline
liwiro_ui_section "Services Ready"
if [ "$VDB_TRANSPORT" = "http" ]; then
  liwiro_ui_kv "VDB HTTP" "$VDB_HTTP_URL"
  liwiro_ui_kv "VDB IPC" "disabled while HTTP transport is active"
elif [ "$VDB_TRANSPORT" = "namedpipe" ]; then
  liwiro_ui_kv "VDB HTTP" "inactive"
  liwiro_ui_kv "VDB IPC" "namedpipe://$VDB_NAMED_PIPE_PATH"
else
  liwiro_ui_kv "VDB IPC" "unix://$VDB_SOCKET_PATH"
  liwiro_ui_kv "VDB HTTP" "inactive"
fi
if [ -n "$VDB_ACTIVE_LOG_PATH" ]; then
  liwiro_ui_kv "VDB Log" "$VDB_ACTIVE_LOG_PATH"
fi
liwiro_ui_kv "Backend" "$BACKEND_URL"
liwiro_ui_kv "Frontend" "$FRONTEND_URL"
liwiro_ui_kv "Backend Log" "$BACKEND_LOG_PATH"
liwiro_ui_kv "Frontend Log" "$FRONTEND_LOG_PATH"
liwiro_ui_kv "Python Cache" "$TOOLS_CACHE_PATH"
liwiro_ui_kv "Runtime Logs" "$RUNTIME_LOG_DIR"
liwiro_ui_newline
liwiro_ui_info "Press Ctrl+C to stop everything."

wait
