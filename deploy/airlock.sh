#!/usr/bin/env bash
# Airlock: build/deploy or full cleanup (SQLite + workspace Docker volumes).
# Data lives in <repo>/data (same bind mount as docker-compose ./data:/app/data).
#
# Usage:
#   ./deploy/airlock.sh              # same as deploy
#   ./deploy/airlock.sh deploy       # build, up -d, print URLs
#   ./deploy/airlock.sh deploy --no-build
#   AIRLOCK_ROOT=/path/to/Airlock ./deploy/airlock.sh deploy
#   ./deploy/airlock.sh cleanup      # stop stack, delete ./data, remove airlock_ws_* volumes
#   ./deploy/airlock.sh cleanup --rmi-local   # also remove images built by this compose file
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${AIRLOCK_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.yml}"

cd "$ROOT"

compose() {
  docker compose -f "$COMPOSE_FILE" --project-directory "$ROOT" "$@"
}

ensure_env() {
  if [[ ! -f "$ROOT/.env" ]]; then
    if [[ -f "$ROOT/.env.example" ]]; then
      cp "$ROOT/.env.example" "$ROOT/.env"
      echo "Created $ROOT/.env from .env.example — set JWT_SECRET and SESSION_SECRET before production." >&2
    else
      echo "Missing $ROOT/.env and no .env.example; create .env manually." >&2
      exit 1
    fi
  fi
}

ensure_data_dir() {
  mkdir -p "$ROOT/data"
}

env_val() {
  local key="$1"
  [[ -f "$ROOT/.env" ]] || return 0
  grep -E "^${key}=" "$ROOT/.env" 2>/dev/null | head -1 | sed -E "s/^${key}=//; s/^[\"']//; s/[\"']$//" || true
}

compose_host_url() {
  local raw="$1"
  if [[ -z "$raw" ]]; then
    echo "(service not running)"
    return
  fi
  local port="${raw##*:}"
  echo "http://127.0.0.1:${port}"
}

print_access() {
  local fe_addr be_addr fe_url api_url
  fe_addr=$(compose port frontend 5173 2>/dev/null || true)
  be_addr=$(compose port backend 8000 2>/dev/null || true)
  fe_url=$(compose_host_url "$fe_addr")
  api_url=$(compose_host_url "$be_addr")

  local env_fe env_wo
  env_fe="$(env_val FRONTEND_URL)"
  env_wo="$(env_val WEBAUTHN_ORIGIN)"

  echo ""
  echo "=== Airlock — access ==="
  echo "  Project root:  $ROOT"
  echo "  Data (SQLite): $ROOT/data"
  echo "  UI (published):  $fe_url"
  echo "  API (published): $api_url"
  if [[ -n "$env_fe" ]]; then
    echo "  FRONTEND_URL (.env): $env_fe"
  fi
  if [[ -n "$env_wo" ]]; then
    echo "  WEBAUTHN_ORIGIN:     $env_wo"
  fi
  if [[ "$api_url" != "(service not running)" ]]; then
    echo "  API docs:            ${api_url}/docs"
  fi
  echo "========================"
  echo ""
}

cmd_deploy() {
  local do_build=1
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-build) do_build=0 ;;
      -h|--help)
        echo "Usage: $0 deploy [--no-build]"
        exit 0
        ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
  done

  ensure_env
  ensure_data_dir

  if [[ "$do_build" -eq 1 ]]; then
    compose build
  fi
  compose up -d --remove-orphans
  print_access
}

remove_workspace_volumes() {
  local vols
  vols=$(docker volume ls -q 2>/dev/null | grep -E '^airlock_ws_' || true)
  [[ -z "$vols" ]] && return 0
  while read -r v; do
    [[ -z "$v" ]] && continue
    docker volume rm "$v" 2>/dev/null || true
  done <<< "$vols"
}

cmd_cleanup() {
  local rmi_local=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --rmi-local) rmi_local=1 ;;
      -h|--help)
        echo "Usage: $0 cleanup [--rmi-local]"
        exit 0
        ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
  done

  if [[ "$rmi_local" -eq 1 ]]; then
    compose down --remove-orphans --rmi local 2>/dev/null || compose down --remove-orphans 2>/dev/null || true
  else
    compose down --remove-orphans 2>/dev/null || true
  fi

  if [[ -d "$ROOT/data" ]]; then
    rm -rf "$ROOT/data"
    echo "Removed $ROOT/data (SQLite DB, audit log, and other local data)."
  else
    echo "No $ROOT/data directory."
  fi

  remove_workspace_volumes
  echo "Removed Docker volumes named airlock_ws_* (per-user workspace data), if any."

  if [[ "$rmi_local" -eq 1 ]]; then
    echo "Cleanup finished (compose images with --rmi local were removed where supported)."
  else
    echo "Cleanup finished. Re-run with cleanup --rmi-local to drop compose-built images, or prune Docker manually."
  fi
}

main() {
  local cmd="deploy"
  if [[ $# -eq 0 ]]; then
    cmd_deploy
    return
  fi
  case "$1" in
    deploy|cleanup|-h|--help) cmd="$1"; shift ;;
    -*)
      cmd_deploy "$@"
      return
      ;;
  esac

  case "$cmd" in
    deploy) cmd_deploy "$@" ;;
    cleanup) cmd_cleanup "$@" ;;
    -h|--help)
      echo "Usage: $0 [deploy|cleanup] [options]"
      echo ""
      echo "  deploy   Build images, start stack, print UI/API URLs. Data: \$ROOT/data"
      echo "           Options: --no-build"
      echo "  cleanup  Stop stack, delete ./data, remove airlock_ws_* volumes"
      echo "           Options: --rmi-local (also remove compose-built images)"
      echo ""
      echo "Environment:"
      echo "  AIRLOCK_ROOT   Repository root (default: parent of deploy/)"
      echo "  COMPOSE_FILE   Override compose file path"
      exit 0
      ;;
    *)
      echo "Unknown command: $cmd (use deploy or cleanup)" >&2
      exit 1
      ;;
  esac
}

main "$@"
