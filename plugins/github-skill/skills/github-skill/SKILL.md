---
name: github-skill
description: Operate GitHub from this workspace — authenticated git push, pull requests, issues, Actions — and add new skills to the oh-agent-skills marketplace. Use when a task touches a GitHub repo, branch, pull request, workflow, or when adding or editing a skill in this marketplace.
triggers:
- github
- gh
- git push
- pull request
---

# GitHub

## Pick a credential

Try in this order, and stop at the first one that has write access:

1. `$GITHUB_PAT` — a personal access token with `repo` (and `workflow`) scope.
2. `$GITHUB_TOKEN` — injected by the app. Often **read-only**; verify before relying on it.
3. `/var/openhands/.github-token` — mode-600 file, persistent for this runtime. Use `TOKEN=$(cat /var/openhands/.github-token)`.

Probe write access without changing anything:

```bash
git push --dry-run "https://x-access-token:$TOKEN@github.com/OWNER/REPO.git" HEAD:main
```

`Everything up-to-date` or a ref update line means writable. `403` / `denied` means read-only — fall through to the next source. `Resource not accessible by integration` means the credential is a GitHub App token, which cannot push or delete refs.

If no source has write access, ask the operator for a PAT. Never invent one, and never store a token in a file inside a git working tree.

## Push

Pass the token per command so it never lands in `.git/config`:

```bash
git push "https://x-access-token:$TOKEN@github.com/OWNER/REPO.git" HEAD:BRANCH
```

Then check `git remote -v`. If a token is embedded in the URL, fix it:

```bash
git remote set-url origin https://github.com/OWNER/REPO.git
```

## gh CLI

```bash
export GH_TOKEN="$TOKEN"
gh pr list --repo OWNER/REPO --state open
gh pr create --repo OWNER/REPO --base main --head BRANCH --title "..." --body "..."
```

`gh` reads `GH_TOKEN`, not `GITHUB_TOKEN`.

## Rules

- Never push to `main` directly unless the operator asks for it. Branch, then open a PR.
- Merge only when the operator explicitly asks.
- Never commit, echo, or paste a token. Conversation logs and repository history are both permanent.
- Any credential that appears in a transcript is compromised: rotate it, then store the new value in the secret store.
- When posting PR bodies, comments, or issues, open with one line stating an AI agent produced the content.

## Add a skill to this marketplace

Layout:

```
plugins/<plugin-name>/.claude-plugin/plugin.json    # name, displayName, version, description
plugins/<plugin-name>/skills/<skill-name>/SKILL.md  # frontmatter: name, description
```

Then register the plugin in `.claude-plugin/marketplace.json`:

```json
{ "name": "<plugin-name>", "source": "./plugins/<plugin-name>",
  "description": "...", "version": "1.0.0" }
```

Constraints:

- `<skill-name>` must be unique across every loaded marketplace. The public marketplace already ships `github`, `docker`, `kubernetes`, `slack`, and others — a duplicate name makes skill loading fail with `Duplicate skill name found`.
- The `name` in SKILL.md frontmatter must equal the directory name.
- Validate JSON before pushing: `python3 -m json.tool <file> > /dev/null`.
- Marketplaces are cloned when a workspace starts, so a merged change takes effect on the next workspace start, not immediately.

## Verify a push landed

```bash
gh api repos/OWNER/REPO/contents/PATH?ref=main --jq '.name'
```
