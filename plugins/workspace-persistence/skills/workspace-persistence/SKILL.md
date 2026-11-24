---
name: workspace-persistence
description: Keep work across sandbox resets. Snapshots the workspace and installed package manifests to an encrypted git branch, and restores them at session start. Use when a sandbox was reset, when files or packages are missing, or when the operator asks to make the workspace survive restarts.
---

# Workspace persistence

OpenHands cloud sandboxes are ephemeral. A reset, a reap, or a new conversation
starts from an empty `/workspace`, so installed packages and unsaved files are
gone. This plugin makes the workspace reproducible instead of trying to keep the
sandbox alive.

## What runs automatically

| Hook | Script | Effect |
|---|---|---|
| `SessionStart` | `scripts/restore.sh` | Restores the latest snapshot into `/workspace` if this sandbox has not restored yet |
| `UserPromptSubmit` | `scripts/snapshot.sh --throttle 600` | Snapshots at most every 10 minutes |
| `Stop` | `scripts/snapshot.sh --throttle 120` | Snapshots after a turn, at most every 2 minutes |
| `SessionEnd` | `scripts/snapshot.sh` | Final snapshot |

Every script exits 0 on every failure path, so a missing token or an
unreachable remote never blocks a session.

## Storage

- Default target: branch `workspace-state` of `ms7498143-cmd/oh-agent-skills`.
- The branch holds `state.tgz.enc`, an AES-256-CBC (PBKDF2) blob. Manifests and
  files are inside the archive, never in the clear.
- `WS_STATE_KEY` must be present or nothing is written. Set it as an account
  secret so every sandbox receives it.
- Point `WS_STATE_REPO` at a private repository to store plaintext instead and
  set `WS_STATE_ALLOW_PLAINTEXT=1`.

Configuration lives in `~/.workspace-state.conf` (sourced shell) or the
environment:

```sh
WS_STATE_REPO=owner/name        # default ms7498143-cmd/oh-agent-skills
WS_STATE_BRANCH=workspace-state # branch holding the snapshot
WS_STATE_KEY=...                # encryption passphrase (secret)
WS_STATE_SRC=/workspace         # directory to snapshot
WS_STATE_MAX_MB=40              # skip snapshots larger than this
WS_STATE_ALLOW_PLAINTEXT=0      # 1 = allow unencrypted snapshots
```

## Manual use

```sh
bash "$PLUGIN_ROOT/scripts/snapshot.sh"    # snapshot now
bash "$PLUGIN_ROOT/scripts/restore.sh"     # restore now (ignores the once-per-sandbox marker)
bash "$PLUGIN_ROOT/scripts/bootstrap.sh"   # reinstall pip/npm/apt packages from the last snapshot
```

Restore never overwrites existing files: it extracts with `--skip-old-files`, so
a partially rebuilt workspace keeps its newer work.

## What is excluded

`node_modules`, `.venv`, `venv`, `__pycache__`, `*.pyc`, `.git`, caches, build
output, `*.log`, and secret-bearing files (`.env`, `*.pem`, `*.key`, `id_rsa*`,
`*.token`, `secrets.json`, `.github-token`). Secrets are expected to live in the
account secret store, not in the snapshot.

## Limits

- Snapshots are capped at `WS_STATE_MAX_MB` (40 MB default). Larger workspaces
  skip the snapshot and log why; keep big assets in git or object storage.
- History is force-pushed to a single commit so the branch stays small. Only the
  newest snapshot is kept.
- The passphrase is not recoverable. Losing `WS_STATE_KEY` makes existing
  snapshots unreadable.
