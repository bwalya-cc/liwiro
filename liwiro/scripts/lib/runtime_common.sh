#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

if [ -n "${LIWIRO_RUNTIME_COMMON_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
LIWIRO_RUNTIME_COMMON_LOADED=1

LIWIRO_RUNTIME_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIWIRO_SCRIPTS_DIR="$(cd "$LIWIRO_RUNTIME_LIB_DIR/.." && pwd)"
LIWIRO_ROOT="$(cd "$LIWIRO_SCRIPTS_DIR/.." && pwd)"
LIWIRO_REPO_ROOT="$(cd "$LIWIRO_ROOT/.." && pwd)"
LIWIRO_PLATFORM_CACHE_PATH="${LIWIRO_PLATFORM_CACHE_PATH:-$LIWIRO_REPO_ROOT/tmp/platform-runtime.json}"
LIWIRO_FRONTEND_BUILD_CACHE_PATH="${LIWIRO_FRONTEND_BUILD_CACHE_PATH:-$LIWIRO_REPO_ROOT/tmp/frontend-managed-build.json}"

# shellcheck disable=SC1090
. "$LIWIRO_RUNTIME_LIB_DIR/terminal_ui.sh"

liwiro_source_env_file() {
  local file_path="$1"
  if [ -f "$file_path" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$file_path"
    set +a
  fi
}

liwiro_load_env_stack() {
  local env_files=(
    "$LIWIRO_ROOT/.env"
    "$LIWIRO_ROOT/.env.local"
    "$LIWIRO_ROOT/backend/.env"
    "$LIWIRO_ROOT/backend/.env.local"
    "$LIWIRO_ROOT/frontend/.env"
    "$LIWIRO_ROOT/frontend/.env.local"
  )
  local file_path
  for file_path in "${env_files[@]}"; do
    liwiro_source_env_file "$file_path"
  done
}

liwiro_read_frontend_build_signature() {
  local cache_path="${1:-$LIWIRO_FRONTEND_BUILD_CACHE_PATH}"
  if [ ! -f "$cache_path" ]; then
    return 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$cache_path" <<'PY' 2>/dev/null
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

signature = str((payload or {}).get("signature") or "").strip()
if signature:
    print(signature)
    raise SystemExit(0)
raise SystemExit(1)
PY
    return $?
  fi

  local signature
  signature="$(grep -E '"signature"[[:space:]]*:[[:space:]]*"' "$cache_path" 2>/dev/null | head -n 1 | sed -E 's/.*"signature"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
  if [ -n "$signature" ]; then
    printf '%s\n' "$signature"
    return 0
  fi
  return 1
}

liwiro_write_frontend_build_signature() {
  local signature="$1"
  local cache_path="${2:-$LIWIRO_FRONTEND_BUILD_CACHE_PATH}"
  local frontend_root="${3:-$LIWIRO_ROOT/frontend}"
  local backend_url="${4:-${NEXT_PUBLIC_LIWIRO_BACKEND:-}}"

  mkdir -p "$(dirname "$cache_path")"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$cache_path" "$signature" "$frontend_root" "$backend_url" <<'PY'
import json
import sys
from pathlib import Path

cache_path = Path(sys.argv[1])
signature = str(sys.argv[2] or "").strip()
frontend_root = str(sys.argv[3] or "").strip()
backend_url = str(sys.argv[4] or "").strip()

payload = {
    "schema": 1,
    "signature": signature,
    "frontend_root": frontend_root,
    "next_public_backend": backend_url,
}
cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
    return 0
  fi

  cat >"$cache_path" <<EOF
{"schema":1,"signature":"$signature","frontend_root":"$frontend_root","next_public_backend":"$backend_url"}
EOF
}

liwiro_compute_frontend_build_signature() {
  local frontend_root="${1:-$LIWIRO_ROOT/frontend}"
  local backend_url="${2:-${NEXT_PUBLIC_LIWIRO_BACKEND:-}}"
  if ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi

  python3 - "$LIWIRO_ROOT" "$frontend_root" "$backend_url" <<'PY'
import hashlib
import sys
from pathlib import Path

liwiro_root = Path(sys.argv[1]).resolve()
frontend_root = Path(sys.argv[2]).resolve()
backend_url = str(sys.argv[3] or "").strip()

tracked_paths = [
    frontend_root / "app",
    frontend_root / "components",
    frontend_root / "hooks",
    frontend_root / "lib",
    frontend_root / "public",
    frontend_root / "styles",
    frontend_root / "package.json",
    frontend_root / "package-lock.json",
    frontend_root / "next.config.mjs",
    frontend_root / "tsconfig.json",
    frontend_root / "postcss.config.mjs",
    frontend_root / "tailwind.config.ts",
    liwiro_root / ".env",
    liwiro_root / ".env.local",
    liwiro_root / "backend/.env",
    liwiro_root / "backend/.env.local",
    frontend_root / ".env",
    frontend_root / ".env.local",
]

hasher = hashlib.sha256()
hasher.update(f"NEXT_PUBLIC_LIWIRO_BACKEND={backend_url}\n".encode("utf-8"))

for candidate in tracked_paths:
    rel_candidate = candidate.relative_to(liwiro_root)
    hasher.update(f"path={rel_candidate}\n".encode("utf-8"))
    if not candidate.exists():
        hasher.update(b"missing\n")
        continue
    if candidate.is_file():
        stat = candidate.stat()
        hasher.update(f"file={rel_candidate}|{stat.st_size}|{stat.st_mtime_ns}\n".encode("utf-8"))
        continue
    for file_path in sorted(path for path in candidate.rglob("*") if path.is_file()):
        rel_path = file_path.relative_to(liwiro_root)
        stat = file_path.stat()
        hasher.update(f"file={rel_path}|{stat.st_size}|{stat.st_mtime_ns}\n".encode("utf-8"))

print(hasher.hexdigest())
PY
}

liwiro_read_cached_platform() {
  local cache_path="${1:-$LIWIRO_PLATFORM_CACHE_PATH}"
  if [ ! -f "$cache_path" ]; then
    return 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$cache_path" <<'PY' 2>/dev/null
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

platform_name = str((payload or {}).get("platform") or "").strip().lower()
if platform_name in {"windows", "linux", "macos"}:
    print(platform_name)
    raise SystemExit(0)
raise SystemExit(1)
PY
    return $?
  fi

  local cached
  cached="$(grep -E '"platform"[[:space:]]*:[[:space:]]*"' "$cache_path" 2>/dev/null | head -n 1 | sed -E 's/.*"platform"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/' | tr '[:upper:]' '[:lower:]')"
  case "$cached" in
    windows|linux|macos)
      printf '%s\n' "$cached"
      return 0
      ;;
  esac
  return 1
}

liwiro_detect_host_platform() {
  local cached
  cached="$(liwiro_read_cached_platform 2>/dev/null || true)"
  case "$cached" in
    windows|linux|macos)
      LIWIRO_PLATFORM_CACHE_STATUS="hit"
      printf '%s\n' "$cached"
      return 0
      ;;
  esac

  LIWIRO_PLATFORM_CACHE_STATUS="miss"
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import os
import platform
import sys

system_name = str(platform.system() or "").strip().lower()
os_name = str(os.name or "").strip().lower()
sys_platform = str(sys.platform or "").strip().lower()

if os_name == "nt" or sys_platform.startswith("win") or system_name.startswith("win"):
    print("windows")
elif system_name == "darwin" or sys_platform == "darwin":
    print("macos")
elif system_name.startswith("linux") or sys_platform.startswith("linux"):
    print("linux")
elif os_name == "posix":
    print("linux")
else:
    print(system_name or "linux")
PY
    return 0
  fi

  if [ "${OS:-}" = "Windows_NT" ] || [ -n "${COMSPEC:-}" ] || [ -n "${WINDIR:-}" ] || [ -n "${SYSTEMROOT:-}" ]; then
    printf 'windows\n'
    return 0
  fi

  case "$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')" in
    mingw*|msys*|cygwin*) printf 'windows\n' ;;
    darwin*) printf 'macos\n' ;;
    linux*) printf 'linux\n' ;;
    *) printf 'linux\n' ;;
  esac
}

