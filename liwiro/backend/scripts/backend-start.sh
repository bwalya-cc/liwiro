#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIWIRO_ROOT="$(cd "$BACKEND_ROOT/.." && pwd)"
REPO_ROOT="$(cd "$LIWIRO_ROOT/.." && pwd)"
UI_LIB="$LIWIRO_ROOT/scripts/lib/terminal_ui.sh"
RUNTIME_LIB="$LIWIRO_ROOT/scripts/lib/runtime_common.sh"
VENV_DIR="$BACKEND_ROOT/vvv"
TOOLS_CACHE_PATH="$REPO_ROOT/tmp/runtime-tools.json"
PYTHON=${PYTHON:-}
REQUIREMENTS_FILE="$BACKEND_ROOT/requirements.txt"
REQUIREMENTS_STAMP="$VENV_DIR/.requirements-installed.stamp"
RUNTIME_HELPERS_AVAILABLE=0

if [ -f "$RUNTIME_LIB" ]; then
    # shellcheck disable=SC1090
    . "$RUNTIME_LIB"
    liwiro_load_env_stack
    RUNTIME_HELPERS_AVAILABLE=1
elif [ -f "$UI_LIB" ]; then
    # shellcheck disable=SC1090
    . "$UI_LIB"
else
    liwiro_ui_section() { printf '%s\n' "$*" >&2; }
    liwiro_ui_step() { printf '%s\n' "$*" >&2; }
    liwiro_ui_ok() { printf '%s\n' "$*" >&2; }
    liwiro_ui_warn() { printf '%s\n' "$*" >&2; }
    liwiro_ui_error() { printf '%s\n' "$*" >&2; }
    liwiro_ui_info() { printf '%s\n' "$*" >&2; }
    liwiro_ui_kv() { printf '  %s: %s\n' "$1" "$2" >&2; }
    liwiro_ui_newline() { printf '\n' >&2; }
fi

is_enabled() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

read_cached_python_path() {
    if [ ! -f "$TOOLS_CACHE_PATH" ]; then
        return 1
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$TOOLS_CACHE_PATH" <<'PY' 2>/dev/null
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

python_path = str((payload or {}).get("python_path") or "").strip()
if python_path:
    print(python_path)
    raise SystemExit(0)
raise SystemExit(1)
PY
        return $?
    fi
    grep -E '"python_path"[[:space:]]*:[[:space:]]*"' "$TOOLS_CACHE_PATH" 2>/dev/null | head -n 1 | sed -E 's/.*"python_path"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/'
}

write_cached_python_path() {
    local resolved_python="$1"
    local escaped_python
    escaped_python="$(printf '%s' "$resolved_python" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    mkdir -p "$(dirname "$TOOLS_CACHE_PATH")"
    cat >"$TOOLS_CACHE_PATH" <<EOF
{
  "python_path": "$escaped_python",
  "tools_schema": 1
}
EOF
}

normalize_executable_path() {
    local value="$1"
    if [ -z "$value" ]; then
        return 1
    fi
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -u "$value" 2>/dev/null || printf '%s\n' "$value"
        return 0
    fi
    case "$value" in
        [A-Za-z]:\\*)
            printf '%s\n' "$value" | sed -E 's#\\#/#g; s#^([A-Za-z]):#/\\L\1#'
            return 0
            ;;
    esac
    printf '%s\n' "$value"
}

resolve_python_command_path() {
    local candidate="$1"
    if [ -z "$candidate" ]; then
        return 1
    fi
    "$candidate" -c "import sys; print(sys.executable)" 2>/dev/null | tr -d '\r' | tail -n 1 | while IFS= read -r line; do
        normalize_executable_path "$line"
    done
}

find_system_python() {
    local cached candidate resolved

    if [ -n "${PYTHON:-}" ]; then
        resolved="$(resolve_python_command_path "$PYTHON" || true)"
        if [ -n "$resolved" ]; then
            printf '%s\n' "$resolved"
            return 0
        fi
    fi

    cached="$(read_cached_python_path || true)"
    if [ -n "$cached" ]; then
        cached="$(normalize_executable_path "$cached")"
        resolved="$(resolve_python_command_path "$cached" || true)"
        if [ -n "$resolved" ]; then
            printf '%s\n' "$resolved"
            return 0
        fi
    fi

    for candidate in python3 python python.exe py; do
        if ! command -v "$candidate" >/dev/null 2>&1; then
            continue
        fi
        if [ "$candidate" = "py" ]; then
            resolved="$(py -3 -c "import sys; print(sys.executable)" 2>/dev/null | tr -d '\r' | tail -n 1)"
        else
            resolved="$(resolve_python_command_path "$candidate" || true)"
        fi
        if [ -n "$resolved" ]; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done

    if command -v where.exe >/dev/null 2>&1; then
        while IFS= read -r candidate; do
            resolved="$(resolve_python_command_path "$candidate" || true)"
            if [ -n "$resolved" ]; then
                printf '%s\n' "$resolved"
                return 0
            fi
        done < <(where.exe python 2>/dev/null | tr -d '\r')
    fi

    return 1
}

