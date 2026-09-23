#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
VDB_JAR="$VERUN_ROOT/vdb/target/vdb-1.0.0-jar-with-dependencies.jar"
export VI_CUSTOM_MODULES_DIR="${VI_CUSTOM_MODULES_DIR:-$VERUN_ROOT/vi/custom_modules}"

if [ ! -f "$VDB_JAR" ]; then
  echo "VDB jar not found. Building project..."
  bash "$VERUN_ROOT/scripts/compile_all.sh"
fi

has_namedpipe_class() {
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$VDB_JAR" <<'PY'
import sys
import zipfile
from pathlib import Path

jar_path = Path(sys.argv[1])
required = "verun/vdb/VDBNamedPipe.class"
try:
    with zipfile.ZipFile(jar_path, "r") as archive:
        raise SystemExit(0 if required in archive.namelist() else 1)
except Exception:
    raise SystemExit(1)
PY
}

if ! has_namedpipe_class; then
  echo "Direct VDB named-pipe runtime is missing from the current build."
  echo "Rebuilding Verun VDB to include verun.vdb.VDBNamedPipe..."
  bash "$VERUN_ROOT/scripts/compile_all.sh"
fi

if ! has_namedpipe_class; then
  if command -v python3 >/dev/null 2>&1; then
    echo "Direct VDB named-pipe runtime is still missing from the rebuilt output."
    echo "Rebuild Verun VDB so $VDB_JAR includes verun.vdb.VDBNamedPipe."
    exit 1
  fi
fi

sh "$SCRIPT_DIR/ensure_mit_acceptance.sh" "named-pipe"

VDB_PIPE_PATH="${VDB_NAMED_PIPE_PATH:-${VDB_INTERFACE_NAMEDPIPE_PATH:-}}"

if [ -n "${VDB_PIPE_PATH:-}" ]; then
  exec java \
    -Dvdb.interface.namedpipe.enabled=true \
    -Dvdb.interface.namedpipe.path="$VDB_PIPE_PATH" \
    -cp "$VDB_JAR" \
    verun.vdb.VDBNamedPipe \
    "$@"
fi

exec java \
  -Dvdb.interface.namedpipe.enabled=true \
  -cp "$VDB_JAR" \
  verun.vdb.VDBNamedPipe \
  "$@"