liwiro_write_platform_cache() {
  local platform_name="$1"
  local cache_path="${2:-$LIWIRO_PLATFORM_CACHE_PATH}"
  mkdir -p "$(dirname "$cache_path")"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$cache_path" "$platform_name" <<'PY'
import json
import os
import platform
import sys
from pathlib import Path

path = Path(sys.argv[1])
platform_name = str(sys.argv[2] or "").strip().lower() or "linux"
payload = {
    "schema": 1,
    "platform": platform_name,
    "system": str(platform.system() or "").strip(),
    "os_name": str(os.name or "").strip(),
    "sys_platform": str(sys.platform or "").strip(),
    "machine": str(platform.machine() or "").strip(),
    "release": str(platform.release() or "").strip(),
    "detected_by": "runtime_common.sh",
    "cache_path": str(path),
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
    return 0
  fi

  cat >"$cache_path" <<EOF
{"schema":1,"platform":"$platform_name","detected_by":"runtime_common.sh","cache_path":"$cache_path"}
EOF
}

liwiro_platform_family() {
  local host_platform="${1:-linux}"
  if [ "$host_platform" = "windows" ]; then
    printf 'win\n'
  else
    printf 'unix\n'
  fi
}

liwiro_platform_script_path() {
  local script_name="$1"
  local host_platform="$2"
  printf '%s/%s/%s\n' "$LIWIRO_SCRIPTS_DIR" "$(liwiro_platform_family "$host_platform")" "$script_name"
}

liwiro_normalize_vdb_transport() {
  local requested="${1:-}"
  local platform_name="${2:-linux}"
  local normalized
  normalized="$(printf '%s' "$requested" | tr '[:upper:]' '[:lower:]' | tr '-' '_')"
  case "$normalized" in
    http|httpserver|http_server|tcp|tcp_loopback)
      printf 'http\n'
      return 0
      ;;
    # IPC is a logical selection: resolve it to the native interface for the
    # host instead of treating a named pipe as Windows-only configuration.
    namedpipe|named_pipe|pipe|ipc|af_pipe)
      if [ "$platform_name" = "windows" ]; then
        printf 'namedpipe\n'
      else
        printf 'unixsocket\n'
      fi
      return 0
      ;;
    unixsocket|unix_socket|unix|socket|uds)
      if [ "$platform_name" = "windows" ]; then
        printf 'namedpipe\n'
      else
        printf 'unixsocket\n'
      fi
      return 0
      ;;
    ""|default|auto)
      ;;
  esac

  if [ "$platform_name" = "windows" ]; then
    printf 'namedpipe\n'
  else
    printf 'unixsocket\n'
  fi
}

