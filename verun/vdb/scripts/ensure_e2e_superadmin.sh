#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
VDB_ROOT="${VERUN_VDB_ROOT:-$VERUN_ROOT/vdb}"
USER_FILE="$VDB_ROOT/__data__/sys/users/users.bson"
STORE_HELPER="$SCRIPT_DIR/bson_store.py"
E2E_USER="${VDB_E2E_USER:-ver}"
E2E_EMAIL="${VDB_E2E_EMAIL:-ver@local.dev}"
E2E_HASH="${VDB_E2E_PASS_HASH:-}"

if [ -z "$E2E_HASH" ]; then
  echo "Set VDB_E2E_PASS_HASH to a bcrypt hash for your local E2E VDB password before running this helper." >&2
  exit 1
fi

mkdir -p "$(dirname "$USER_FILE")"
python3 "$STORE_HELPER" upsert-user "$USER_FILE" "$E2E_USER" "$E2E_EMAIL" "APPLICATION" "$E2E_HASH" default liwiro
echo "Ensured VDB E2E user '$E2E_USER' with application role + owned domains."
