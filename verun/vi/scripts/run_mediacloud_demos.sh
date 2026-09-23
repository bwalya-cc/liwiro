#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEMO_DIR="$PROJECT_ROOT/vi/demo/mediacloud"
RUN_FILE_SCRIPT="$SCRIPT_DIR/run_file.sh"

if [ ! -x "$RUN_FILE_SCRIPT" ]; then
  echo "Missing or non-executable runner: $RUN_FILE_SCRIPT"
  exit 1
fi

echo "RUNNING MEDIACLOUD DEMOS IN $DEMO_DIR"
echo ""

fail_count=0
pass_count=0

demo_role_for_file() {
  local source_file="$1"
  local marker
  marker="$(sed -n '1,12p' "$source_file" | sed -n 's/^[[:space:]]*#\s*demo_role:\s*\([a-z_][a-z_]*\)\s*$/\1/p' | head -n 1)"
  if [ -n "$marker" ]; then
    printf '%s\n' "$marker"
  fi
}

while read -r file; do
  [ -z "${file:-}" ] && continue
  [ -f "$file" ] || continue

  name="$(basename "$file")"
  demo_role="$(demo_role_for_file "$file")"
  [ "$demo_role" = "support" ] && continue
  [ "$demo_role" = "generated" ] && continue

  if ! "$RUN_FILE_SCRIPT" "$file"; then
    echo "FAILED: $file"
    fail_count=$((fail_count + 1))
  else
    echo "PASSED: $file"
    pass_count=$((pass_count + 1))
  fi

  echo ""
  echo ""
done < <(find "$DEMO_DIR" -maxdepth 1 -type f -name "*.versa" | sort)

if [ "$fail_count" -gt 0 ]; then
  echo "Completed with $pass_count passing and $fail_count failing MediaCloud demo(s)."
  exit 1
fi

echo "Completed with $pass_count passing and 0 failing MediaCloud demos."
