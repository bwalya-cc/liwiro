#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

if [ -n "${LIWIRO_UI_LIB_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
LIWIRO_UI_LIB_LOADED=1

liwiro_ui_supports_color() {
  [ -t 2 ] || return 1
  [ "${TERM:-}" != "dumb" ] || return 1
  [ -z "${NO_COLOR:-}" ] || return 1
  return 0
}

liwiro_ui_supports_unicode() {
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *UTF-8*|*utf8*|*utf-8*) return 0 ;;
  esac
  return 1
}

if liwiro_ui_supports_color; then
  LIWIRO_UI_RESET="$(printf '\033[0m')"
  LIWIRO_UI_BOLD="$(printf '\033[1m')"
  LIWIRO_UI_DIM="$(printf '\033[2m')"
  LIWIRO_UI_BLUE="$(printf '\033[38;5;39m')"
  LIWIRO_UI_CYAN="$(printf '\033[38;5;44m')"
  LIWIRO_UI_GREEN="$(printf '\033[38;5;41m')"
  LIWIRO_UI_YELLOW="$(printf '\033[38;5;214m')"
  LIWIRO_UI_RED="$(printf '\033[38;5;196m')"
  LIWIRO_UI_MAGENTA="$(printf '\033[38;5;141m')"
else
  LIWIRO_UI_RESET=""
  LIWIRO_UI_BOLD=""
  LIWIRO_UI_DIM=""
  LIWIRO_UI_BLUE=""
  LIWIRO_UI_CYAN=""
  LIWIRO_UI_GREEN=""
  LIWIRO_UI_YELLOW=""
  LIWIRO_UI_RED=""
  LIWIRO_UI_MAGENTA=""
fi

if liwiro_ui_supports_unicode; then
  LIWIRO_ICON_SECTION="◆"
  LIWIRO_ICON_STEP="▸"
  LIWIRO_ICON_OK="✓"
  LIWIRO_ICON_WARN="▲"
  LIWIRO_ICON_ERROR="✕"
  LIWIRO_ICON_INFO="ℹ"
  LIWIRO_ICON_REUSE="↺"
  LIWIRO_ICON_LOG="•"
  LIWIRO_ICON_WAIT="◌"
else
  LIWIRO_ICON_SECTION="="
  LIWIRO_ICON_STEP=">"
  LIWIRO_ICON_OK="[ok]"
  LIWIRO_ICON_WARN="[!]"
  LIWIRO_ICON_ERROR="[x]"
  LIWIRO_ICON_INFO="[i]"
  LIWIRO_ICON_REUSE="[=]"
  LIWIRO_ICON_LOG="[-]"
  LIWIRO_ICON_WAIT="[...]"
fi

liwiro_ui_newline() {
  printf '\n' >&2
}

liwiro_ui_rule() {
  local width="${1:-${COLUMNS:-72}}"
  if [ "$width" -gt 88 ]; then
    width=88
  fi
  if [ "$width" -lt 32 ]; then
    width=32
  fi
  local char="-"
  if liwiro_ui_supports_unicode; then
    char="─"
  fi
  local line
  printf -v line '%*s' "$width" ''
  line="${line// /$char}"
  printf '%s%s%s\n' "$LIWIRO_UI_DIM" "$line" "$LIWIRO_UI_RESET" >&2
}

liwiro_ui_banner() {
  local title="$1"
  local subtitle="${2:-}"
  liwiro_ui_rule
  printf '%s%s%s\n' "$LIWIRO_UI_BOLD$LIWIRO_UI_BLUE" "$title" "$LIWIRO_UI_RESET" >&2
  if [ -n "$subtitle" ]; then
    printf '%s%s%s\n' "$LIWIRO_UI_DIM" "$subtitle" "$LIWIRO_UI_RESET" >&2
  fi
  liwiro_ui_rule
}

liwiro_ui_section() {
  printf '%s%s %s%s\n' "$LIWIRO_UI_BOLD$LIWIRO_UI_BLUE" "$LIWIRO_ICON_SECTION" "$*" "$LIWIRO_UI_RESET" >&2
}

liwiro_ui_step() {
  printf '%s%s%s %s\n' "$LIWIRO_UI_CYAN" "$LIWIRO_ICON_STEP" "$LIWIRO_UI_RESET" "$*" >&2
}

liwiro_ui_ok() {
  printf '%s%s%s %s\n' "$LIWIRO_UI_GREEN" "$LIWIRO_ICON_OK" "$LIWIRO_UI_RESET" "$*" >&2
}

liwiro_ui_warn() {
  printf '%s%s%s %s\n' "$LIWIRO_UI_YELLOW" "$LIWIRO_ICON_WARN" "$LIWIRO_UI_RESET" "$*" >&2
}

liwiro_ui_error() {
  printf '%s%s%s %s\n' "$LIWIRO_UI_RED" "$LIWIRO_ICON_ERROR" "$LIWIRO_UI_RESET" "$*" >&2
}

liwiro_ui_info() {
  printf '%s%s%s %s\n' "$LIWIRO_UI_MAGENTA" "$LIWIRO_ICON_INFO" "$LIWIRO_UI_RESET" "$*" >&2
}

liwiro_ui_kv() {
  local label="$1"
  local value="$2"
  local width="${3:-14}"
  printf '  %s%-*s%s %s\n' "$LIWIRO_UI_DIM" "$width" "$label" "$LIWIRO_UI_RESET" "$value" >&2
}

liwiro_ui_status() {
  local state="$(printf '%s' "${1:-info}" | tr '[:upper:]' '[:lower:]')"
  local label="$2"
  local detail="${3:-}"
  local color="$LIWIRO_UI_MAGENTA"
  local icon="$LIWIRO_ICON_INFO"
  local tag="INFO"
  case "$state" in
    start|starting)
      color="$LIWIRO_UI_CYAN"
      icon="$LIWIRO_ICON_STEP"
      tag="START"
      ;;
    wait|waiting)
      color="$LIWIRO_UI_BLUE"
      icon="$LIWIRO_ICON_WAIT"
      tag="WAIT"
      ;;
    ok|ready|healthy)
      color="$LIWIRO_UI_GREEN"
      icon="$LIWIRO_ICON_OK"
      tag="READY"
      ;;
    reuse|existing|cached)
      color="$LIWIRO_UI_GREEN"
      icon="$LIWIRO_ICON_REUSE"
      tag="REUSE"
      ;;
    warn|warning)
      color="$LIWIRO_UI_YELLOW"
      icon="$LIWIRO_ICON_WARN"
      tag="WARN"
      ;;
    error|failed|fail)
      color="$LIWIRO_UI_RED"
      icon="$LIWIRO_ICON_ERROR"
      tag="FAIL"
      ;;
    log|path)
      color="$LIWIRO_UI_DIM"
      icon="$LIWIRO_ICON_LOG"
      tag="LOG"
      ;;
    stop|cleanup)
      color="$LIWIRO_UI_YELLOW"
      icon="$LIWIRO_ICON_WARN"
      tag="STOP"
      ;;
  esac
  printf '  %s%s %-6s%s %-16s %s\n' "$color" "$icon" "$tag" "$LIWIRO_UI_RESET" "$label" "$detail" >&2
}
