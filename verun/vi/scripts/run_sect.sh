#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_FILE_SCRIPT="$SCRIPT_DIR/run_file.sh"

if [ ! -x "$RUN_FILE_SCRIPT" ]; then
  echo "Missing or non-executable runner: $RUN_FILE_SCRIPT"
  exit 1
fi

# Curated core demo slice
FILES=(
    "core/builtins.versa"
    "core/closures.versa"
    "core/comprehensions.versa"
    "core/conditionals.versa"
    "core/exceptions.versa"
    "core/fact.versa"
    "core/fib_with_for_loop.versa"
    "core/fib_with_while_loop.versa"
    "core/for_in_demo.versa"
    "core/for_with_index_demo.versa"
    "core/function.versa"
    "core/lambda.versa"
    "core/leng.versa"
    "core/list_and_join_demo.versa"
    "core/list_indexing.versa"
    "core/print.versa"
    "core/range_demo.versa"
)

# Loop through the files and run each one
for FILE in "${FILES[@]}"; do
    if ! "$RUN_FILE_SCRIPT" "$FILE"; then
        echo "FAILED: $FILE"
        exit 1
    fi
    echo ""
    echo ""
done
