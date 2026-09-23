#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEMO_DIR="$PROJECT_ROOT/vi/demo"
JAR="$PROJECT_ROOT/vi/target/vi-1.0.0-jar-with-dependencies.jar"
VDB_STORE_HELPER="$PROJECT_ROOT/vdb/scripts/bson_store.py"
export VI_CUSTOM_MODULES_DIR="${VI_CUSTOM_MODULES_DIR:-$PROJECT_ROOT/vi/custom_modules}"

# shellcheck disable=SC1090
. "$SCRIPT_DIR/lib/demo_credentials.sh"

missing_external_config=()
if [ "$(verun_demo_email_configured)" != "true" ]; then
  missing_external_config+=("SMTP: VERUN_DEMO_EMAIL_SMTP_USERNAME, VERUN_DEMO_EMAIL_SMTP_PASSWORD, VERUN_DEMO_EMAIL_FROM, VERUN_DEMO_EMAIL_TO")
fi
if [ "$(verun_demo_cloudinary_configured)" != "true" ]; then
  missing_external_config+=("Cloudinary: VERUN_DEMO_CLOUDINARY_ENABLED=true plus VERUN_DEMO_CLOUDINARY_CLOUD_NAME, VERUN_DEMO_CLOUDINARY_API_KEY, VERUN_DEMO_CLOUDINARY_API_SECRET")
fi
if [ "${#missing_external_config[@]}" -gt 0 ]; then
  if [ "${VI_DEMO_ALLOW_MISSING_EXTERNAL:-0}" != "1" ]; then
    echo "External demo preflight failed. Configure these values in $(verun_demo_env_file):" >&2
    printf ' - %s\n' "${missing_external_config[@]}" >&2
    echo "For an explicitly local-only run, set VI_DEMO_ALLOW_MISSING_EXTERNAL=1." >&2
    exit 2
  fi
  echo "NOTICE: local-only mode enabled; unconfigured SMTP/Cloudinary demos will report skips."
fi

demo_runtime_dir="$(mktemp -d /tmp/verun_vi_demos_XXXXXX)"
demo_work_dir="$demo_runtime_dir/work"
export VERUN_VDB_ROOT="$demo_runtime_dir/vdb"
VDB_USER_FILE="$VERUN_VDB_ROOT/__data__/sys/users/users.bson"
mkdir -p "$demo_work_dir"
ln -s "$DEMO_DIR" "$demo_work_dir/demo"

cleanup_demo_runtime() {
  rm -f "${tmp_credentials_probe:-}"
  rm -f "${tmp_file:-}"
  rm -rf "$demo_runtime_dir"
}
trap cleanup_demo_runtime EXIT INT TERM

if [ "$(verun_demo_vdb_configured)" != "true" ]; then
  demo_suffix="${PPID}_${RANDOM}"
  export VERUN_DEMO_VDB_USER="vi_demo_$demo_suffix"
  export VERUN_DEMO_VDB_PASS="ViDemo-${demo_suffix}-Aa1!"
  export VERUN_DEMO_VDB_DOMAIN="vi_demos_$demo_suffix"
  export VERUN_DEMO_VDB_DB="main"
  echo "Using isolated auto-provisioned VDB demo account."
else
  echo "Using configured credentials in an isolated VDB demo store."
fi

demo_vdb_user="$(verun_demo_vdb_user)"
demo_vdb_pass="$(verun_demo_vdb_pass)"
demo_vdb_domain="$(verun_demo_vdb_domain)"
demo_hash="$(DEMO_PASSWORD="$demo_vdb_pass" python3 -c 'import bcrypt, os; print(bcrypt.hashpw(os.environ["DEMO_PASSWORD"].encode(), bcrypt.gensalt()).decode().replace("$2b$", "$2a$", 1))')"
mkdir -p "$(dirname "$VDB_USER_FILE")"
python3 "$VDB_STORE_HELPER" upsert-user "$VDB_USER_FILE" \
  "$demo_vdb_user" "${demo_vdb_user}@local.test" APPLICATION "$demo_hash" \
  "$demo_vdb_domain"

if [ ! -f "$JAR" ]; then
  "$PROJECT_ROOT/scripts/compile_all.sh"
fi

cd "$demo_work_dir" || exit 1

echo "RUNNING VI DEMOS IN $DEMO_DIR"
echo ""

