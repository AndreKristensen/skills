# Sandcastle failure signatures

Failures walk outward through the pipeline: container start → dependency install → prompt preprocessing → agent auth → agent work → merge. A run that fails later than the last one is progress, not a new problem.

Two habits before diagnosing anything:

- **Read the log, not the exit code.** `cmd | tail -5` reports `tail`'s status, so a failure reads as success. Use `cmd > run.log 2>&1; echo "EXIT=$?"`.
- **Sandcastle's own error output often omits the underlying tool's stderr.** When a hook fails, reproduce the command directly in the container against the preserved worktree — that is usually the only way to see the real message:

```bash
docker run --rm -v "$PWD/.sandcastle/worktrees/<name>:/home/agent/workspace" \
  -w /home/agent/workspace --entrypoint sh <image> -c 'pnpm install --frozen-lockfile 2>&1 | tail -20'
```

---

## `permission denied while trying to connect to the docker API`

The user is not in the `docker` group, **or** is in it but the process tree predates the change.

```bash
getent group docker   # system truth
id -nG                # what this process sees
```

If the first lists the user and the second doesn't, the configuration is correct and only the session is stale — group lists are fixed at login and never refresh. A new terminal inherits the stale list from the same stale parent, so it appears to change nothing. Requires a full logout/login or reboot. `newgrp docker` works for a single interactive shell, but is absent on some systems (as is `sg`).

Restarting the Docker *service* does not help — this is a client-side credential problem, not a daemon one.

---

## `! Corepack is about to download …` then exit 1

Corepack blocking on an interactive confirmation. It fetches the exact version pinned in `packageManager` at runtime, and the sandbox has no TTY to answer.

Fix: `ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0` in the Dockerfile.

---

## `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`

pnpm wants to purge a `node_modules` it considers foreign and stops to ask. Usually triggered by `copyToWorktree: ["node_modules"]` copying in a tree whose recorded store path does not exist inside the container.

Fix: `ENV CI=true` in the Dockerfile.

Worth telling the user: because pnpm discards and reinstalls the copy anyway, `copyToWorktree` is buying nothing here — it pays a large file copy *and* a full install every run. Dropping it is strictly faster for pnpm projects.

---

## `ERR_PNPM_UNEXPECTED_STORE`

The `node_modules` was linked from a different store than the current pnpm wants. Common when a project has been installed by an IDE-bundled package manager (a snap or flatpak path) and later by one on `PATH`.

On the host, install against the existing store rather than forcing a full reinstall:

```bash
pnpm install --store-dir /path/from/the/error/message
```

Inside the container this manifests as the modules-purge prompt above.

---

## `gh: To use GitHub CLI in automation, set the GH_TOKEN environment variable`

`GH_TOKEN` is not reaching the sandbox. Host `gh` auth is typically keyring-based and does not exist in the container.

Fix: forward it explicitly — `sandbox: docker({ env: { GH_TOKEN: process.env.GH_TOKEN ?? "" } })`. See `secrets.md`.

---

## `claude-code exited with code 1: Not logged in · Please run /login`

The Claude credential is not reaching the container. Expected when there is no `.sandcastle/.env` for sandcastle to auto-resolve from (the varlock/vault setup).

Fix: forward it on the agent provider — `claudeCode(model, { env: { CLAUDE_CODE_OAUTH_TOKEN: … } })`. See `secrets.md`.

---

## `PromptError: Command … exited with code N`

A `!`-prefixed line in `prompt.md` failed inside the sandbox. The embedded command runs in the container, so it needs whatever auth and tooling that implies. The error quotes the command — run it manually in the container to see the real stderr.

Note that `gh issue list --label <missing-label>` is *not* an error: it returns `[]` with exit 0. A missing label yields an empty queue, not a crash.

---

## Run succeeds but reports "worktree has uncommitted changes"

Usually a package-manager store directory created in the worktree (`.pnpm-store/`). Harmless, but it recurs every run and an agent may eventually commit it. Add it to the repo's root `.gitignore`.

Confirm it is only that before dismissing it:

```bash
git -C .sandcastle/worktrees/<name> status --porcelain
git -C .sandcastle/worktrees/<name> diff --stat
```

---

## Dependency install fails on a supply-chain policy

Repos with `minimumReleaseAge`, `preferFrozenLockfile`, or similar policies can reject an install that would otherwise be fine — including one triggered by adding sandcastle itself.

Do not bypass the policy to unblock setup; it exists for a reason and is the user's decision. Diagnose honestly first: `git diff pnpm-lock.yaml` distinguishes "my change caused this" from "the committed lockfile already violates the policy" — the latter is a timing collision that resolves itself as packages age, and no flag will change it.

Note that pinning older versions via `pnpm.overrides` in `package.json` does nothing on pnpm 10+ — that field is no longer read (it emits a warning that is easy to miss), and it cannot address transitive dependencies anyway.

---

## Agent runs but does nothing

Check the queue first — an empty issue list is the intended no-op, and the log will say so explicitly with a completion signal. If work *was* expected, verify the label exists and is applied:

```bash
gh label list
gh issue list --state open --label ready-for-agent
```

---

## Agent commits code that fails to build

Check what the prompt's verification step actually asks for. The scaffolded template requires `npm run typecheck` and `npm run test`; if those scripts don't exist, verification silently accomplishes nothing.

Also suspect `CI=true` if the failure is lint-strictness related — some build tools (notably `next build`) are stricter under it than in a local run.
