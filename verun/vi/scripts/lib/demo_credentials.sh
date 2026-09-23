#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

if [ -n "${VERUN_DEMO_CREDENTIALS_LIB_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
VERUN_DEMO_CREDENTIALS_LIB_LOADED=1

VERUN_VI_SCRIPTS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERUN_VI_SCRIPTS_DIR="$(cd "$VERUN_VI_SCRIPTS_LIB_DIR/.." && pwd)"
VERUN_ROOT="$(cd "$VERUN_VI_SCRIPTS_DIR/../.." && pwd)"
VERUN_VI_DEMO_DIR="$VERUN_ROOT/vi/demo"
VERUN_VI_DEMO_ENV_FILE="$VERUN_VI_DEMO_DIR/.env"

verun_source_env_file() {
  local file_path="$1"
  if [ -f "$file_path" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$file_path"
    set +a
  fi
}

verun_load_demo_env() {
  if [ -n "${VERUN_DEMO_ENV_LOADED:-}" ]; then
    return 0
  fi
  verun_source_env_file "$VERUN_VI_DEMO_ENV_FILE"
  VERUN_DEMO_ENV_LOADED=1
}

verun_demo_env_file() {
  printf '%s\n' "$VERUN_VI_DEMO_ENV_FILE"
}

verun_demo_value() {
  local fallback="$1"
  shift
  verun_load_demo_env
  local key
  for key in "$@"; do
    local value="${!key:-}"
    if [ -n "$value" ]; then
      printf '%s\n' "$value"
      return 0
    fi
  done
  printf '%s\n' "$fallback"
}

verun_demo_normalize_bool() {
  local raw="${1:-}"
  local fallback="${2:-false}"
  case "${raw,,}" in
    1|true|yes|on)
      printf 'true\n'
      ;;
    0|false|no|off)
      printf 'false\n'
      ;;
    *)
      printf '%s\n' "$fallback"
      ;;
  esac
}