tmp_credentials_probe="$(mktemp /tmp/vi_demo_creds_XXXXXX.versa)"
verun_write_demo_credentials_prelude "$tmp_credentials_probe"

if grep -q 'CHANGE_ME_VDB' "$tmp_credentials_probe"; then
  echo "NOTICE: demo VDB credentials are still using CHANGE_ME values."
  echo "Set VERUN_DEMO_VDB_* in $(verun_demo_env_file)."
  echo ""
fi

if grep -q 'CHANGE_ME_EMAIL' "$tmp_credentials_probe"; then
  echo "NOTICE: demo email settings are still using CHANGE_ME values."
  echo "Set VERUN_DEMO_EMAIL_* in $(verun_demo_env_file)."
  echo ""
fi

fail_count=0
VI_RUN_FLAGS=()
if [ "${VI_DEMO_VERBOSE_LOGS:-0}" = "1" ]; then
  VI_RUN_FLAGS=(--msg-only --log --all)
fi

expected_exit_code_for_file() {
  local source_file="$1"
  local marker
  marker="$(sed -n '1,12p' "$source_file" | sed -n 's/^[[:space:]]*#\s*demo_expected_exit_code:\s*\([0-9][0-9]*\)\s*$/\1/p' | head -n 1)"
  if [ -n "$marker" ]; then
    printf '%s\n' "$marker"
  fi
}

demo_role_for_file() {
  local source_file="$1"
  local marker
  marker="$(sed -n '1,12p' "$source_file" | sed -n 's/^[[:space:]]*#\s*demo_role:\s*\([a-z_][a-z_]*\)\s*$/\1/p' | head -n 1)"
  if [ -n "$marker" ]; then
    printf '%s\n' "$marker"
  fi
}

while read -r file; do
  [ -z "${file:-}" ] && continue
  [ -f "$file" ] || continue

  name="$(basename "$file")"
  rel_path="${file#$DEMO_DIR/}"
  [[ "$rel_path" == mediacloud/lib/* ]] && continue
  [[ "$rel_path" == import_helpers/* ]] && continue
  [[ "$name" == .vi_demo_* ]] && continue
  [[ "$name" == _tmp_* ]] && continue

  demo_role="$(demo_role_for_file "$file")"
  [ "$demo_role" = "support" ] && continue
  [ "$demo_role" = "generated" ] && continue

  echo "--------------------------------------------------"
  echo "Running file: $file"
  echo "--------------------------------------------------"

  tmp_file=""
  run_target="$file"

  if [[ "$rel_path" == vdb/* || "$rel_path" == vdb_exceptions/* || "$rel_path" == email/* || "$rel_path" == mediacloud/* || "$name" == vdb_* || "$name" == email_* ]]; then
    tmp_file="$(mktemp /tmp/vi_demo_run_XXXXXX.versa)"
    verun_compose_with_prelude "$tmp_credentials_probe" "$file" "$tmp_file"
    run_target="$tmp_file"
  fi

  expected_exit_code="$(expected_exit_code_for_file "$file")"

  set +e
  if [ -f "$file" ] && grep -q "input(" "$file"; then
    echo "Jelita" | java -jar "$JAR" "$run_target" "${VI_RUN_FLAGS[@]}"
  else
    java -jar "$JAR" "$run_target" "${VI_RUN_FLAGS[@]}" < /dev/null
  fi
  status=$?
  set -e

  if [ -n "${expected_exit_code:-}" ]; then
    if [ "$status" -ne "$expected_exit_code" ]; then
      echo "FAILED: $file"
      fail_count=$((fail_count + 1))
    else
      echo "Expected exit code observed: $status"
    fi
  elif [ "$status" -ne 0 ]; then
    echo "FAILED: $file"
    fail_count=$((fail_count + 1))
  fi

  if [ -n "$tmp_file" ] && [ -f "$tmp_file" ]; then
    rm -f "$tmp_file"
  fi

  echo ""
  echo ""
done < <(find "$DEMO_DIR" -type f -name "*.versa" ! -name ".vi_demo_*.versa" | sort)

rm -f "$tmp_credentials_probe"
tmp_credentials_probe=""

if [ "$fail_count" -gt 0 ]; then
  echo "Completed with $fail_count failing demo(s)."
  exit 1
fi

echo "Completed with 0 failing demos."
