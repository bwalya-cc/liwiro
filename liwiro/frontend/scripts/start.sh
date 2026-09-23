#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIWIRO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

exec bash "$LIWIRO_ROOT/scripts/start_front.sh" "$@"
