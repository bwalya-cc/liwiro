#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
JAR="$PROJECT_ROOT/vi/target/vi-1.0.0-jar-with-dependencies.jar"
export VI_CUSTOM_MODULES_DIR="${VI_CUSTOM_MODULES_DIR:-$PROJECT_ROOT/vi/custom_modules}"

if [ ! -f "$JAR" ]; then
  "$PROJECT_ROOT/scripts/compile_all.sh"
fi

exec java -jar "$JAR"
