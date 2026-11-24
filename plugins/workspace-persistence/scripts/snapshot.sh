#!/usr/bin/env bash
# Snapshot $WS_SRC plus package manifests to the state branch. Always exits 0.
set -uo pipefail
cd "$(dirname "$0")" && . ./_config.sh

THROTTLE=0
[ "${1:-}" = "--throttle" ] && THROTTLE="${2:-0}"

ws_enabled || exit 0
ws_can_write || exit 0

STAMP=/tmp/.ws-snapshot-last
if [ "$THROTTLE" -gt 0 ] && [ -f "$STAMP" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  [ $(( $(date +%s) - last )) -lt "$THROTTLE" ] && exit 0
fi
date +%s >"$STAMP"

MAN="$WS_SRC/.workspace-state"
mkdir -p "$MAN" 2>/dev/null || exit 0
python3 -m pip freeze >"$MAN/pip-freeze.txt" 2>/dev/null || :
npm ls -g --depth=0 --parseable 2>/dev/null | tail -n +2 >"$MAN/npm-global.txt" || :
dpkg --get-selections 2>/dev/null | awk '$2=="install"{print $1}' >"$MAN/apt.txt" || :
date -u +%FT%TZ >"$MAN/snapshot-at.txt"
hostname >"$MAN/host.txt" 2>/dev/null || :

WORK=$(mktemp -d) || exit 0
trap 'rm -rf "$WORK"' EXIT

if ! git clone -q --depth 1 --branch "$WS_BRANCH" "$(ws_remote)" "$WORK/repo" 2>/dev/null; then
  mkdir -p "$WORK/repo" && cd "$WORK/repo" || exit 0
  git init -q && git checkout -q -b "$WS_BRANCH" 2>/dev/null
  git remote add origin "$(ws_remote)"
else
  cd "$WORK/repo" || exit 0
fi

EXCLUDES=(
  --exclude=node_modules --exclude=.venv --exclude=venv --exclude=__pycache__
  --exclude='*.pyc' --exclude=.git --exclude=.cache --exclude='*.log'
  --exclude=.npm --exclude=.cargo --exclude=target --exclude=dist --exclude=build
  --exclude=.env --exclude='*.pem' --exclude='*.key' --exclude='id_rsa*'
  --exclude='*.token' --exclude=secrets.json --exclude=.github-token
  --exclude=.agent_tmp --exclude=.workspace-state-restored
)

tar czf "$WORK/state.tgz" -C "$WS_SRC" "${EXCLUDES[@]}" . 2>/dev/null || { ws_log "tar failed"; exit 0; }

size_mb=$(( $(stat -c%s "$WORK/state.tgz" 2>/dev/null || echo 0) / 1048576 ))
if [ "$size_mb" -gt "$WS_MAX_MB" ]; then
  ws_log "skip: snapshot ${size_mb}MB exceeds ${WS_MAX_MB}MB"
  exit 0
fi

rm -f state.tgz state.tgz.enc
if [ -n "$WS_KEY" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:WS_STATE_KEY \
    -in "$WORK/state.tgz" -out state.tgz.enc 2>/dev/null || { ws_log "encrypt failed"; exit 0; }
else
  cp "$WORK/state.tgz" state.tgz
fi
printf '/state.tgz\n' >.gitignore

git add -A >/dev/null 2>&1
git -c user.name=openhands -c user.email=openhands@all-hands.dev \
    commit -q -m "snapshot $(date -u +%FT%TZ) $(hostname 2>/dev/null)" >/dev/null 2>&1 \
    || { ws_log "nothing to commit"; exit 0; }
git push -q --force origin "$WS_BRANCH" >/dev/null 2>&1 || { ws_log "push failed"; exit 0; }
ws_log "snapshot pushed ${size_mb}MB"
exit 0
