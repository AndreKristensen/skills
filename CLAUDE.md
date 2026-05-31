# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of Claude Code custom skill definitions. Each skill is a Markdown file that Claude Code loads and executes when a user invokes `/skill-name`.

Skills live at: `.claude/skills/<skill-name>/SKILL.md`

## Skill file format

Every `SKILL.md` starts with YAML frontmatter, followed by freeform Markdown instructions:

```markdown
---
name: skill-name               # must match the directory name
description: >
  One or two sentences. This exact text appears in the skill picker
  and in the system reminder Claude receives.
argument-hint: "[optional]"   # shown in the CLI after the skill name
allowed-tools: [Read, Write, Edit, Bash, WebFetch]  # optional allowlist
---

# Skill Title

Step-by-step instructions Claude follows when the skill is invoked.
```

### Key frontmatter fields

| Field | Purpose |
|-------|---------|
| `name` | Slug used in `/name` invocation; must match directory name |
| `description` | Determines when Claude auto-suggests the skill via `TRIGGER when:` patterns |
| `argument-hint` | Displayed hint for optional CLI argument (e.g. `/update-packages minor`) |
| `allowed-tools` | Restricts which tools the skill can use (omit to allow all) |

## Writing skill instructions

Skills are imperative Markdown documents — Claude reads and follows them literally. Effective patterns used in this repo:

- **Step-by-step numbered sections** with explicit commands to run
- **Edge case tables** at the end for unusual inputs
- **`AskUserQuestion` tool calls** described inline when user input is needed mid-flow
- **Parallel tool hints** (e.g. "run all fetches in parallel") to improve performance
- Explicit output format examples (code blocks showing exactly what to print)

## Adding a new skill

1. Create `.claude/skills/<name>/SKILL.md`
2. Write frontmatter with `name`, `description`, and optionally `argument-hint` / `allowed-tools`
3. Write the body as step-by-step instructions Claude will follow
4. Test by invoking `/name` in a Claude Code session in any project

No build step, no install, no tests — the file is the artifact.