liwiro_resolve_vdb_socket_path() {
  if [ -n "${VDB_UNIX_SOCKET_PATH:-}" ]; then
    printf '%s\n' "$VDB_UNIX_SOCKET_PATH"
    return 0
  fi
  if [ -n "${VDB_INTERFACE_UNIXSOCKET_PATH:-}" ]; then
    printf '%s\n' "$VDB_INTERFACE_UNIXSOCKET_PATH"
    return 0
  fi
  if [ -d /run ] && [ -w /run ]; then
    printf '/run/vdb.sock\n'
    return 0
  fi
  printf '/tmp/vdb.sock\n'
}

liwiro_resolve_vdb_named_pipe_path() {
  local configured="${VDB_NAMED_PIPE_PATH:-}"
  if [ -z "$configured" ] && [ -n "${VDB_INTERFACE_NAMEDPIPE_PATH:-}" ]; then
    configured="$VDB_INTERFACE_NAMEDPIPE_PATH"
  fi
  if [ -z "$configured" ]; then
    configured='\\.\pipe\verun_vdb'
  fi
  configured="${configured//$'\r'/}"
  configured="${configured//$'\v'/\\v}"
  configured="${configured//\//\\}"
  local pipe_name="${configured##*\\}"
  case "$pipe_name" in
    ""|"."|"pipe")
      pipe_name="verun_vdb"
      ;;
  esac
  printf '\\\\.\\pipe\\%s\n' "$pipe_name"
}

liwiro_resolve_vdb_http_url() {
  local server_url="${1:-${VDB_SERVER_URL:-}}"
  if [ -n "${server_url:-}" ]; then
    printf '%s\n' "$server_url"
    return 0
  fi
  printf 'http://127.0.0.1:1957\n'
}

