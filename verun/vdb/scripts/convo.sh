#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
VDB_JAR="$VERUN_ROOT/vdb/target/vdb-1.0.0-jar-with-dependencies.jar"

if [ ! -f "$VDB_JAR" ]; then
  echo "VDB jar not found. Building project..."
  "$VERUN_ROOT/scripts/compile_all.sh"
fi

trap 'echo "Exiting..."; exit 1' INT TERM
exec java -jar "$VDB_JAR" "$@"