venv_python_path() {
    if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
        normalize_executable_path "$VENV_DIR/Scripts/python.exe"
        return 0
    fi
    normalize_executable_path "$VENV_DIR/bin/python"
}

venv_python_is_healthy() {
    local interpreter="$1"
    [ -x "$interpreter" ] || return 1
    "$interpreter" -c "import sys; print(sys.version)" >/dev/null 2>&1
}

ensure_virtualenv() {
    local system_python="$1"
    local interpreter

    interpreter="$(venv_python_path)"
    if [ -d "$VENV_DIR" ] && ! venv_python_is_healthy "$interpreter"; then
        liwiro_ui_warn "Existing virtual environment is invalid. Rebuilding with $system_python."
        rm -rf "$VENV_DIR"
    fi

    if [ ! -d "$VENV_DIR" ]; then
        liwiro_ui_step "Creating Python environment..."
        "$system_python" -m venv "$VENV_DIR"
    fi

    interpreter="$(venv_python_path)"
    if ! venv_python_is_healthy "$interpreter"; then
        liwiro_ui_error "Could not prepare a working virtual environment at $interpreter"
        exit 1
    fi
    printf '%s\n' "$interpreter"
}

cd "$BACKEND_ROOT"

SYSTEM_PYTHON="$(find_system_python || true)"
if [ -z "$SYSTEM_PYTHON" ]; then
    liwiro_ui_error "Unable to locate a working Python interpreter on this system."
    liwiro_ui_info "Install Python 3.11+ or set PYTHON to an absolute interpreter path, then re-run."
    exit 1
fi
write_cached_python_path "$SYSTEM_PYTHON"
export PYTHON="$SYSTEM_PYTHON"
VENV_PYTHON="$(ensure_virtualenv "$SYSTEM_PYTHON")"

# Install requirements only when the environment is new or requirements changed.
if [ ! -f "$REQUIREMENTS_STAMP" ] || [ "$REQUIREMENTS_FILE" -nt "$REQUIREMENTS_STAMP" ]; then
    liwiro_ui_step "Syncing Python dependencies..."
    "$VENV_PYTHON" -m pip install --disable-pip-version-check -q -r "$REQUIREMENTS_FILE"
    touch "$REQUIREMENTS_STAMP"
fi

# Set environment variables
export FLASK_APP=app.main:create_app
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$BACKEND_ROOT"
# Bind locally by default; deployments that need external ingress must opt in
# with FLASK_HOST=0.0.0.0 (typically behind a reverse proxy).
export FLASK_HOST=${FLASK_HOST:-127.0.0.1}
export FLASK_PORT=${FLASK_PORT:-5000}
if [ "$RUNTIME_HELPERS_AVAILABLE" = "1" ] && is_enabled "${LIWIRO_AUTO_PORTS:-1}" && liwiro_is_port_open "$FLASK_PORT"; then
    NEXT_FLASK_PORT="$(liwiro_find_next_free_port "$FLASK_PORT")"
    if [ "$NEXT_FLASK_PORT" != "$FLASK_PORT" ]; then
        liwiro_ui_warn "Backend port $FLASK_PORT is already in use. Switching to $NEXT_FLASK_PORT."
        export FLASK_PORT="$NEXT_FLASK_PORT"
    fi
fi
export LIWIRO_BACKEND_PORT="$FLASK_PORT"
export LIWIRO_BACKEND_URL="http://127.0.0.1:$FLASK_PORT"
export FLASK_ENV=${FLASK_ENV:-production}
export LIWIRO_VDB_AUTH_CONFIG="${LIWIRO_VDB_AUTH_CONFIG:-${LIWIRO_AUTH_PATH:-$BACKEND_ROOT/.runtime/liwiro.vdb.auth.json}}"
export LIWIRO_AUTH_PATH="${LIWIRO_AUTH_PATH:-$LIWIRO_VDB_AUTH_CONFIG}"
export FLASK_DEBUG=${FLASK_DEBUG:-0}

if ! is_enabled "${LIWIRO_MANAGED_STARTUP:-0}"; then
    liwiro_ui_section "Liwiro Backend"
    liwiro_ui_kv "Python" "$VENV_PYTHON"
    liwiro_ui_kv "Host" "$FLASK_HOST"
    liwiro_ui_kv "Port" "$FLASK_PORT"
    liwiro_ui_kv "Env" "$FLASK_ENV"
    liwiro_ui_kv "Reload" "$(is_enabled "${LIWIRO_BACKEND_RELOAD:-0}" && echo on || echo off)"
    liwiro_ui_newline
fi

if is_enabled "${LIWIRO_PRODUCTION_SERVER:-1}"; then
    exec "$VENV_PYTHON" "$BACKEND_ROOT/scripts/serve_production.py"
fi

FLASK_ARGS=(run --host="$FLASK_HOST" --port="$FLASK_PORT")
if ! is_enabled "${LIWIRO_BACKEND_RELOAD:-0}"; then
    FLASK_ARGS+=(--no-reload)
fi
if is_enabled "${LIWIRO_MANAGED_STARTUP:-0}"; then
    FLASK_ARGS+=(--no-debugger)
fi

exec "$VENV_PYTHON" -m flask "${FLASK_ARGS[@]}"