liwiro_http_url_port() {
  local server_url="${1:-http://127.0.0.1:1957}"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$server_url" <<'PY'
from urllib.parse import urlparse
import sys

url = (sys.argv[1] or "").strip() or "http://127.0.0.1:1957"
parsed = urlparse(url if "://" in url else f"http://{url}")
print(parsed.port or 1957)
PY
    return 0
  fi
  printf '%s\n' "$server_url" | sed -E 's#.*:([0-9]+).*#\1#'
}

liwiro_http_url_with_port() {
  local server_url="$1"
  local port="$2"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$server_url" "$port" <<'PY'
from urllib.parse import urlparse
import sys

url = (sys.argv[1] or "").strip() or "http://127.0.0.1:1957"
port = int(sys.argv[2] or 1957)
parsed = urlparse(url if "://" in url else f"http://{url}")
scheme = parsed.scheme or "http"
host = parsed.hostname or "127.0.0.1"
print(f"{scheme}://{host}:{port}")
PY
    return 0
  fi
  printf 'http://127.0.0.1:%s\n' "$port"
}

liwiro_is_local_http_url() {
  local server_url="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$server_url" <<'PY'
from urllib.parse import urlparse
import socket
import sys

url = (sys.argv[1] or "").strip() or "http://127.0.0.1:1957"
parsed = urlparse(url if "://" in url else f"http://{url}")
host = (parsed.hostname or "").strip().lower()
if not host:
    raise SystemExit(1)

aliases = {"localhost", "127.0.0.1", "::1"}
for candidate in (socket.gethostname(), socket.getfqdn()):
    text = str(candidate or "").strip().lower()
    if text:
        aliases.add(text)

local_ips = {"127.0.0.1", "::1"}
for candidate in aliases:
    try:
        for info in socket.getaddrinfo(candidate, None):
            resolved = str(info[4][0] or "").strip().lower()
            if resolved:
                local_ips.add(resolved)
    except OSError:
        continue

if host in aliases or host in local_ips:
    raise SystemExit(0)

try:
    for info in socket.getaddrinfo(host, None):
        resolved = str(info[4][0] or "").strip().lower()
        if resolved in local_ips:
            raise SystemExit(0)
except OSError:
    pass

raise SystemExit(1)
PY
    return $?
  fi
  case "$server_url" in
    *127.0.0.1*|*localhost*) return 0 ;;
  esac
  return 1
}

liwiro_is_port_open() {
  local port="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

try:
    port = int(sys.argv[1] or 0)
except (TypeError, ValueError):
    raise SystemExit(1)

if port <= 0 or port > 65535:
    raise SystemExit(1)

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except OSError:
    raise SystemExit(2)
try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
except PermissionError:
    raise SystemExit(2)
except OSError:
    raise SystemExit(0)
finally:
    sock.close()

raise SystemExit(1)
PY
    local bind_status=$?
    if [ "$bind_status" -ne 2 ]; then
      return "$bind_status"
    fi
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" >/dev/null 2>&1
    return $?
  fi
  (echo >"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
}

liwiro_port_pids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' || true
    return
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "( sport = :$port )" 2>/dev/null | awk -F'pid=' 'NR>1 && NF>1 {split($2,a,","); print a[1]}' || true
    return
  fi
}

liwiro_pid_running() {
  local pid="$1"
  [ -n "${pid:-}" ] || return 1
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  # A child that has exited but has not yet been reaped still answers kill -0.
  # Treat zombie/dead process states as stopped so readiness checks fail fast.
  if command -v ps >/dev/null 2>&1; then
    local process_state
    process_state="$(ps -o stat= -p "$pid" 2>/dev/null | awk 'NF { print substr($1, 1, 1); exit }')"
    case "$process_state" in
      ""|Z|X) return 1 ;;
    esac
  fi
  return 0
}

liwiro_process_group_id() {
  local pid="$1"
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  if command -v ps >/dev/null 2>&1; then
    ps -o pgid= -p "$pid" 2>/dev/null | awk 'NF { gsub(/[[:space:]]/, "", $0); print; exit }'
    return 0
  fi
  return 1
}

