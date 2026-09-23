#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERUN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$VERUN_ROOT"

rm -rf __data__/
rm -rf vdb/__data__/

./scripts/compile_all.sh
./vdb/scripts/run_query.sh define
./vdb/scripts/run_query.sh create
./vdb/scripts/run_query.sh list
./vdb/scripts/run_query.sh read
