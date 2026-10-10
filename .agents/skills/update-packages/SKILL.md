---
name: update-packages
description: >
  Check for outdated npm packages with pnpm, show changelogs for the selected
  packages, and run the update. Use when the user says "update packages",
  "check for updates", "pnpm outdated", "upgrade dependencies",
  "what packages are outdated", or "update my npm packages".
argument-hint: "[patch|minor|major]"
---

# Update Packages with pnpm

Detect outdated packages, show changelogs for the ones the user wants to update, then run the update.

## Step 1 — Check for outdated packages

Run:

```bash
pnpm outdated --json 2>&1
```

Parse the JSON. If the result is empty or `{}`, tell the user all packages are up to date and stop.

The JSON shape is:

```json
{
  "package-name": {
    "current": "1.2.3",
    "wanted":  "1.2.5",
    "latest":  "2.0.0",
    "dependencyType": "dependencies" | "devDependencies",
    "isDeprecated": false
  }
}
```

## Step 2 — Categorise by semver bump type

For each package, compare `current` → `latest`:

| Type | Condition |
|------|-----------|
| **major** | different major version number |
| **minor** | same major, different minor |
| **patch** | same major.minor, different patch |

Display a grouped summary before asking any question:

```
MAJOR (N packages)
  package-name      1.0.0 → 2.0.0   [dependencies]

MINOR (N packages)
  package-name      1.0.0 → 1.5.0   [devDependencies]

PATCH (N packages)
  package-name      1.0.0 → 1.0.3   [dependencies]
```

Mark deprecated packages clearly with `[DEPRECATED]`.

## Step 3 — Ask the user what to update

Use `AskUserQuestion` with these options:

- **Patch only** — bug fixes, safest
- **Patch + Minor** — new features, backward-compatible
- **Everything (Patch + Minor + Major)** — includes breaking changes
- **Let me pick** — user types specific package names

If the user picks "Let me pick", ask a follow-up question listing all outdated package names so they can select exactly which ones to update (use `multiSelect: true`).

If an argument was passed to the skill (e.g. `/update-packages minor`), skip the question and use it directly.

## Step 4 — Fetch changelogs (in parallel)

For each package that falls within the chosen update scope, fetch its changelog. Run all fetches in parallel using multiple `WebFetch` calls in a single response.

### Finding the changelog source

**a) npm registry → GitHub repo**

```
GET https://registry.npmjs.org/{package-name}
```

Extract `.repository.url`. Strip the `git+` prefix and `.git` suffix to get the GitHub URL:
`git+https://github.com/owner/repo.git` → `https://github.com/owner/repo`

**b) GitHub Releases API (preferred)**

```
GET https://api.github.com/repos/{owner}/{repo}/releases?per_page=30
```

Filter to releases whose tag version is `> current` and `<= latest`. Show only the relevant release notes, not the entire history.

**c) Fallback — raw CHANGELOG.md**

If the Releases API returns no useful entries, try:

```
GET https://raw.githubusercontent.com/{owner}/{repo}/HEAD/CHANGELOG.md
```

Extract version sections between `current` and `latest` using heading matching (e.g. `## [1.5.0]`, `# v1.5.0`).

**d) Last resort**

If no GitHub repo is found or both fetches fail, show:

```
⚠ No changelog found for {package-name}.
  npm page: https://www.npmjs.com/package/{package-name}?activeTab=versions
```

Never silently skip a package.

### Display format

Show each package result like this:

```
─────────────────────────────────────────
package-name  1.2.3 → 1.5.0
Source: https://github.com/owner/repo/releases
─────────────────────────────────────────

### v1.5.0
...release notes...

### v1.4.0
...release notes...
```

Truncate release notes that are excessively long (keep the first ~50 lines per release and add "… (see full release notes at SOURCE_URL)").

### Breaking changes

Scan each release's notes for breaking changes. If any are found, surface them **before** the full release notes with a prominent callout block:

```
> ⚠ BREAKING CHANGES in vX.Y.Z
> - <breaking change 1>
> - <breaking change 2>
```

Signals to scan for: headings or text containing "breaking", "BREAKING CHANGE", "migration", "removed", "deprecated API", or major semver bumps with behavioral caveats. When in doubt, flag it.

## Step 5 — Write changelog log file

Before asking to confirm the update, write a log file so the user has a record to review.

**Determine the scope label** from the highest bump type among the packages being updated:
- Any major update → `major`
- Any minor update (no major) → `minor`
- All patches → `patch`

**File path:** `package-changelog/{yyyy-mm-dd}-{scope}.md` relative to the project root (the directory containing `package.json`).

If a file with that name already exists, **append** the new update session to it rather than creating a new file. Add a `---` separator and a new `## Updated packages` + `## Changelogs` section below the existing content.

Ensure the `package-changelog/` directory exists by running `mkdir -p package-changelog` first.

**File content format:**

```markdown
# Package Update — {yyyy-mm-dd} ({scope})

## Updated packages

| Package | From | To | Type |
|---------|------|----|------|
| package-name | 1.2.3 | 1.2.6 | patch |

## Changelogs

---

### package-name  1.2.3 → 1.2.6

<!-- If breaking changes exist, add this block first: -->
> ⚠ BREAKING CHANGES
> - <breaking change 1>

...release notes (same content shown to user, untruncated)...

---
```

After writing the file, tell the user: `Changelog written to package-changelog/{filename}` and then ask to confirm the update.

## Step 6 — Confirm and run the update

After displaying all changelogs, ask the user to confirm before touching anything:

> Ready to update N packages. Run `pnpm update`?

If they confirm, run:

```bash
# For packages still within their semver range (patch / minor):
pnpm update {pkg1} {pkg2} ...

# For packages that require bumping the range (major):
pnpm update --latest {pkg1} {pkg2} ...
```

Split the list into two separate `pnpm update` calls if needed: one without `--latest` for in-range packages and one with `--latest` for out-of-range ones.

After the update completes, run `pnpm outdated --json 2>&1` again and confirm the updated packages no longer appear.

Remind the user to run their test suite if any major updates were applied.

## Step 7 — Suggest a git commit message

After a successful update, output a ready-to-use git commit message in a code block:

```
chore(deps): update {scope} dependencies ({date})

- package-name: 1.2.3 → 1.2.6
- package-name: 1.0.0 → 1.0.4
```

Rules:
- Subject line: `chore(deps): update {scope} dependencies ({yyyy-mm-dd})`
- Body: one bullet per package in the format `- {name}: {old} → {new}`
- If multiple bump types are included, use the highest as the scope label
- Keep it copy-paste ready — no extra explanation around the code block

## Edge cases

| Situation | Action |
|-----------|--------|
| Package not on GitHub (GitLab, Bitbucket, etc.) | Show the repository URL and link to the npm page instead |
| Private or scoped package with no public registry entry | Note it is private and skip changelog fetch |
| GitHub API rate limit hit (403 / 429) | Fall back to raw CHANGELOG.md; note the rate limit |
| Package has `isDeprecated: true` | Warn the user before updating; suggest searching for alternatives |
| Major update with no migration guide in release notes | Remind user to check the package's docs for a migration guide |
| pnpm not installed | Tell the user to install pnpm and stop |
| No `package.json` in cwd | Tell the user to run this from a project root |