liwiro_process_group_members() {
  local pgid="$1"
  case "$pgid" in
    ''|*[!0-9]*) return 0 ;;
  esac
  if command -v ps >/dev/null 2>&1; then
    ps -eo pid=,pgid= 2>/dev/null | awk -v target="$pgid" '$2 == target { print $1 }'
  fi
}

liwiro_descendant_pids() {
  local root_pid="$1"
  case "$root_pid" in
    ''|*[!0-9]*) return 0 ;;
  esac
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$root_pid" <<'PY' 2>/dev/null
import subprocess
import sys

try:
    root_pid = int(sys.argv[1] or 0)
except (TypeError, ValueError):
    raise SystemExit(0)

if root_pid <= 0:
    raise SystemExit(0)

try:
    output = subprocess.check_output(
        ["ps", "-eo", "pid=,ppid="],
        text=True,
        stderr=subprocess.DEVNULL,
    )
except Exception:
    raise SystemExit(0)

children = {}
for line in output.splitlines():
    parts = line.split()
    if len(parts) != 2:
        continue
    try:
        pid = int(parts[0])
        parent_pid = int(parts[1])
    except (TypeError, ValueError):
        continue
    children.setdefault(parent_pid, []).append(pid)

queue = list(children.get(root_pid, []))
seen = []
visited = set(queue)
while queue:
    current = queue.pop(0)
    seen.append(current)
    for child in children.get(current, []):
        if child in visited:
            continue
        visited.add(child)
        queue.append(child)

for pid in seen:
    print(pid)
PY
}

liwiro_socket_pids() {
  local socket_path="$1"
  if [ ! -e "$socket_path" ]; then
    return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -- "$socket_path" 2>/dev/null | awk 'NF && !seen[$0]++' || true
    return
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser "$socket_path" 2>/dev/null | tr ' ' '\n' | awk 'NF && !seen[$0]++' || true
    return
  fi
}

liwiro_kill_port_listeners() {
  local port="$1"
  local targets
  targets="$(liwiro_port_pids "$port")"
  if [ -z "${targets:-}" ]; then
    return 0
  fi
  liwiro_ui_warn "Stopping stale process(es) on port $port: $targets"
  local pid
  for pid in $targets; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  sleep 1
  targets="$(liwiro_port_pids "$port")"
  if [ -n "${targets:-}" ]; then
    liwiro_ui_warn "Force killing stubborn process(es) on port $port: $targets"
    for pid in $targets; do
      kill -9 "$pid" >/dev/null 2>&1 || true
    done
    sleep 1
  fi
}

liwiro_cleanup_unix_socket() {
  local socket_path="$1"
  if [ -S "$socket_path" ] && ! liwiro_is_unix_socket_healthy "$socket_path"; then
    liwiro_ui_warn "Removing stale Unix socket at $socket_path"
    rm -f "$socket_path"
  fi
}

liwiro_kill_unix_socket_listeners() {
  local socket_path="$1"
  local targets
  targets="$(liwiro_socket_pids "$socket_path")"
  if [ -n "${targets:-}" ]; then
    liwiro_ui_warn "Stopping stale process(es) using socket $socket_path: $targets"
    local pid
    for pid in $targets; do
      kill "$pid" >/dev/null 2>&1 || true
    done
    sleep 1
    targets="$(liwiro_socket_pids "$socket_path")"
    if [ -n "${targets:-}" ]; then
      liwiro_ui_warn "Force killing stubborn process(es) using socket $socket_path: $targets"
      for pid in $targets; do
        kill -9 "$pid" >/dev/null 2>&1 || true
      done
      sleep 1
    fi
  fi
  liwiro_cleanup_unix_socket "$socket_path"
}

