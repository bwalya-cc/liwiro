#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
USER_FILE="$VERUN_ROOT/vdb/__data__/sys/users/users.bson"
STORE_HELPER="$SCRIPT_DIR/bson_store.py"
DEFAULT_USER="${VDB_USER:-}"
DEFAULT_EMAIL="${VDB_EMAIL:-z@zulan.io}"
DEFAULT_PASS="${VDB_PASS:-}"

# shellcheck disable=SC1090
. "$VERUN_ROOT/vi/scripts/lib/demo_credentials.sh"

[ -n "$DEFAULT_USER" ] || DEFAULT_USER="$(verun_demo_vdb_user)"
[ -n "$DEFAULT_PASS" ] || DEFAULT_PASS="$(verun_demo_vdb_pass)"

if [ -f "$USER_FILE" ] && python3 "$STORE_HELPER" has-user "$USER_FILE" "$DEFAULT_USER"; then
  echo "VDB demo user '$DEFAULT_USER' already configured."
  exit 0
fi

if [ -f "$USER_FILE" ] && python3 "$STORE_HELPER" has-any-users "$USER_FILE"; then
  echo "Existing VDB users detected, but '$DEFAULT_USER' is missing."
  echo "Skipping bootstrap. Use VDB_USER/VDB_PASS to target an existing account."
  exit 0
fi

echo "Bootstrapping initial VDB super admin '$DEFAULT_USER' via console..."
printf "%s\n%s\n%s\n" "$DEFAULT_USER" "$DEFAULT_EMAIL" "$DEFAULT_PASS" | "$SCRIPT_DIR/convo.sh" >/dev/null 2>&1 || true

if [ -f "$USER_FILE" ] && python3 "$STORE_HELPER" has-user "$USER_FILE" "$DEFAULT_USER"; then
  echo "VDB demo user '$DEFAULT_USER' created."
  exit 0
fi

echo "Failed to create VDB demo user '$DEFAULT_USER'."
exit 1
