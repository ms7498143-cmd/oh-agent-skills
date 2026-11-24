# Verified endpoint reference

Base: `https://app.all-hands.dev`. Auth: `Authorization: Bearer $OPENHANDS_API_KEY`.

## Settings
| Endpoint | Notes |
|---|---|
| `GET /api/v1/settings` | whole account: `agent_settings`, `conversation_settings`, `disabled_skills`, `registered_marketplaces`, `llm_api_key_set`, `secrets_store` |
| `POST /api/v1/settings` | writes; nested need `agent_settings_diff` / `conversation_settings_diff` |
| `GET /api/v1/settings/agent-schema` | JSON schema of agent settings |
| `GET /api/v1/settings/conversation-schema` | schema; returns nulls for container_cpus/container_memory |
| `GET/POST /api/v1/settings/profiles[/{name}]` | save, rename, activate profiles |

Useful keys: `agent_settings.persona`, `agent_settings.llm.model`,
`conversation_settings.container_cpus`, `conversation_settings.container_memory`,
`conversation_settings.max_iterations`, `disabled_skills`,
`registered_marketplaces[] {name, source, ref, repo_path, auto_load, scope}`.

## Secrets
| Endpoint | Notes |
|---|---|
| `GET /api/v1/secrets/search?limit=N` | names, ids, scopes - never values |
| `POST /api/v1/secrets` | `{name, value, description?}`; injected into sandboxes by name |
| `PUT/DELETE /api/v1/secrets/{id}` | update or remove |
| `POST /api/v1/secrets/git-providers` | provider tokens |

## Sandboxes
| Endpoint | Notes |
|---|---|
| `POST /api/v1/sandboxes?sandbox_spec_id=<image>` | only parameter; no resources |
| `GET /api/v1/sandboxes/search?limit=N` | `status` RUNNING / MISSING, `exposed_urls`, `session_api_key` |
| `DELETE /api/v1/sandboxes/{id}` | terminates |
| `POST /api/v1/sandboxes/{id}/pause` / `resume` | resume 404s on a MISSING sandbox |
| `GET /api/v1/sandbox-specs/search` | read-only; image/command/env/working_dir only |

## Conversations
| Endpoint | Notes |
|---|---|
| `GET /api/v1/app-conversations/search?limit=N` | `sandbox_status` shows MISSING when the sandbox is gone |
| `POST /api/v1/app-conversations` | create from the GUI/API |
| `DELETE /api/v1/app-conversations/{id}` | delete |
| `GET /api/v1/app-conversations/{id}/download` | zip of the full trajectory; works even when the sandbox is MISSING |
| `POST /api/v1/app-conversations/{id}/send-message` | continue a conversation |
| `GET /api/v1/app-conversations/{id}/skills`, `/hooks` | what the conversation loaded |

## Billing (not under /api/v1)
| Endpoint | Notes |
|---|---|
| `GET /api/billing/credits` | `{"credits":"0.00"}` |
| `GET /api/billing/subscription-access` | null when none |
| `POST /api/billing/has-payment-method` | bare bool |
| `POST /api/billing/create-checkout-session {"amount":N}` | live Stripe URL; balance changes only after payment |
| `POST /api/billing/create-customer-setup-session` | save a card |
| `GET /api/billing/cancel` | cancel subscription |

## Sandbox runtime (inside a sandbox, port 60000)
| Endpoint | Notes |
|---|---|
| `GET /server_info` | version, tools, idle timeout |
| `GET /api/plugins/installed`, `POST /api/plugins/install {"source": path}` | local plugin install |
| `POST /api/conversations` | create with an explicit agent/LLM |
| `POST /api/conversations/{id}/bash/execute_bash_command {"command": ...}` | direct shell, no LLM turn |
| `GET /api/conversations/{id}/file/download` | pull a file |

Header: `X-Session-API-Key: <sandbox session_api_key>`.

## Known ceilings (measured, not assumed)
- Host: 4 vCPU (1 socket x 2 cores x 2 threads), 15.6 GB RAM, 25 GB `/workspace`, 59 GB free on `/`, 0 GPU, 0 NPU, no `/dev/kvm`.
- `container_cpus` / `container_memory` / `remote_runtime_resource_factor` are accepted but do not change what a sandbox reports.
- Credits cannot be granted by API; org budgets return 400 on personal workspaces.
