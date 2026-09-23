#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

if [ $# -lt 1 ]; then
  echo "Usage: $0 <query_name>"
  exit 1
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
QUERY_NAME="$1"
VDB_JAR="$VERUN_ROOT/vdb/target/vdb-1.0.0-jar-with-dependencies.jar"
QUERY_FILE="$VERUN_ROOT/vdb/src/main/resources/queries/${QUERY_NAME}_queries.vql"
VDB_USER="${VDB_USER:-}"
VDB_PASS="${VDB_PASS:-}"

# shellcheck disable=SC1090
. "$VERUN_ROOT/vi/scripts/lib/demo_credentials.sh"
[ -n "$VDB_USER" ] || VDB_USER="$(verun_demo_vdb_user)"
[ -n "$VDB_PASS" ] || VDB_PASS="$(verun_demo_vdb_pass)"

if [ ! -f "$QUERY_FILE" ]; then
  QUERY_FILE="$VERUN_ROOT/vdb/target/classes/queries/${QUERY_NAME}_queries.vql"
fi

if [ ! -f "$QUERY_FILE" ]; then
  echo "Query file not found for '$QUERY_NAME'"
  exit 1
fi

if [ ! -f "$VDB_JAR" ]; then
  echo "VDB jar not found. Building project..."
  "$VERUN_ROOT/scripts/compile_all.sh"
fi

# Ensure the demo user exists for non-interactive query runs.
if ! "$VERUN_ROOT/vdb/scripts/setup_demo_admin.sh" >/dev/null 2>&1; then
  echo "Failed to bootstrap demo user. Set VDB_USER/VDB_PASS for an existing account and retry."
  exit 1
fi

echo "Running ${QUERY_NAME} operations test..."
exec java -jar "$VDB_JAR" "$VDB_USER" "$VDB_PASS" < "$QUERY_FILE"
