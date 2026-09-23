#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <file.versa | file_basename>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEMO_DIR="$PROJECT_ROOT/vi/demo"
JAR="$PROJECT_ROOT/vi/target/vi-1.0.0-jar-with-dependencies.jar"
INPUT="$1"
RUNTIME_CWD="$PROJECT_ROOT/vi"
export VI_CUSTOM_MODULES_DIR="${VI_CUSTOM_MODULES_DIR:-$PROJECT_ROOT/vi/custom_modules}"

# shellcheck disable=SC1090
. "$SCRIPT_DIR/lib/demo_credentials.sh"

run_vi_java() {
  (
    cd "$RUNTIME_CWD"
    java -jar "$JAR" "$@"
  )
}

if [ ! -f "$JAR" ]; then
  "$PROJECT_ROOT/scripts/compile_all.sh"
fi

if [ -f "$INPUT" ]; then
  TARGET_FILE="$INPUT"
elif [ -f "$DEMO_DIR/$INPUT" ]; then
  TARGET_FILE="$DEMO_DIR/$INPUT"
elif [ -f "$DEMO_DIR/${INPUT}.versa" ]; then
  TARGET_FILE="$DEMO_DIR/${INPUT}.versa"
else
  MATCHES="$(find "$DEMO_DIR" -type f \( -name "$INPUT" -o -name "${INPUT}.versa" \) | sort)"
  if [ -n "$MATCHES" ]; then
    TARGET_FILE="$(echo "$MATCHES" | head -n 1)"
  else
    echo "File not found: $INPUT"
    exit 1
  fi
fi

echo "--------------------------------------------------"
echo "Running file: $TARGET_FILE"
echo "--------------------------------------------------"

REL_PATH="${TARGET_FILE#$DEMO_DIR/}"

if [[ "$REL_PATH" == vdb/* || "$REL_PATH" == vdb_exceptions/* || "$REL_PATH" == email/* || "$REL_PATH" == mediacloud/* || "$(basename "$TARGET_FILE")" == vdb_* || "$(basename "$TARGET_FILE")" == email_* ]]; then
  TMP_FILE="$(mktemp /tmp/vi_single_XXXXXX.versa)"
  TMP_CREDS_FILE="$(mktemp /tmp/vi_demo_XXXXXX.versa)"
  verun_write_demo_credentials_prelude "$TMP_CREDS_FILE"
  verun_compose_with_prelude "$TMP_CREDS_FILE" "$TARGET_FILE" "$TMP_FILE"
  run_vi_java "$TMP_FILE" --msg-only --log --all
  rm -f "$TMP_FILE"
  rm -f "$TMP_CREDS_FILE"
else
  run_vi_java "$TARGET_FILE" --msg-only --log --all
fi
