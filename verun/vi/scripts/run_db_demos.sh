#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
JAR="$PROJECT_ROOT/vi/target/vi-1.0.0-jar-with-dependencies.jar"
DEMO_DIR="$PROJECT_ROOT/vi/demo"

# shellcheck disable=SC1090
. "$SCRIPT_DIR/lib/demo_credentials.sh"

if [ ! -f "$JAR" ]; then
  "$PROJECT_ROOT/scripts/compile_all.sh"
fi

demo_role_for_file() {
  local source_file="$1"
  local marker
  marker="$(sed -n '1,12p' "$source_file" | sed -n 's/^[[:space:]]*#\s*demo_role:\s*\([a-z_][a-z_]*\)\s*$/\1/p' | head -n 1)"
  if [ -n "$marker" ]; then
    printf '%s\n' "$marker"
  fi
}

for file in "$DEMO_DIR"/vdb/vdb_*.versa; do
  [ -f "$file" ] || continue
  demo_role="$(demo_role_for_file "$file")"
  [ "$demo_role" = "support" ] && continue
  [ "$demo_role" = "generated" ] && continue
  echo ""
  echo "Running VDB demo file: $file"
  tmp_file="$(mktemp /tmp/vdb_demo_XXXXXX.versa)"
  tmp_creds_file="$(mktemp /tmp/vdb_creds_XXXXXX.versa)"
  verun_write_demo_credentials_prelude "$tmp_creds_file"
  verun_compose_with_prelude "$tmp_creds_file" "$file" "$tmp_file"
  java -jar "$JAR" "$tmp_file" --log
  rm -f "$tmp_file"
  rm -f "$tmp_creds_file"
done
