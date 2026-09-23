#!/bin/sh
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VERUN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
QUERY_FILE="$VERUN_ROOT/vdb/src/main/resources/test_query_formats.vql"

curl -X POST http://localhost:1957/vdb -H 'Content-Type: text/versa' --data-binary @"$QUERY_FILE"
