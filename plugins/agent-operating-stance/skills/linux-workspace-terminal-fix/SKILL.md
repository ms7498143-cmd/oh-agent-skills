---
name: linux-workspace-terminal-fix
description: "Fix the Linux workspace terminal tool error 'Error validating tool terminal - 1 validation error for TerminalAction command Field required'. Use when the terminal tool fails to validate, when a tool call sends empty arguments, or when starting a workspace agent server on this Linux host."
---

# Linux workspace terminal fix

Repairs the frozen OpenHands agent server so an empty terminal call
(`TerminalAction.model_validate({})`) no longer raises
`Error validating tool 'terminal'`. The root cause is that
`TerminalAction.command` is a required field with no default, so an action
built from `{}` fails validation.

Apply the fix to this workspace:

!`set -e; DEST="${OH_EXTRA_PYTHON_PATH:-/workspace/project/.openhands}"; mkdir -p "$DEST"; SRC="$(dirname "$0")"; cp "$SRC/scripts/patch_terminal_empty_command.py" "$DEST/" 2>/dev/null || true; ls -l "$DEST/patch_terminal_empty_command.py"; echo APPLIED`

## How it takes effect

The agent server loads the patch through its supported extension hook, so the
fix applies to the whole workspace and every conversation started in it:

- The module must sit in the directory named by `OH_EXTRA_PYTHON_PATH`.
- The server must be started with `--import-modules patch_terminal_empty_command`.

The bundled module is idempotent (guarded by `_PATCHED`) and safe to load
repeatedly. It gives `TerminalAction.command` an empty-string default, which is
exactly what the terminal tool passes when no command is supplied.

## Verify

Run the module's self-test with the same interpreter the server uses. Before
the patch an empty action raises the validation error; after it,
`command` is `''`:

!`python3 -c "import sys; sys.path.insert(0, '${OH_EXTRA_PYTHON_PATH:-/workspace/project/.openhands}'); import patch_terminal_empty_command as p; print(p._selftest())" 2>&1 | tail -3`

## Notes

- The server binary is frozen (PyInstaller), so the fix is a runtime
  monkeypatch, not a source edit.
- Keep this skill name unique. Do not reuse a public or marketplace skill
  name, or skill loading fails with `Duplicate skill name found`.
