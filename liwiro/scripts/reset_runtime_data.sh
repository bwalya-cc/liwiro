#!/usr/bin/env bash
# Remove Liwiro/Verun runtime state while preserving source and configuration.
#
# Usage:
#   liwiro/scripts/reset_runtime_data.sh          # erase runtime/data, keep VDB history
#   liwiro/scripts/reset_runtime_data.sh --yes    # same without prompting
#   liwiro/scripts/reset_runtime_data.sh --full-reset --yes  # explicit full reset
#   liwiro/scripts/reset_runtime_data.sh --dry-run
#   liwiro/scripts/reset_runtime_data.sh --full-reset --yes --clear-command-history

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIWIRO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$LIWIRO_ROOT/.." && pwd)"

assume_yes=0
dry_run=0
full_reset=0
clear_command_history=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) assume_yes=1 ;;
    --dry-run) dry_run=1 ;;
    --full-reset|--all-data) full_reset=1 ;;
    --clear-command-history) clear_command_history=1 ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$arg" >&2
      exit 2
      ;;
  esac
done

if (( clear_command_history && ! full_reset )); then
  printf '%s requires --full-reset; command history was not cleared.\n' '--clear-command-history' >&2
  exit 2
fi

# Every path below is derived from the repository root and is deliberately
# enumerated. Config files (LAPIS examples, schemas, source, env templates,
# and runtime JSON settings) are not included.
files=(
  "$LIWIRO_ROOT/backend/.runtime/liwiro.vdb.auth.json"
  "$LIWIRO_ROOT/backend/.runtime/liwiro.frontend.sessions.json"
  "$LIWIRO_ROOT/backend/.runtime/backend.env.local"
)
directories=(
  "$LIWIRO_ROOT/backend/.runtime/generated-service-runtime"
  "$LIWIRO_ROOT/data/verse"
  "$LIWIRO_ROOT/logs"
  "$REPO_ROOT/logs"
  "$REPO_ROOT/tmp/runtime-logs"
  "$REPO_ROOT/verun/logs"
  "$REPO_ROOT/verun/vi/logs"
  "$REPO_ROOT/verun/vi/tmp"
  "$REPO_ROOT/verun/vdb/logs"
)
for backup_dir in "$REPO_ROOT"/tmp/app-data-backup-*; do
  directories+=("$backup_dir")
done

vdb_data_root="$REPO_ROOT/verun/vdb/__data__"
vdb_history_path="$vdb_data_root/sys/command_history.txt"

for path in "${files[@]}" "${directories[@]}"; do
  case "$path" in
    "$LIWIRO_ROOT"/*|"$REPO_ROOT"/*) ;;
    *) printf 'Refusing unsafe path: %s\n' "$path" >&2; exit 1 ;;
  esac
done

case "$vdb_data_root" in
  "$LIWIRO_ROOT"/*|"$REPO_ROOT"/*) ;;
  *) printf 'Refusing unsafe path: %s\n' "$vdb_data_root" >&2; exit 1 ;;
esac

printf 'Runtime reset targets (configs are preserved):\n'
for path in "${files[@]}" "${directories[@]}"; do
  if [[ -e "$path" || -L "$path" ]]; then
    printf '  %s\n' "${path#"$REPO_ROOT"/}"
  fi
done
if [[ -e "$vdb_data_root" ]]; then
  printf '  %s\n' "${vdb_data_root#"$REPO_ROOT"/}" 
  if (( ! clear_command_history )) && [[ -f "$vdb_history_path" ]]; then
    printf '  preserving %s\n' "${vdb_history_path#"$REPO_ROOT"/}"
  fi
fi

if (( dry_run )); then
  exit 0
fi

if (( ! assume_yes )); then
  if (( full_reset )); then
    printf '\nThis permanently removes runtime users, keys, sessions, VDB data, Verse data, logs, and generated-service data. Continue? [y/N] '
  else
    printf '\nThis permanently removes runtime credentials, sessions, VDB data, Verse data, logs, and generated-service data; only VDB command history is preserved. Continue? [y/N] '
  fi
  read -r reply
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]] || { printf 'Cancelled.\n'; exit 0; }
fi

remove_path() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    rm -rf -- "$path"
    printf 'removed %s\n' "${path#"$REPO_ROOT"/}"
  fi
}

remove_vdb_data() {
  [[ -d "$vdb_data_root" ]] || return 0
  local child base
  for child in "$vdb_data_root"/* "$vdb_data_root"/.[!.]* "$vdb_data_root"/..?*; do
    [[ -e "$child" || -L "$child" ]] || continue
    base="${child#"$vdb_data_root"/}"
    if (( ! clear_command_history )) && [[ "$base" == "sys" ]]; then
      # Remove all system state except the persisted interactive command history.
      find "$child" -mindepth 1 -maxdepth 1 ! -path "$vdb_history_path" -exec rm -rf -- {} +
      continue
    fi
    if (( ! clear_command_history )) && [[ "$child" == "$vdb_history_path" ]]; then
      continue
    fi
    rm -rf -- "$child"
  done
  printf 'removed %s (command history %s)\n' "${vdb_data_root#"$REPO_ROOT"/}" "$([[ $clear_command_history -eq 1 ]] && echo cleared || echo preserved)"
}

for path in "${files[@]}" "${directories[@]}"; do
  remove_path "$path"
done
remove_vdb_data

# Recreate runtime containers with their harmless placeholders, without
# recreating credentials or data files.
mkdir -p "$LIWIRO_ROOT/backend/.runtime" "$LIWIRO_ROOT/data/verse/datasets" \
  "$LIWIRO_ROOT/data/verse/dataset_archives" "$LIWIRO_ROOT/data/verse/threads" \
  "$REPO_ROOT/verun/vdb/__data__" "$REPO_ROOT/verun/vdb/logs" "$REPO_ROOT/verun/vi/logs"
touch "$LIWIRO_ROOT/data/verse/datasets/.gitkeep" \
  "$LIWIRO_ROOT/data/verse/dataset_archives/.gitkeep" \
  "$LIWIRO_ROOT/data/verse/threads/.gitkeep"
printf 'Runtime data reset complete. Start the app to regenerate fresh credentials/state.\n'
