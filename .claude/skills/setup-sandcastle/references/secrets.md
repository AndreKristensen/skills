# Secrets and sandcastle

## The rule that catches everyone

Sandcastle resolves environment variables automatically from `.sandcastle/.env` and the host `process.env` — but **only the variables the configured agent provider itself requires.** For `claudeCode` that means the Claude credential and nothing else.

Anything else the agent needs inside the container — a GitHub token above all — must be forwarded **explicitly** in `.sandcastle/main.mts`. A token that exists, is valid, and is present in the host environment will still not reach the sandbox without a forwarding line.

The failure mode is unpleasant: it appears minutes into a run, and the error names neither the variable nor the reason.

| Symptom in the log | Missing variable | Where it goes |
|---|---|---|
| `gh: To use GitHub CLI in automation, set the GH_TOKEN environment variable` | `GH_TOKEN` | sandbox provider `env` |
| `claude-code exited with code 1: Not logged in · Please run /login` | `CLAUDE_CODE_OAUTH_TOKEN` (or `ANTHROPIC_API_KEY`) | agent provider `env` |

Host `gh` auth does **not** carry over. It usually lives in a system keyring, which does not exist in the container — so a host that is happily authenticated tells you nothing about the sandbox.

## Forwarding syntax

Both provider factories take an optional `env: Record<string, string>`:

```ts
import { run, claudeCode } from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";

await run({
  agent: claudeCode("claude-opus-4-8", {
    env: {
      CLAUDE_CODE_OAUTH_TOKEN: process.env.CLAUDE_CODE_OAUTH_TOKEN ?? "",
    },
  }),
  sandbox: docker({
    env: { GH_TOKEN: process.env.GH_TOKEN ?? "" },
  }),
  promptFile: "./.sandcastle/prompt.md",
  branchStrategy: { type: "merge-to-head" },
});
```

Provider `env` overrides `.sandcastle/.env` for shared keys. Add a forwarding line for every new secret — declaring it in a schema or storing it in a vault is not enough on its own.

## Where the secrets live: two options

### Option A — `.sandcastle/.env` (simple, default)

Copy `.env.example` to `.env` and fill it in. `.sandcastle/.gitignore` already ignores `.env`.

Good when: a solo project, or the team is fine with plaintext credentials at rest on developer machines.

With this option sandcastle resolves the agent credential from the file automatically, so only the *extra* variables (`GH_TOKEN`) need forwarding.

### Option B — varlock + a secrets manager (no secrets on disk)

Secrets are declared in a committed `.env.schema` and resolved on demand from a vault (Doppler, 1Password, etc.). No `.env` file exists anywhere.

```bash
npm install --save-dev varlock
```

`.env.schema` — commit this; it contains no secrets, only their shape and the lookup:

```bash
# @defaultSensitive=true
# ---

# Claude Code OAuth token — generate with `claude setup-token`.
# @required @sensitive
CLAUDE_CODE_OAUTH_TOKEN=exec('doppler secrets get CLAUDE_CODE_OAUTH_TOKEN --plain -p <project> -c <config>')

# GitHub token the agent uses to read and close issues.
# @required @sensitive
GH_TOKEN=exec('doppler secrets get GH_TOKEN --plain -p <project> -c <config>')
```

Then run the loop through varlock so the resolved values land in `process.env`:

```json
{ "scripts": { "sandcastle": "varlock run -- npx tsx .sandcastle/main.mts" } }
```

Verify resolution independently before running the loop — `varlock load` prints each variable with sensitive values masked, and fails closed if the vault is unreachable.

**The cost of this option, stated plainly:** with no `.sandcastle/.env`, sandcastle has nothing to auto-resolve, so **every** secret needs a forwarding line — including the agent credential that Option A gets for free. This is exactly the trap in the table above, and it is invisible until runtime.

Two things to check when adopting it:

- An over-broad `.env*` rule in `.gitignore` will silently swallow `.env.schema`, which is meant to be committed. Add `!.env.schema` and verify with `git status`, not `git check-ignore` (which returns 0 for negation matches too).
- Skip framework integrations and type generation unless something actually consumes the variables in typed code. Sandcastle reads them from `process.env` at runtime, so generated types have no consumer.

## What the agent can see

Worth being explicit with the user: **either option puts real credentials inside the container**, where the autonomous agent can read them from its own environment. Vaulting changes where secrets live at rest on the host; it does not isolate them from the agent.

The practical mitigation is scope. A fine-grained GitHub PAT limited to the one repo with Issues (read/write) and Metadata (read) is enough for the issue loop, and bounds the blast radius if the agent misbehaves.

`varlock proxy --sandbox=docker` is the real fix — the agent receives placeholders while a host-side proxy injects credentials into outbound requests and keeps an audit log. It is meaningfully more work to wire to a container sandcastle already orchestrates (mounting a CA, setting `HTTPS_PROXY` / `NODE_EXTRA_CA_CERTS`), so treat it as a deliberate follow-up once the loop is trusted rather than part of initial setup. Letting `varlock proxy` run the agent in *its own* sandbox is the wrong shape — it duplicates the containerisation and worktree management sandcastle exists to provide.

## Which quota the Claude token draws on

`claude setup-token` mints an OAuth token backed by the user's Claude subscription (Pro, Max, Team, Enterprise), so runs use included subscription usage rather than metered API billing.

The part worth flagging: that allowance is **shared**. Agent runs draw on the same rolling five-hour and weekly windows as the user's own interactive Claude Code and claude.ai usage, across all surfaces. An unattended overnight loop can consume the quota needed for interactive work the next morning. Past the allowance, runs stop — or, with usage credits enabled, spill into metered spend.

`maxIterations` in `main.mts` is the throttle, and a cheaper model for routine issues stretches the same allowance considerably further.

Do not mount the host's `~/.claude/` credentials into the container as a shortcut. Those are refreshing session credentials: the container would need write access to renew them, a stale copy breaks mid-run, and it hands the agent the user's entire Claude session instead of one purpose-minted, individually revocable token.
