#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$SCRIPT_DIR/run_demo_files.sh"

if [ ! -x "$RUNNER" ]; then
  echo "Missing executable runner: $RUNNER"
  exit 1
fi

TMP_OUT="$(mktemp /tmp/vi_demo_health_XXXXXX.log)"
trap 'rm -f "$TMP_OUT"' EXIT
had_email_warning=0

echo "Running all VI demos for health check..."
if ! "$RUNNER" | tee "$TMP_OUT"; then
  echo ""
  echo "Health check failed: run_demo_files.sh reported execution failures."
  exit 1
fi

ok_false_hits="$(rg -n '(^|[[:space:]])ok=false([[:space:]]|$)' "$TMP_OUT" || true)"
if [ -n "$ok_false_hits" ]; then
  non_email_failures="$(rg -n '(^|[[:space:]])ok=false([[:space:]]|$)' "$TMP_OUT" | rg -v 'op=send_email' || true)"
  email_failures="$(rg -n '(^|[[:space:]])ok=false([[:space:]]|$).*op=send_email' "$TMP_OUT" || true)"

  if [ -n "$non_email_failures" ]; then
    echo ""
    echo "Health check failed: detected non-email operation failures (ok=false)."
    echo "$non_email_failures"
    echo ""
    echo "Tip: inspect the corresponding demo output above to identify the failing module/flow."
    exit 1
  fi

  if [ -n "$email_failures" ]; then
    if [ "${VI_DEMO_STRICT_EMAIL:-0}" = "1" ]; then
      echo ""
      echo "Health check failed: email demo failures detected in strict mode."
      echo "$email_failures"
      exit 1
    fi
    echo ""
    echo "Warning: email demo failures detected (external SMTP/network may be unavailable)."
    echo "$email_failures"
    echo "Set VI_DEMO_STRICT_EMAIL=1 to fail on email demo send errors."
    had_email_warning=1
  fi
fi

echo ""
if [ "$had_email_warning" = "1" ]; then
  echo "Demo health check passed with warnings (email-only send failures)."
else
  echo "Demo health check passed: no runner failures and no ok=false responses detected."
fi
