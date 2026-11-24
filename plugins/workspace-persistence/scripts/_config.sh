# Shared config for the workspace-persistence hooks. Sourced, not executed.
WS_STATE_CONF="${WS_STATE_CONF:-$HOME/.workspace-state.conf}"
# shellcheck disable=SC1090
[ -f "$WS_STATE_CONF" ] && . "$WS_STATE_CONF"

WS_REPO="${WS_STATE_REPO:-ms7498143-cmd/oh-agent-skills}"
WS_BRANCH="${WS_STATE_BRANCH:-workspace-state}"
WS_SRC="${WS_STATE_SRC:-/workspace}"
WS_MAX_MB="${WS_STATE_MAX_MB:-40}"
WS_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-${WS_STATE_TOKEN:-}}}"
WS_KEY="${WS_STATE_KEY:-}"
WS_ALLOW_PLAINTEXT="${WS_STATE_ALLOW_PLAINTEXT:-0}"
WS_LOG="${WS_STATE_LOG:-$HOME/.workspace-state.log}"

ws_log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$WS_LOG" 2>/dev/null; }

ws_remote() {
  case "$WS_REPO" in
    http*|git@*|/*|.*) printf '%s' "$WS_REPO" ;;
    */*) printf 'https://x-access-token:%s@github.com/%s.git' "$WS_TOKEN" "$WS_REPO" ;;
    *) printf '%s' "$WS_REPO" ;;
  esac
}

ws_enabled() {
  [ -n "$WS_REPO" ] || { ws_log "disabled: WS_STATE_REPO not set"; return 1; }
  case "$WS_REPO" in
    http*|git@*|/*|.*) return 0 ;;
  esac
  [ -n "$WS_TOKEN" ] || { ws_log "disabled: no token"; return 1; }
  return 0
}

# Snapshots are encrypted unless the operator explicitly opts into plaintext
# for a private remote.
ws_can_write() {
  if [ -n "$WS_KEY" ]; then return 0; fi
  if [ "$WS_ALLOW_PLAINTEXT" = "1" ]; then return 0; fi
  ws_log "disabled: WS_STATE_KEY not set and plaintext not allowed"
  return 1
}

ws_decrypt() {
  openssl enc -d -aes-256-cbc -pbkdf2 -salt -pass env:WS_STATE_KEY -in "$1" -out "$2" 2>/dev/null
}
