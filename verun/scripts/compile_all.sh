#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERUN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$VERUN_ROOT"

echo "Compiling Verun modules (vdb + vi runtime module)..."
mvn clean package -pl vdb,vi -am

echo ""
echo "Build complete."
echo "VDB jar: $VERUN_ROOT/vdb/target/vdb-1.0.0-jar-with-dependencies.jar"
echo "VI jar: $VERUN_ROOT/vi/target/vi-1.0.0-jar-with-dependencies.jar"
