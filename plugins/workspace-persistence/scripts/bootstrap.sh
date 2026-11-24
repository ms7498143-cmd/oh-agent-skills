#!/usr/bin/env bash
# Reinstall the packages recorded in the last snapshot. Always exits 0.
set -uo pipefail
cd "$(dirname "$0")" && . ./_config.sh

MAN="$WS_SRC/.workspace-state"
[ -d "$MAN" ] || { echo "no manifest at $MAN"; exit 0; }

if [ -s "$MAN/pip-freeze.txt" ]; then
  python3 -m pip install -q -r "$MAN/pip-freeze.txt" 2>&1 | tail -5
fi
if [ -s "$MAN/npm-global.txt" ] && command -v npm >/dev/null 2>&1; then
  xargs -r npm install -g <"$MAN/npm-global.txt" 2>&1 | tail -3
fi
if [ -s "$MAN/apt.txt" ] && command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
  xargs -r apt-get install -y <"$MAN/apt.txt" 2>&1 | tail -3
fi
echo "bootstrap done"
exit 0
