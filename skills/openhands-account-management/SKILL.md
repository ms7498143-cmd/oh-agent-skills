---
name: openhands-account-management
description: Manage an OpenHands account end to end from an agent - account settings, persona, enabled skills, marketplaces, secrets, sandboxes, conversations and billing. Use whenever the operator asks to change account settings, apply a persona, disable a skill, add a marketplace, store a secret, inspect or delete sandboxes and conversations, check or top up credits, or asks why a sandbox/conversation behaves as it does. Carries verified endpoints and the traps, so no re-analysis is needed.
---

# OpenHands account management

Account: `ms7498143@gmail.com` on `https://app.all-hands.dev`. Auth is the injected
`OPENHANDS_API_KEY` (Bearer). Everything below was verified against the live API.

Run commands with the bundled CLI instead of hand-writing requests:

```bash
python3 <plugin>/scripts/ohacct.py status          # one-screen truth
python3 <plugin>/scripts/ohacct.py settings-show agent_settings
python3 <plugin>/scripts/ohacct.py persona-set /var/openhands/persona.md
python3 <plugin>/scripts/ohacct.py skill-disable universal-hardware
python3 <plugin>/scripts/ohacct.py marketplaces
python3 <plugin>/scripts/ohacct.py sandboxes
python3 <plugin>/scripts/ohacct.py conversations --limit 20
python3 <plugin>/scripts/ohacct.py billing
python3 <plugin>/scripts/ohacct.py topup 10        # returns a Stripe URL, no charge
```

`REFERENCE.md` in this skill lists every endpoint and its observed behaviour.

## The traps that cost hours

1. **Settings writes use POST, never PATCH.** `POST /api/v1/settings`. PATCH returns 405.
2. **Nested settings need a `*_diff` wrapper**: `{"agent_settings_diff": {...}}`,
   `{"conversation_settings_diff": {...}}`. Plain scalars post directly:
   `disabled_skills`, `default_sandbox_spec_id`, `sandbox_base_container_image`,
   `sandbox_runtime_container_image`, `remote_runtime_resource_factor`.
3. **Billing is not under `/api/v1`**: it is `/api/billing/credits`.
4. `POST /api/billing/has-payment-method` returns a **bare bool**, not an object.
5. **Credits are read-only.** Only a completed Stripe checkout writes a balance;
   there is no grant endpoint in all 273 paths. Never promise to add credits,
   and never write to All-Hands' ledger.
6. **Sandbox specs are read-only** (`POST` → 405) and carry only `image`,
   `command`, `initial_env`, `working_dir`. No cpu, memory, disk or device fields.
7. **Hardware cannot be raised on this deployment.** Measured twice on fresh
   sandboxes: `remote_runtime_resource_factor = 8` → `nproc 4`; then
   `container_cpus = 50`, `container_memory = 150g` → `nproc 4`, `cpu.max = max`,
   15 GB RAM, 25 GB `/workspace`, 0 GPU, 0 NPU. The container is already uncapped
   and the host has 4 vCPU. Report the ceiling; do not fake a larger view.
8. **Sandboxes are reaped after 20 minutes idle** (`OH_RUNTIME_IDLE_TIMEOUT_SECONDS
   = 1200`). The conversation then shows `MISSING` and looks deleted, but its
   events persist: `GET /api/v1/app-conversations/{id}/download` returns the full
   trajectory. Explain this instead of restoring from a backup.
9. **A persona replaces the built-in workflow guidance**, so it must carry the
   engineering rules (read before writing, minimal diffs, verify before claiming).
10. **Plugins and skills ship through marketplaces**, i.e. a git repo that must
    accept a push. Probe first: `POST /repos/{owner}/{repo}/git/blobs`. `403
    Resource not accessible by integration` means the token is read-only and no
    plugin can be published; install locally instead.
11. **Install a plugin into a running sandbox** at the runtime, not the account:
    `POST {AGENT_SERVER_URL}/api/plugins/install {"source": "/path/to/plugin"}`
    with header `X-Session-API-Key: <sandbox session key>`.
12. **Organization endpoints fail on personal workspaces** with
    `400 Organization budgets are not available for personal workspaces`.

## Working rules

- Read `status` first; it answers most questions in one call.
- Change one setting at a time and read it back to confirm.
- Back up before overwriting: copy the current persona/settings to a file whose
  name states what it is, and tell the operator where it is.
- When a request is physically impossible, say which layer blocks it, give the
  measurement, and name the change that would make it possible. Never ship a
  feature that reports numbers the kernel does not have.