liwiro_find_next_free_port() {
  local start_port="$1"
  local port="$start_port"
  while [ "$port" -le 65535 ]; do
    if ! liwiro_is_port_open "$port"; then
      printf '%s\n' "$port"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

liwiro_is_http_healthy() {
  local url="$1"
  curl -fsS --max-time 3 "$url" >/dev/null 2>&1
}

liwiro_preview_log_tail() {
  local log_path="$1"
  local title="${2:-Recent log output}"
  local lines="${3:-12}"
  if [ -z "${log_path:-}" ] || [ ! -f "$log_path" ]; then
    return 0
  fi
  liwiro_ui_newline
  liwiro_ui_section "$title"
  while IFS= read -r line; do
    printf '  %s%s%s\n' "$LIWIRO_UI_DIM" "$line" "$LIWIRO_UI_RESET" >&2
  done < <(grep -v '^[[:space:]]*$' "$log_path" 2>/dev/null | tail -n "$lines" || true)
}

liwiro_preview_log_diagnosis() {
  local service_name="$1"
  local log_path="$2"
  if [ -z "${log_path:-}" ] || [ ! -f "$log_path" ]; then
    return 0
  fi
  local diagnosis
  diagnosis="$(python3 - "$service_name" "$log_path" <<'PY' 2>/dev/null || true
import re
import sys
from pathlib import Path

service_name = (sys.argv[1] or "").strip()
log_path = Path(sys.argv[2])
try:
    text = log_path.read_text(encoding="utf-8", errors="replace")
except Exception:
    raise SystemExit(0)

normalized = text.replace("\r\n", "\n")
lines = [line.strip() for line in normalized.splitlines() if line.strip()]
lower = normalized.lower()

def emit(*items: str) -> None:
    print("\n".join(item for item in items if item))

if "next/font" in lower and "google fonts" in lower:
    layout_match = re.search(r"(?m)^([A-Za-z0-9_./-]+layout\.[A-Za-z0-9_]+)$", normalized)
    fetch_match = re.search(r"Failed to fetch `([^`]+)` from Google Fonts\.", normalized)
    font_name = fetch_match.group(1) if fetch_match else "a Google Font"
    source_file = layout_match.group(1) if layout_match else "app/layout.tsx"
    emit(
        f"{service_name} failed during the managed Next.js build.",
        f"Root cause: next/font could not download {font_name} from Google Fonts.",
        f"Source: {source_file}",
        "Likely fix: switch that font to a local asset or use a network-available build environment.",
    )
    raise SystemExit(0)

if "failed to compile" in lower:
    first_error = ""
    for line in lines:
        if "error" in line.lower():
            first_error = line
            break
    emit(
        f"{service_name} failed during startup compilation.",
        f"Primary clue: {first_error}" if first_error else "",
    )
    raise SystemExit(0)

if "timed out" in lower or "etimedout" in lower:
    emit(
        f"{service_name} hit a timeout during startup.",
        "Check the retained log for the blocking external fetch or stalled build step.",
    )
    raise SystemExit(0)
PY
)"
  if [ -z "${diagnosis:-}" ]; then
    return 0
  fi
  liwiro_ui_newline
  liwiro_ui_section "$service_name diagnosis"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    printf '  %s%s%s\n' "$LIWIRO_UI_DIM" "$line" "$LIWIRO_UI_RESET" >&2
  done <<<"$diagnosis"
}

liwiro_wait_for_http_health() {
  local name="$1"
  local url="$2"
  local timeout="${3:-60}"
  local log_path="${4:-}"
  local service_pid="${5:-}"
  local elapsed=0
  liwiro_ui_status "wait" "$name" "health check $url"
  until liwiro_is_http_healthy "$url"; do
    if [ -n "$service_pid" ] && ! liwiro_pid_running "$service_pid"; then
      liwiro_ui_error "$name exited before becoming healthy at $url."
      if [ -n "$log_path" ]; then
        liwiro_ui_status "log" "$name log" "$log_path"
        liwiro_preview_log_diagnosis "$name" "$log_path"
        liwiro_preview_log_tail "$log_path" "$name log tail" 14
      fi
      return 1
    fi
    if [ "$elapsed" -ge "$timeout" ]; then
      liwiro_ui_error "$name did not become healthy at $url within ${timeout}s."
      if [ -n "$log_path" ]; then
        liwiro_ui_status "log" "$name log" "$log_path"
        liwiro_preview_log_diagnosis "$name" "$log_path"
        liwiro_preview_log_tail "$log_path" "$name log tail" 14
      fi
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    if [ $((elapsed % 10)) -eq 0 ]; then
      liwiro_ui_status "wait" "$name" "still waiting (${elapsed}s/${timeout}s)"
    fi
  done
  liwiro_ui_status "ready" "$name" "healthy after ${elapsed}s -> $url"
}

