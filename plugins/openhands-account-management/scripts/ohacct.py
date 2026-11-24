#!/usr/bin/env python3
"""Account-level OpenHands management.

Reads OPENHANDS_API_KEY. Writes settings, persona, skills, secrets and manages
sandboxes, conversations and billing. Every write path here is verified against
app.all-hands.dev; see SKILL.md for the traps.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("OPENHANDS_API_BASE", "https://app.all-hands.dev").rstrip("/")


def url(path):
    return BASE + path if path.startswith("/api/") else BASE + "/api/v1" + path


def req(method, path, body=None, timeout=120):
    key = os.environ.get("OPENHANDS_API_KEY")
    if not key:
        sys.exit("OPENHANDS_API_KEY is not set")
    r = urllib.request.Request(
        url(path), method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def download(path, dest):
    key = os.environ["OPENHANDS_API_KEY"]
    r = urllib.request.Request(url(path), headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(r, timeout=300) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    return os.path.getsize(dest)


def settings():
    return req("GET", "/settings")


def run(a):
    if a.command == "status":
        s = settings()
        agent = s.get("agent_settings", {})
        persona = agent.get("persona") or ""
        sandboxes = req("GET", "/sandboxes/search?limit=50").get("items", [])
        convs = req("GET", "/app-conversations/search?limit=100").get("items", [])
        print(json.dumps({
            "email": s.get("email"),
            "llm": (agent.get("llm") or {}).get("model"),
            "llm_key_set": s.get("llm_api_key_set"),
            "persona_chars": len(persona),
            "disabled_skills": s.get("disabled_skills"),
            "marketplaces": [m.get("name") for m in (s.get("registered_marketplaces") or [])],
            "container_cpus": s["conversation_settings"].get("container_cpus"),
            "container_memory": s["conversation_settings"].get("container_memory"),
            "credits": req("GET", "/api/billing/credits").get("credits"),
            "sandboxes": {st: sum(1 for x in sandboxes if x.get("status") == st)
                          for st in {x.get("status") for x in sandboxes}},
            "conversations": len(convs),
        }, indent=2))

    elif a.command == "settings-show":
        s = settings()
        print(json.dumps(s if not a.key else s.get(a.key), indent=2))

    elif a.command == "persona-get":
        print((settings().get("agent_settings", {}).get("persona") or ""))

    elif a.command == "persona-set":
        text = open(a.file).read()
        print(req("POST", "/settings", {"agent_settings_diff": {"persona": text}}))
        print("chars:", len(text))

    elif a.command in ("skill-disable", "skill-enable"):
        s = settings()
        names = set(s.get("disabled_skills") or [])
        names.add(a.name) if a.command == "skill-disable" else names.discard(a.name)
        print(req("POST", "/settings", {"disabled_skills": sorted(names)}))

    elif a.command == "marketplaces":
        for m in settings().get("registered_marketplaces") or []:
            print(f"{m.get('name'):28} {m.get('source')}  auto_load={m.get('auto_load')} scope={m.get('scope')}")

    elif a.command == "secrets":
        for x in req("GET", "/secrets/search?limit=100").get("items", []):
            print(f"{x.get('name'):32} scope={x.get('scope')} id={x.get('id')}")

    elif a.command == "secret-set":
        value = a.value or sys.stdin.read().strip()
        print(req("POST", "/secrets", {"name": a.name, "description": a.description, "value": value}))

    elif a.command == "secret-delete":
        print(req("DELETE", f"/secrets/{a.id}"))

    elif a.command == "sandboxes":
        for x in req("GET", "/sandboxes/search?limit=50").get("items", []):
            print(f"{x.get('id')} {x.get('status'):10} {x.get('created_at')} {x.get('sandbox_spec_id')}")

    elif a.command == "sandbox-create":
        spec = a.spec or next(iter(req("GET", "/sandbox-specs/search?limit=5").get("items", [])), {}).get("id")
        print(json.dumps(req("POST", "/sandboxes?sandbox_spec_id=" + urllib.parse.quote(spec, safe=""))))

    elif a.command == "sandbox-delete":
        print(req("DELETE", f"/sandboxes/{a.id}"))

    elif a.command == "conversations":
        for x in req("GET", f"/app-conversations/search?limit={a.limit}").get("items", []):
            print(f"{x.get('id')} {x.get('created_at')} {x.get('sandbox_status')} {str(x.get('title'))[:60]}")

    elif a.command == "conversation-delete":
        print(req("DELETE", f"/app-conversations/{a.id}"))

    elif a.command == "conversation-download":
        print("bytes:", download(f"/app-conversations/{a.id}/download", a.dest))

    elif a.command == "billing":
        print(json.dumps({
            "credits": req("GET", "/api/billing/credits").get("credits"),
            "payment_method": req("POST", "/api/billing/has-payment-method", {}),
            "subscription": req("GET", "/api/billing/subscription-access"),
        }, indent=2))

    elif a.command == "topup":
        print(req("POST", "/api/billing/create-checkout-session", {"amount": a.amount})["redirect_url"])

    elif a.command == "container-resources":
        print(req("POST", "/settings", {"conversation_settings_diff": {
            "container_cpus": a.cpus, "container_memory": a.memory}}))
        print("note: inert on app.all-hands.dev - measured, see SKILL.md")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, **kw):
        sp = sub.add_parser(name, **kw)
        return sp

    add("status", help="one-screen account summary")
    sp = add("settings-show", help="raw settings or one top-level key")
    sp.add_argument("key", nargs="?")
    add("persona-get", help="print the account persona")
    sp = add("persona-set", help="apply a persona file") ; sp.add_argument("file")
    sp = add("skill-disable", help="disable a skill by name"); sp.add_argument("name")
    sp = add("skill-enable", help="re-enable a skill by name"); sp.add_argument("name")
    add("marketplaces", help="list registered marketplaces")
    add("secrets", help="list secret names")
    sp = add("secret-set"); sp.add_argument("name"); sp.add_argument("value", nargs="?")
    sp.add_argument("--description")
    sp = add("secret-delete"); sp.add_argument("id")
    add("sandboxes", help="list sandboxes")
    sp = add("sandbox-create"); sp.add_argument("--spec")
    sp = add("sandbox-delete"); sp.add_argument("id")
    sp = add("conversations"); sp.add_argument("--limit", type=int, default=25)
    sp = add("conversation-delete"); sp.add_argument("id")
    sp = add("conversation-download"); sp.add_argument("id"); sp.add_argument("dest")
    add("billing", help="credits, card, subscription")
    sp = add("topup"); sp.add_argument("amount", type=int)
    sp = add("container-resources", help="set per-conversation container cpu/memory")
    sp.add_argument("cpus", type=float); sp.add_argument("memory")

    a = p.parse_args()
    run(a)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:400]}")
