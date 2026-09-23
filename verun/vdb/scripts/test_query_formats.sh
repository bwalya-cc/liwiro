#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
VDB_JAR="$VERUN_ROOT/vdb/target/vdb-1.0.0-jar-with-dependencies.jar"
QUERY_FILE="$VERUN_ROOT/vdb/src/main/resources/test_query_formats.vql"

if [ ! -f "$VDB_JAR" ]; then
  "$VERUN_ROOT/scripts/compile_all.sh"
fi

echo "Running query format tests..."
VDB_USER="${VDB_USERNAME:-liwiro}"
VDB_PASS="${VDB_PASSWORD:-ChangeMeVdbAppPass0!}"
echo "Authenticating as '$VDB_USER' (override with VDB_USERNAME/VDB_PASSWORD)."
exec java -jar "$VDB_JAR" "$VDB_USER" "$VDB_PASS" < "$QUERY_FILE"
