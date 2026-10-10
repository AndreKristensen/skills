---
name: setup-varlock
description: Set up Varlock with Doppler CLI for environment variable management in a project. Use when the user asks to "add varlock", "set up varlock", "add doppler", "set up environment variables with varlock", "secure my env vars", or "add secrets management". Works with Next.js, Vite, Astro, or any Node.js project.
argument-hint: "[framework]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, WebFetch, Agent]
---

# Set Up Varlock + Doppler CLI

Add schema-validated environment variable management with zero secrets on disk using Varlock and the Doppler CLI.

## Overview

This skill configures:
- **Varlock** for schema validation, type generation, and sensitivity control
- **Doppler CLI** via `exec()` for local secret resolution (browser-based auth, no tokens on disk)
- **Doppler Vercel/platform sync** for production (env vars injected directly, `exec()` skipped)

## Prerequisites

Before running, confirm:
1. Node.js >= 22
2. The project uses a supported package manager (npm, pnpm, yarn, bun)
3. The user has a Doppler account and project set up
4. The Doppler CLI is installed (`doppler --version`). If not, install it:
   - macOS: `brew install dopplerhq/cli/doppler`
   - Linux (no sudo): `curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh | sh -s -- --install-path $HOME/bin`
   - Linux (sudo): See https://docs.doppler.com/docs/install-cli

## Steps

### Step 1 — Detect the project

Read `package.json` to determine:
- Package manager (check `packageManager` field, or presence of `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`)
- Framework (Next.js, Vite, Astro, or plain Node.js — check dependencies)
- Existing `.env` files (scan for `.env`, `.env.local`, `.env.example`, etc.)
- Existing env var usage (grep for `process.env` across the codebase)

Ask the user for:
- Their **Doppler project name** (e.g., `my-app`)
- Their **Doppler config name** (e.g., `dev`)

### Step 2 — Install packages

Install Varlock core. For framework-specific integrations, install the appropriate package:

| Framework | Packages |
|-----------|----------|
| Next.js   | `varlock @varlock/nextjs-integration` |
| Vite      | `varlock @varlock/vite-integration` |
| Astro     | `varlock @varlock/astro-integration` |
| Other     | `varlock` |

### Step 3 — Configure the framework integration

#### Next.js

1. Add the `@next/env` override based on the package manager:

   **pnpm v10+** (`pnpm-workspace.yaml`):
   ```yaml
   overrides:
     "@next/env": "npm:@varlock/nextjs-integration"
   ```

   **pnpm v9** (`package.json`):
   ```json
   { "pnpm": { "overrides": { "@next/env": "npm:@varlock/nextjs-integration" } } }
   ```

   **npm** (`package.json`):
   ```json
   { "overrides": { "next": { "@next/env": "npm:@varlock/nextjs-integration" } } }
   ```

   **yarn** (`package.json`):
   ```json
   { "resolutions": { "**/@next/env": "npm:@varlock/nextjs-integration" } }
   ```

   **bun** (`package.json`):
   ```json
   { "overrides": { "@next/env": "npm:@varlock/nextjs-integration" } }
   ```

2. Reinstall dependencies to apply the override.

3. Update `next.config.ts` (or `.js`/`.mjs`):
   - Add `import { varlockNextConfigPlugin } from '@varlock/nextjs-integration/plugin'`
   - Wrap the export: `export default varlockNextConfigPlugin()(nextConfig)`
   - Convert from `module.exports` to `export default` if needed

#### Vite / Astro

Follow the integration docs at https://varlock.dev/integrations/vite/ or https://varlock.dev/integrations/astro/

### Step 4 — Generate the `.env.schema`

Build the schema file at the project root. For each env var found in the codebase:

```
# @defaultSensitive=inferFromPrefix('NEXT_PUBLIC_')
# @generateTypes(lang=ts, path=env.d.ts)
# ----------

# Description of the variable
# @required (or @optional)
# @sensitive (if not inferred from prefix)
VAR_NAME=exec(`doppler secrets get VAR_NAME --plain -p <project> -c <config>`)
```

Rules:
- Every variable gets an `exec()` call pointing to the Doppler CLI
- Use `@sensitive` for server-only secrets (or rely on `inferFromPrefix` for Next.js `NEXT_PUBLIC_` convention)
- Use `@required` for variables the app cannot start without
- Use `@optional` for variables that have fallbacks or are only used in specific features
- Use `@type=url` for URL variables
- Add a short description comment above each variable
- Group variables by service/feature with section headers

### Step 5 — Update TypeScript config

Add `env.d.ts` to `tsconfig.json` `include` array:
```json
{ "include": ["env.d.ts", ...existing] }
```

Add `env.d.ts` to `.gitignore`.

### Step 6 — Update scripts that need env vars

For CLI tools that run outside the framework (e.g., Sanity CLI, database migrations), prefix them with `varlock run --`:

```json
{
  "scripts": {
    "db:migrate": "varlock run -- prisma migrate deploy",
    "sanity:schema": "varlock run -- sanity schema extract"
  }
}
```

### Step 7 — Clean up

- Empty the `.env` file (remove all secrets — they now come from Doppler)
- Keep `.env` in `.gitignore`
- Commit `.env.schema` to version control (it contains no secrets)
- Remove any `.env.example` files (the schema replaces them)

### Step 8 — Verify

Run `varlock load` (or `pnpm exec varlock load`) to confirm all variables resolve correctly.

If the user hasn't run `doppler login` yet, remind them to do so.

### Step 9 — Production setup guidance

Tell the user:

> For production (Vercel, Netlify, etc.), set up Doppler's native integration to sync secrets directly as platform env vars. When values are already in the environment, Varlock skips the `exec()` calls — the Doppler CLI doesn't need to be installed on the platform.
>
> 1. In Doppler dashboard: Integrations > [Your Platform] > Connect
> 2. Map your Doppler project configs to platform environments
> 3. Deploy — Varlock validates the synced values automatically

## Edge Cases

| Situation | Action |
|-----------|--------|
| Doppler CLI not installed | Show install command for their OS |
| User not logged into Doppler | Remind them to run `doppler login` |
| Monorepo | Override must be in the root package.json/workspace config |
| pnpm v9 vs v10 | v10 uses `pnpm-workspace.yaml` for overrides, v9 uses `package.json` |
| next.config uses CommonJS | Convert `module.exports` to `export default` |
| Existing env validation (Zod, t3-env) | Note it can be removed — Varlock replaces it |
| Variables not in Doppler yet | Remind user to add them to their Doppler project first |

## Output

When complete, summarise:
- Number of environment variables configured
- Which are required vs optional
- Which are sensitive
- Reminder to run `doppler login` if not yet authenticated
- Link to the Doppler dashboard for their project
- Reminder to set up platform sync for production