verun_demo_int() {
  local raw="$1"
  local fallback="$2"
  if [[ "$raw" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$raw"
  else
    printf '%s\n' "$fallback"
  fi
}

verun_versa_escape() {
  local value="${1:-}"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

verun_demo_has_real_value() {
  local value="${1:-}"
  [ -n "$value" ] && [[ "$value" != CHANGE_ME* ]]
}

verun_demo_vdb_user() {
  verun_demo_value "CHANGE_ME_VDB_USER" VERUN_DEMO_VDB_USER VDB_USERNAME
}

verun_demo_vdb_pass() {
  verun_demo_value "CHANGE_ME_VDB_PASSWORD" VERUN_DEMO_VDB_PASS VDB_PASSWORD
}

verun_demo_vdb_domain() {
  verun_demo_value "vi_demos" VERUN_DEMO_VDB_DOMAIN LIWIRO_DOMAIN
}

verun_demo_vdb_db() {
  verun_demo_value "main" VERUN_DEMO_VDB_DB LIWIRO_DB
}

verun_demo_email_host() {
  verun_demo_value "smtp.gmail.com" VERUN_DEMO_EMAIL_SMTP_HOST
}

verun_demo_email_port() {
  local raw
  raw="$(verun_demo_value "587" VERUN_DEMO_EMAIL_SMTP_PORT)"
  verun_demo_int "$raw" "587"
}

verun_demo_email_starttls() {
  local raw
  raw="$(verun_demo_value "true" VERUN_DEMO_EMAIL_SMTP_STARTTLS)"
  verun_demo_normalize_bool "$raw" "true"
}

verun_demo_email_ssl() {
  local raw
  raw="$(verun_demo_value "false" VERUN_DEMO_EMAIL_SMTP_SSL)"
  verun_demo_normalize_bool "$raw" "false"
}

verun_demo_email_auth() {
  local raw
  raw="$(verun_demo_value "true" VERUN_DEMO_EMAIL_SMTP_AUTH)"
  verun_demo_normalize_bool "$raw" "true"
}

verun_demo_email_username() {
  verun_demo_value "CHANGE_ME_EMAIL_USERNAME" VERUN_DEMO_EMAIL_SMTP_USERNAME
}

verun_demo_email_password() {
  verun_demo_value "CHANGE_ME_EMAIL_PASSWORD" VERUN_DEMO_EMAIL_SMTP_PASSWORD
}

verun_demo_email_from() {
  local username
  username="$(verun_demo_email_username)"
  verun_demo_value "$username" VERUN_DEMO_EMAIL_FROM
}

verun_demo_email_to() {
  local from_address
  from_address="$(verun_demo_email_from)"
  verun_demo_value "$from_address" VERUN_DEMO_EMAIL_TO
}

verun_demo_cloudinary_cloud_name() {
  verun_demo_value "" VERUN_DEMO_CLOUDINARY_CLOUD_NAME
}

verun_demo_cloudinary_api_key() {
  verun_demo_value "" VERUN_DEMO_CLOUDINARY_API_KEY
}

verun_demo_cloudinary_api_secret() {
  verun_demo_value "" VERUN_DEMO_CLOUDINARY_API_SECRET
}

verun_demo_cloudinary_folder() {
  verun_demo_value "liwiro-demo" VERUN_DEMO_CLOUDINARY_FOLDER
}

verun_demo_cloudinary_enabled() {
  verun_load_demo_env
  local raw="${VERUN_DEMO_CLOUDINARY_ENABLED:-}"
  if [ -n "$raw" ]; then
    verun_demo_normalize_bool "$raw" "false"
    return 0
  fi

  local cloud_name api_key api_secret
  cloud_name="$(verun_demo_cloudinary_cloud_name)"
  api_key="$(verun_demo_cloudinary_api_key)"
  api_secret="$(verun_demo_cloudinary_api_secret)"
  if verun_demo_has_real_value "$cloud_name" \
    && verun_demo_has_real_value "$api_key" \
    && verun_demo_has_real_value "$api_secret"; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
}

verun_demo_vdb_configured() {
  local user pass
  user="$(verun_demo_vdb_user)"
  pass="$(verun_demo_vdb_pass)"
  if verun_demo_has_real_value "$user" && verun_demo_has_real_value "$pass"; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
}

verun_demo_email_configured() {
  local host username password from_address to_address
  host="$(verun_demo_email_host)"
  username="$(verun_demo_email_username)"
  password="$(verun_demo_email_password)"
  from_address="$(verun_demo_email_from)"
  to_address="$(verun_demo_email_to)"
  if verun_demo_has_real_value "$host" \
    && verun_demo_has_real_value "$username" \
    && verun_demo_has_real_value "$password" \
    && verun_demo_has_real_value "$from_address" \
    && verun_demo_has_real_value "$to_address"; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
}

verun_demo_cloudinary_configured() {
  local enabled cloud_name api_key api_secret
  enabled="$(verun_demo_cloudinary_enabled)"
  cloud_name="$(verun_demo_cloudinary_cloud_name)"
  api_key="$(verun_demo_cloudinary_api_key)"
  api_secret="$(verun_demo_cloudinary_api_secret)"
  if [ "$enabled" = "true" ] \
    && verun_demo_has_real_value "$cloud_name" \
    && verun_demo_has_real_value "$api_key" \
    && verun_demo_has_real_value "$api_secret"; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
}

verun_write_demo_credentials_prelude() {
  local out_file="$1"
  local vdb_user vdb_pass vdb_domain vdb_db
  local email_host email_port email_starttls email_ssl email_auth email_username email_password email_from email_to
  local cloudinary_cloud_name cloudinary_api_key cloudinary_api_secret cloudinary_folder
  local vdb_configured email_configured cloudinary_configured

  vdb_user="$(verun_demo_vdb_user)"
  vdb_pass="$(verun_demo_vdb_pass)"
  vdb_domain="$(verun_demo_vdb_domain)"
  vdb_db="$(verun_demo_vdb_db)"
  email_host="$(verun_demo_email_host)"
  email_port="$(verun_demo_email_port)"
  email_starttls="$(verun_demo_email_starttls)"
  email_ssl="$(verun_demo_email_ssl)"
  email_auth="$(verun_demo_email_auth)"
  email_username="$(verun_demo_email_username)"
  email_password="$(verun_demo_email_password)"
  email_from="$(verun_demo_email_from)"
  email_to="$(verun_demo_email_to)"
  cloudinary_cloud_name="$(verun_demo_cloudinary_cloud_name)"
  cloudinary_api_key="$(verun_demo_cloudinary_api_key)"
  cloudinary_api_secret="$(verun_demo_cloudinary_api_secret)"
  cloudinary_folder="$(verun_demo_cloudinary_folder)"
  vdb_configured="$(verun_demo_vdb_configured)"
  email_configured="$(verun_demo_email_configured)"
  cloudinary_configured="$(verun_demo_cloudinary_configured)"

  cat >"$out_file" <<EOF
let DEMO_ENV_FILE = "$(verun_versa_escape "$VERUN_VI_DEMO_ENV_FILE")";

let DEMO_VDB_CONFIGURED = $vdb_configured;
let DEMO_VDB_USER = "$(verun_versa_escape "$vdb_user")";
let DEMO_VDB_PASS = "$(verun_versa_escape "$vdb_pass")";
let DEMO_VDB_DOMAIN = "$(verun_versa_escape "$vdb_domain")";
let DEMO_VDB_DB = "$(verun_versa_escape "$vdb_db")";

let DEMO_EMAIL_CONFIGURED = $email_configured;
let EMAIL_SMTP_HOST = "$(verun_versa_escape "$email_host")";
let EMAIL_SMTP_PORT = $email_port;
let EMAIL_SMTP_STARTTLS = $email_starttls;
let EMAIL_SMTP_SSL = $email_ssl;
let EMAIL_SMTP_AUTH = $email_auth;
let EMAIL_SMTP_USERNAME = "$(verun_versa_escape "$email_username")";
let EMAIL_SMTP_PASSWORD = "$(verun_versa_escape "$email_password")";
let EMAIL_FROM = "$(verun_versa_escape "$email_from")";
let EMAIL_TO = "$(verun_versa_escape "$email_to")";

let DEMO_CLOUDINARY_CONFIGURED = $cloudinary_configured;
EOF

  if [ "$cloudinary_configured" = "true" ]; then
    cat >>"$out_file" <<EOF
let cloudinary_media_config = {
  defaultProvider: "cloudinary",
  cloudName: "$(verun_versa_escape "$cloudinary_cloud_name")",
  apiKey: "$(verun_versa_escape "$cloudinary_api_key")",
  apiSecret: "$(verun_versa_escape "$cloudinary_api_secret")",
  folder: "$(verun_versa_escape "$cloudinary_folder")"
};
EOF
  else
    cat >>"$out_file" <<'EOF'
let cloudinary_media_config = null;
EOF
  fi
}

verun_compose_with_prelude() {
  local prelude_file="$1"
  local source_file="$2"
  local out_file="$3"

  awk -v prelude="$prelude_file" '
    function flush_prelude() {
      if (prelude_done) return;
      while ((getline pline < prelude) > 0) print pline;
      close(prelude);
      prelude_done = 1;
    }
    BEGIN { state = "header"; prelude_done = 0; }
    {
      line = $0;
      trimmed = line;
      sub(/^[[:space:]]+/, "", trimmed);

      if (state == "header") {
        if (trimmed == "" || trimmed ~ /^#/) {
          header[++hcount] = line;
          next;
        }
        if (trimmed ~ /^[A-Za-z_][A-Za-z0-9_./-]*[[:space:]]+import([[:space:]]|$)/ || trimmed ~ /^import[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*;/) {
          for (i = 1; i <= hcount; i++) print header[i];
          hcount = 0;
          print line;
          state = "imports";
          next;
        }
        for (i = 1; i <= hcount; i++) print header[i];
        hcount = 0;
        flush_prelude();
        print line;
        state = "body";
        next;
      }

      if (state == "imports") {
        if (trimmed ~ /^[A-Za-z_][A-Za-z0-9_./-]*[[:space:]]+import([[:space:]]|$)/ || trimmed ~ /^import[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*;/ || trimmed == "" || trimmed ~ /^#/) {
          print line;
          next;
        }
        flush_prelude();
        print line;
        state = "body";
        next;
      }

      print line;
    }
    END {
      if (state == "header" || state == "imports") {
        if (state == "header") {
          for (i = 1; i <= hcount; i++) print header[i];
        }
        flush_prelude();
      }
    }
  ' "$source_file" > "$out_file"
}
