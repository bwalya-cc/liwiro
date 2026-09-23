#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
VDB_ROOT="${VERUN_VDB_ROOT:-$VERUN_ROOT/vdb}"
ACCEPTANCE_FILE="$VDB_ROOT/__data__/sys/mit-license-acceptance.bson"
STORE_HELPER="$SCRIPT_DIR/bson_store.py"
CHANNEL="${1:-shell}"

if [ -s "$ACCEPTANCE_FILE" ]; then
  exit 0
fi

if [ ! -t 0 ]; then
  echo "MIT license not accepted. Run a VDB startup command in a terminal and answer y/Y first." >&2
  exit 1
fi

echo "Verun + Liwiro is distributed under the MIT License."
printf "Accept MIT license? [y/N]: "
IFS= read -r ANSWER || ANSWER=""

case "$ANSWER" in
  y|Y)
    mkdir -p "$(dirname "$ACCEPTANCE_FILE")"
    ACCEPTED_BY="${USER:-unknown}"
    ACCEPTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 "$STORE_HELPER" record-mit-acceptance "$ACCEPTANCE_FILE" "$CHANNEL" "$ACCEPTED_BY" "$ACCEPTED_AT"
    ;;
  *)
    echo "MIT license not accepted. Exiting." >&2
    exit 1
    ;;
esac
