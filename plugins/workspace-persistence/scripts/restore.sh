#!/usr/bin/env bash
# Restore the latest snapshot at session start. Always exits 0.
set -uo pipefail
cd "$(dirname "$0")" && . ./_config.sh

ws_enabled || exit 0
MARKER="$WS_SRC/.workspace-state-restored"
[ -f "$MARKER" ] && exit 0

WORK=$(mktemp -d) || exit 0
trap 'rm -rf "$WORK"' EXIT

git clone -q --depth 1 --branch "$WS_BRANCH" "$(ws_remote)" "$WORK/repo" 2>/dev/null || exit 0

if [ -f "$WORK/repo/state.tgz.enc" ]; then
  [ -n "$WS_KEY" ] || { ws_log "restore skipped: encrypted snapshot, no WS_STATE_KEY"; exit 0; }
  ws_decrypt "$WORK/repo/state.tgz.enc" "$WORK/state.tgz" || { ws_log "decrypt failed"; exit 0; }
elif [ -f "$WORK/repo/state.tgz" ]; then
  cp "$WORK/repo/state.tgz" "$WORK/state.tgz"
else
  exit 0
fi

mkdir -p "$WS_SRC"
tar xzf "$WORK/state.tgz" -C "$WS_SRC" --skip-old-files 2>/dev/null \
  || tar xzf "$WORK/state.tgz" -C "$WS_SRC" 2>/dev/null || { ws_log "extract failed"; exit 0; }

touch "$MARKER"
stamp=$(cat "$WS_SRC/.workspace-state/snapshot-at.txt" 2>/dev/null)
ws_log "restored from ${stamp:-unknown}"
printf 'Workspace restored from snapshot %s.\n' "${stamp:-unknown}"
printf 'Recorded packages can be reinstalled with: bash "%s/bootstrap.sh"\n' "$(dirname "$0")"
exit 0
