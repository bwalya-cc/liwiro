#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_FILE_SCRIPT="$SCRIPT_DIR/run_file.sh"

if [ ! -x "$RUN_FILE_SCRIPT" ]; then
  echo "Missing or non-executable runner: $RUN_FILE_SCRIPT"
  exit 1
fi

"$RUN_FILE_SCRIPT" core/exceptions.versa
"$RUN_FILE_SCRIPT" core/lambda.versa
