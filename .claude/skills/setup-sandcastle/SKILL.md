---
name: setup-sandcastle
description: Set up the @ai-hero/sandcastle autonomous coding-agent loop in a repository — scaffolding, container image, secret forwarding, and a safe first run. Use this whenever the user mentions sandcastle, wants an agent to work through GitHub issues unattended, asks about `sandcastle init`, an overnight/AFK agent loop, or a RALPH-style issue-driven agent. Also use it when an existing sandcastle run is failing — a container that hangs on a prompt, "Not logged in", or `gh` auth errors from inside the sandbox. It covers the runtime failures sandcastle's own docs do not mention.
---

# Setting up Sandcastle

[Sandcastle](https://github.com/mattpocock/sandcastle) runs a coding agent inside a container against a git worktree, then merges its commits back. `sandcastle init` scaffolds a working setup in about a minute.

The gap this skill fills is what happens *after* that minute. The scaffold is a generic template: it assumes npm, a Node 22 image, and test scripts that probably don't exist in the target repo. And its secret handling has a sharp edge — sandcastle auto-resolves only the variables its **agent provider** requires, so anything else the agent needs (notably a GitHub token) silently never reaches the container.

These failures share a shape: **they all surface at runtime, several minutes into a run, with errors that name neither the variable nor the cause.** A container that hangs on an invisible confirmation prompt looks identical to a slow install. Working through the steps below in order surfaces each one cheaply instead.

## Before starting

Confirm three things about the environment. Each has bitten a real setup.

**Docker (or Podman) reachable by the current user.** Run `docker ps`. On `permission denied … /var/run/docker.sock`, the user must add themselves to the `docker` group themselves — it's a system permission change:

```bash
sudo usermod -aG docker $USER
```

Then the trap: **`usermod` does not affect any process that is already running.** The kernel fixes a process's group list at login, so the current shell, its parent, and the editor or agent session that spawned them all keep the old list. A *new* shell inherits the stale list from that same stale parent, so opening a terminal appears to do nothing. Diagnose it by comparing:

```bash
getent group docker   # system truth: is the user listed?
id -nG                # this process: does it see the group?
```

If the first shows the user and the second doesn't, the config is right and only the session is stale. The fix is a full logout/login or reboot — `newgrp docker` works for one interactive shell if available, but many systems lack it. Note this also means `docker` group membership is roughly root-equivalent on the host; if the user objects, rootless Docker or Podman are the alternatives (Podman is a one-line swap in `main.mts`).

**Node and the package manager.** Note the repo's Node version and whether `packageManager` is pinned in `package.json`. Both drive the image.

**Which verification commands actually exist.** Read the `scripts` block. The scaffolded prompt tells the agent to run `npm run typecheck` and `npm run test`; if those aren't there, the agent will fail verification on every issue.

## 1. Install and scaffold

```bash
npm install --save-dev @ai-hero/sandcastle   # or pnpm add -D / yarn add -D
```

`init` is interactive by default, but every prompt has a flag. Pass them all so it doesn't block:

```bash
npx @ai-hero/sandcastle init \
  --template simple-loop \
  --agent claude-code \
  --model claude-opus-4-8 \
  --sandbox docker \
  --issue-tracker github-issues \
  --create-label false \
  --build-image false \
  --install-template-deps false
```

Choices worth understanding rather than copying:

- `--template` — `simple-loop` (one issue per iteration) is the right start. `sequential-reviewer` adds a review gate and the `parallel-planner` variants fan out; both add moving parts before anything is known to work.
- `--create-label false` — if the repo already has a triage vocabulary, reuse it rather than letting sandcastle create a second overlapping set. If it has none, create one deliberately (see step 8).
- `--build-image false` — the Dockerfile needs editing first; building now just means building twice.
- `--install-template-deps false` — avoids a second dependency resolution, which matters in repos with supply-chain policies (release-age gates, lockfile freezing) that can reject an unexpected install.

This writes `.sandcastle/`: `Dockerfile`, `main.mts`, `prompt.md`, `.env.example`, `.gitignore`.

## 2. Match the image to the project

The scaffolded Dockerfile is Node 22 with npm. Two things usually need changing, and one always does.

**Node version and package manager.** If the repo pins pnpm or yarn via `packageManager`, enable corepack so the pinned version is available:

```dockerfile
FROM node:24-bookworm    # match the project

RUN corepack enable
```

**Headless prompts — this one always applies.** A sandbox has no TTY, so any tool that stops to ask a question hangs or dies, and the surfacing error rarely mentions a prompt. Two are near-certain with corepack + pnpm:

```dockerfile
# corepack fetches the exact version pinned in packageManager at runtime and
# blocks on a confirmation that nothing can answer.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

# pnpm asks before purging a node_modules it considers foreign — which it will,
# whenever copyToWorktree copies one in from a host whose store path doesn't
# exist inside the container.
ENV CI=true
```

`CI=true` is semantically honest for an unattended sandbox and heads off other interactive prompts too. It isn't free: some tools change behaviour under it — `next build` treats lint warnings more strictly, and some test runners disable watch mode. If the agent's verification starts failing on something that passes locally, suspect this first.

Prefer environment variables over hardcoding a version (`corepack prepare pnpm@1.2.3`), so the image can't drift from `packageManager`.

## 3. Wire the secrets

**Read `references/secrets.md` before writing any of this.** It has the forwarding table, both storage options (plain `.sandcastle/.env` vs varlock/Doppler with no secrets on disk), and the exact `env` syntax per provider.

The one-line version, because it's the single most likely thing to go wrong: **sandcastle auto-resolves only what the agent provider needs. Everything else must be forwarded explicitly in `main.mts`.** A GitHub token that exists, is valid, and is loaded on the host will still not reach the container unless it's passed to the sandbox provider.

## 4. Adapt the prompt

`.sandcastle/prompt.md` is the agent's standing contract, layered under each issue. Three edits usually matter.

**The work queue.** The template lists all open issues. If work is gated behind a label, filter on it — a `!`-prefixed line runs inside the sandbox at the start of each iteration:

```markdown
!`gh issue list --state open --label ready-for-agent --limit 100 --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`
```

A missing label is not an error — `gh` returns `[]` with exit 0 — so the loop degrades into a clean no-op rather than crashing. That's what makes the smoke test in step 7 safe.

**The verification step.** Replace the template's `npm run typecheck` / `npm run test` with commands that exist. Requiring a test run in a repo with no test runner guarantees failure; conversely, dropping verification entirely lets the agent commit code that doesn't build. Use whatever the repo actually has — `pnpm lint` and `pnpm build` if that's it — and say plainly that both must pass before committing.

**Project-specific rules.** If the repo has an `AGENTS.md` or `CLAUDE.md` with load-bearing constraints, restate the critical ones in the prompt rather than assuming the agent reads them. A rule like "this framework version differs from your training data — read the local docs first" is exactly the kind of thing that produces confidently wrong code when skipped.

## 5. Ignore the sandbox's droppings

Runs leave artifacts in the worktree. `.sandcastle/.gitignore` covers `.env`, `logs/`, and `worktrees/`, but the package manager may create a store directory in the worktree root — with pnpm it's `.pnpm-store/`. Add it to the repo's root `.gitignore`:

```gitignore
.pnpm-store/
```

Without this, every run reports phantom uncommitted changes, and an agent may eventually commit the store.

**Check for an over-broad `.env*` rule while in there.** Many templates (Next.js among them) ignore `.env*`, which silently swallows a committed schema file like `.env.schema`. `git check-ignore` returns 0 for a *negation* match too, so its exit code can't distinguish "ignored" from "explicitly un-ignored" — verify with `git status --porcelain --untracked-files=all | grep env.schema` instead.

## 6. Build and verify the image

```bash
npx @ai-hero/sandcastle docker build-image
```

Then confirm the customisations actually landed, rather than trusting the build succeeded:

```bash
docker run --rm --entrypoint sh <image> -c \
  'node --version; pnpm --version; git --version; gh --version | head -1; claude --version; id -un'
```

Check the package manager resolves, and that the container user's uid/gid match the host user — a mismatch means bind-mounted files come out owned by the wrong user.

## 7. Smoke-test on an empty queue

Before letting an agent touch real work, run the loop with **nothing** for it to pick up — no issues carrying the queue label. The agent starts, queries the tracker, finds an empty list, and completes. That exercises container start, dependency install, tracker auth, agent auth, and prompt handling, while making unwanted commits structurally impossible.

```bash
npm run sandcastle   # or the script init told you to add
```

A pass looks like this in `.sandcastle/logs/…-worker.log`:

```
Iteration 1/3
  gh issue list … → ~1 tokens
Agent started
There are no open issues ready for work …
<promise>COMPLETE</promise>
Agent signaled completion after 1 iteration(s).
```

Expect to go around this loop a few times. Each failure is normally one layer deeper than the last, which is the point — it's far cheaper to discover them here than mid-run against real code. `references/troubleshooting.md` maps the common failure signatures to fixes; read it when a run fails rather than guessing.

**Check the log, not the exit code.** Sandcastle preserves the worktree on failure and prints a cleanup command; a stale worktree accumulates per failed run, so remove it between attempts:

```bash
git worktree remove --force .sandcastle/worktrees/<name>
git branch -D sandcastle/worker/<name>
```

## 8. First real run

Three things to settle before an agent produces changes:

- **The queue label must exist.** If the prompt filters on `ready-for-agent`, create it (`gh label create ready-for-agent`) along with any sibling triage labels — otherwise nothing can ever enter the queue.
- **Commit outstanding work.** `merge-to-head` merges the agent's temp branch into HEAD; a clean base means any conflict is the agent's doing and the diff is readable.
- **Cap the first run.** Set `maxIterations: 1` in `main.mts` so a debut that goes sideways yields one commit to inspect rather than three to unpick.

Then label one small, well-scoped issue and run it.

## Verifying anything in this workflow

Two habits, both learned the hard way:

**A pipeline's exit code is the last command's.** `some-command | tail -5` reports `tail`'s status, so a failed build reads as success. Redirect to a file and check the status separately:

```bash
some-command > run.log 2>&1; echo "EXIT=$?"
```

**Confirm the state you actually care about.** After a build, check the image exists and contains what you expect. After a run, check `git log` and `git status` — sandcastle's `merge-to-head` should leave HEAD untouched on failure, and confirming that is what tells you the isolation is working.

## Reference files

- `references/secrets.md` — the forwarding table, `.env` vs varlock/Doppler, exact `env` syntax, and which quota the Claude token draws on. **Read before step 3.**
- `references/troubleshooting.md` — failure signatures mapped to causes and fixes. Read when a run fails.
