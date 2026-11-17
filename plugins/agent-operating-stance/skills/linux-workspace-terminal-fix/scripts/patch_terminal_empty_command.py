"""Workspace-local patch: tolerate `terminal` tool calls with no arguments.

Background
----------
`openhands.sdk.agent.agent._get_action_event` builds each action with
``tool.action_from_arguments(arguments)``, which calls
``TerminalAction.model_validate(arguments)``. ``TerminalAction.command`` is a
required pydantic field with no default, so when the model emits a `terminal`
call with empty arguments (``{}``) pydantic raises::

    Error validating tool 'terminal': 1 validation error for TerminalAction
    command
      Field required

Fix
---
Give ``TerminalAction.command`` a default of ``""`` (the tool already documents
the empty string as valid: "view additional logs when the previous exit code is
-1"). This is applied by monkeypatch because the agent-server ships as a frozen
PyInstaller binary with no editable SDK source.

Load it with the agent-server's built-in extension hook::

    OH_EXTRA_PYTHON_PATH=/workspace/project/.openhands \
        openhands-agent-server --import-modules patch_terminal_empty_command
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PATCHED = False


def _patch(cls) -> bool:
    """Give ``cls.command`` an empty-string default. Returns True if changed."""
    field = cls.model_fields.get("command")
    if field is None:  # pragma: no cover - unexpected SDK shape
        logger.warning("terminal patch: %s has no 'command' field", cls.__name__)
        return False
    if not field.is_required() and field.default == "":
        return True
    field.default = ""
    # Pydantic caches validators/schema; force a rebuild so the new default and
    # the "not required" schema take effect.
    cls.model_rebuild(force=True)
    logger.info("terminal patch: %s.command defaulted to ''", cls.__name__)
    return True


def apply() -> bool:
    """Patch the terminal action so an empty call validates. Idempotent."""
    global _PATCHED
    if _PATCHED:
        return True

    from openhands.tools.terminal.definition import TerminalAction

    _PATCHED = _patch(TerminalAction)
    return _PATCHED


def _selftest() -> None:
    """Write proof that the frozen SDK now accepts an empty terminal call."""
    import json

    from pydantic_core import PydanticUndefined

    from openhands.tools.terminal.definition import TerminalAction

    # `ToolDefinition.action_from_arguments` reduces to this exact call for the
    # terminal tool (no response_schema), so it is the operation that failed.
    def _validate_empty() -> str:
        try:
            return f"ok: command={TerminalAction.model_validate({}).command!r}"
        except Exception as exc:
            return f"{type(exc).__name__}: {str(exc).splitlines()[0]}"

    field = TerminalAction.model_fields["command"]

    # 1. Reproduce the unpatched state: `command` required (no default).
    field.default = PydanticUndefined
    TerminalAction.model_rebuild(force=True)
    before = _validate_empty()

    # 2. Apply the patch and re-validate.
    patched = _patch(TerminalAction)
    after = _validate_empty()

    with open(os.environ["OH_PATCH_SELFTEST"], "w", encoding="utf-8") as fh:
        json.dump({"before": before, "patched": patched, "after": after}, fh, indent=2)


apply()

if os.environ.get("OH_PATCH_SELFTEST"):
    _selftest()
