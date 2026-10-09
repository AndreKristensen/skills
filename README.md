# skills

Claude Code skills and plugins.

## model-decider plugin

Picks a model tier for each piece of work and logs every pick, so you can check whether the picker chooses well.

| Tier | Runs as | Used for |
|------|---------|----------|
| haiku | `model-decider:haiku` subagent | Work where the answer is found, not reasoned out: searches, reading files or docs, running a command and summarizing output, mechanical edits |
| sonnet | `model-decider:sonnet` subagent | Clear work that needs judgment: a well-specified feature, tests, a bug with a known cause, refactors within a few files |
| opus | the main session | Uncertainty or tradeoffs: unclear requirements, design, debugging an unknown cause, changes across many files |

Run your main session on Opus. The main session is the picker: it delegates Haiku and Sonnet work to the subagents and keeps Opus work itself. The rules it follows are in [routing.md](plugins/model-decider/routing.md).

### Requirements

- `jq`, `flock` and GNU `date`. These are standard on Linux. On macOS, install `jq`, `flock` and `coreutils` with Homebrew.

### Install

Add this repo as a marketplace:

```bash
claude plugin marketplace add AndreKristensen/skills
```

From a local clone, pass the path to the clone instead of `AndreKristensen/skills`.

Then install the plugin:

```bash
claude plugin install model-decider@ask-skills
```

Restart Claude Code. The routing rules load when a session starts.

### Usage

Work as normal. Each delegation description starts with a reason tag such as `[simple lookup]`, which shows why the tier was picked.

| Command | What it does |
|---------|--------------|
| `/tier <haiku\|sonnet\|opus> <request>` | Forces a tier for one request and logs it as an override |
| `/rate ok` | Marks the last pick in this session as right |
| `/rate should-be <tier>` | Marks the last pick as wrong and records the tier it should have been. A hook handles it, so it uses no tokens |
| `/decider-report [7d\|30d]` | Shows the tier split per project, override and escalation rates, the most suspicious picks, and suggested changes to `routing.md`. The default period is 7 days |

If another plugin uses the same command names, use the full names: `/model-decider:tier`, `/model-decider:rate` and `/model-decider:decider-report`.

### The log

Every event is appended to `~/.claude/model-decider/log.jsonl`, one JSON object per line:

| `event` | Written when |
|---------|--------------|
| `pick` | The main session delegates, or finishes a turn without delegating (logged as an `opus` pick, with its tool-call count and output tokens) |
| `resolved` | A subagent starts. Records the exact model ID that ran |
| `turn` | A turn ends. Records delegations, tool calls, output tokens, and whether the main session did a lot of work after a subagent (a suspected escalation) |
| `override` | You run `/tier` |
| `rate` | You run `/rate` |

The log stores the first 200 characters of each prompt. It stays on your machine.

To set a different log location, use the `MODEL_DECIDER_HOME` environment variable.

### Changing the plugin

1. Edit the files in [plugins/model-decider](plugins/model-decider).
2. Run the tests: `plugins/model-decider/tests/test.sh`.
3. Bump `version` in [plugin.json](plugins/model-decider/.claude-plugin/plugin.json).
4. Run `claude plugin marketplace update ask-skills`.
5. Run `claude plugin update model-decider@ask-skills`.
6. Restart Claude Code.
