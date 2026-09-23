#!/usr/bin/env sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/liwiro/cli/liwiro.py" "$@"
