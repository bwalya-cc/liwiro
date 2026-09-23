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

exec "$RUN_FILE_SCRIPT" core/comprehensions.versa
