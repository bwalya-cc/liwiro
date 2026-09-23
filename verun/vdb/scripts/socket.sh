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

sh "$SCRIPT_DIR/ensure_mit_acceptance.sh" "unix-socket"

VDB_SOCKET_PATH="${VDB_UNIX_SOCKET_PATH:-${VDB_INTERFACE_UNIXSOCKET_PATH:-}}"

if [ -n "${VDB_SOCKET_PATH:-}" ]; then
  exec java \
    -Dvdb.interface.unixsocket.enabled=true \
    -Dvdb.interface.unixsocket.path="$VDB_SOCKET_PATH" \
    -cp "$VDB_JAR" \
    verun.vdb.VDBUnixSocket \
    "$@"
fi

exec java \
  -Dvdb.interface.unixsocket.enabled=true \
  -cp "$VDB_JAR" \
  verun.vdb.VDBUnixSocket \
  "$@"
