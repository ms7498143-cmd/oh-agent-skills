# oh-agent-skills

An OpenHands / Claude Code skill marketplace. Register it account-wide, then
enable the plugin per workspace.

```bash
POST https://app.all-hands.dev/api/v1/settings
{
  "registered_marketplaces": [
    {
      "name": "oh-agent-skills",
      "source": "https://github.com/ms7498143-cmd/oh-agent-skills",
      "ref": null,
      "repo_path": null,
      "auto_load": true,
      "scope": "personal"
    }
  ]
}
```

## Plugins

### `agent-operating-stance`

| Skill | Purpose |
| --- | --- |
| `decisive-execution` | Operating stance: nothing is impossible, treat "can't" as an untested hypothesis, conclude every task as done or blocked, move fast. |
| `deepseek-coding-conventions` | Delivery and communication conventions for engineering work: lead with the result, separate facts from assumptions, preserve code and errors exactly. |
| `linux-workspace-terminal-fix` | Fix for `Error validating tool 'terminal': ... command Field required`. Bundles an idempotent monkeypatch module and its verification self-test. |

## Terminal fix: activation

The bundled patch is a runtime monkeypatch, because the agent server ships as a
frozen PyInstaller binary with no editable SDK source. It gives
`TerminalAction.command` an empty-string default, so a terminal call with empty
arguments validates instead of raising.

A skill injects prompt text; it cannot change how an already-running server was
started. Activate the patch by loading the module through the server's own
extension hook:

```bash
OH_EXTRA_PYTHON_PATH=<path containing patch_terminal_empty_command.py> \
  openhands-agent-server --port 60000 --import-modules patch_terminal_empty_command
```

Verify against the real binary:

```bash
OH_EXTRA_PYTHON_PATH=<path> OH_PATCH_SELFTEST=/tmp/selftest.json \
  openhands-agent-server --port 60001 --import-modules patch_terminal_empty_command
cat /tmp/selftest.json
```

Expected result:

```json
{
  "before": "ValidationError: 1 validation error for TerminalAction",
  "patched": true,
  "after": "ok: command=''"
}
```
