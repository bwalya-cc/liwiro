#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# shellcheck disable=SC1090
. "$SCRIPT_DIR/lib/runtime_common.sh"

liwiro_load_env_stack
HOST_PLATFORM="$(liwiro_detect_host_platform)"
PLATFORM_SCRIPT="$(liwiro_platform_script_path "start.sh" "$HOST_PLATFORM")"

if [ ! -f "$PLATFORM_SCRIPT" ]; then
  liwiro_ui_error "No platform launcher script found at $PLATFORM_SCRIPT"
  exit 1
fi

exec bash "$PLATFORM_SCRIPT" "$@"