liwiro_is_unix_socket_healthy() {
  local socket_path="$1"
  [ -S "$socket_path" ] || return 1
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$socket_path" <<'PY' >/dev/null 2>&1
import socket
import sys

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(1.0)
try:
    sock.connect(sys.argv[1])
finally:
    sock.close()
PY
}

liwiro_wait_for_unix_socket_health() {
  local name="$1"
  local socket_path="$2"
  local timeout="${3:-60}"
  local log_path="${4:-}"
  local service_pid="${5:-}"
  local elapsed=0
  liwiro_ui_status "wait" "$name" "health check unix://$socket_path"
  until liwiro_is_unix_socket_healthy "$socket_path"; do
    if [ -n "$service_pid" ] && ! liwiro_pid_running "$service_pid"; then
      liwiro_ui_error "$name exited before becoming healthy on socket $socket_path."
      if [ -n "$log_path" ]; then
        liwiro_ui_status "log" "$name log" "$log_path"
        liwiro_preview_log_diagnosis "$name" "$log_path"
        liwiro_preview_log_tail "$log_path" "$name log tail" 14
      fi
      return 1
    fi
    if [ "$elapsed" -ge "$timeout" ]; then
      liwiro_ui_error "$name did not become healthy on socket $socket_path within ${timeout}s."
      if [ -n "$log_path" ]; then
        liwiro_ui_status "log" "$name log" "$log_path"
        liwiro_preview_log_diagnosis "$name" "$log_path"
        liwiro_preview_log_tail "$log_path" "$name log tail" 14
      fi
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    if [ $((elapsed % 10)) -eq 0 ]; then
      liwiro_ui_status "wait" "$name" "still waiting (${elapsed}s/${timeout}s)"
    fi
  done
  liwiro_ui_status "ready" "$name" "healthy after ${elapsed}s -> unix://$socket_path"
}

liwiro_is_named_pipe_healthy() {
  local pipe_path="$1"
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "\$path = '$pipe_path'; if (\$path -match '^\\\\\\\\\\.\\\\pipe\\\\(.+)$') { \$name = \$Matches[1]; \$client = New-Object System.IO.Pipes.NamedPipeClientStream('.', \$name, [System.IO.Pipes.PipeDirection]::InOut); try { \$client.Connect(500); \$client.Dispose(); exit 0 } catch { if (\$client) { \$client.Dispose() }; exit 1 } } exit 1" >/dev/null 2>&1
    return $?
  fi
  return 1
}

liwiro_wait_for_named_pipe_health() {
  local name="$1"
  local pipe_path="$2"
  local timeout="${3:-60}"
  local log_path="${4:-}"
  local service_pid="${5:-}"
  local elapsed=0
  liwiro_ui_status "wait" "$name" "health check namedpipe://$pipe_path"
  until liwiro_is_named_pipe_healthy "$pipe_path"; do
    if [ -n "$service_pid" ] && ! liwiro_pid_running "$service_pid"; then
      liwiro_ui_error "$name exited before becoming healthy on pipe $pipe_path."
      if [ -n "$log_path" ]; then
        liwiro_ui_status "log" "$name log" "$log_path"
        liwiro_preview_log_diagnosis "$name" "$log_path"
        liwiro_preview_log_tail "$log_path" "$name log tail" 14
      fi
      return 1
    fi
    if [ "$elapsed" -ge "$timeout" ]; then
      liwiro_ui_error "$name did not become healthy on pipe $pipe_path within ${timeout}s."
      if [ -n "$log_path" ]; then
        liwiro_ui_status "log" "$name log" "$log_path"
        liwiro_preview_log_diagnosis "$name" "$log_path"
        liwiro_preview_log_tail "$log_path" "$name log tail" 14
      fi
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    if [ $((elapsed % 10)) -eq 0 ]; then
      liwiro_ui_status "wait" "$name" "still waiting (${elapsed}s/${timeout}s)"
    fi
  done
  liwiro_ui_status "ready" "$name" "healthy after ${elapsed}s -> namedpipe://$pipe_path"
}
