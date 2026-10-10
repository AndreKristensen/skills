# skills

Skills and plugins for Claude Code and Codex.

## model-decider 0.3.1

Keep your main conversation on Sonnet or GPT-6.1 Sol. The picker delegates substantial
simple tasks to fast and complex work to deep. Tiny questions stay local because
delegation has overhead.

| Tier | Claude Code | Codex | Work |
|---|---|---|---|
| fast | Haiku | GPT-6 Luna, medium effort | Searches, extraction, summaries, mechanical edits |
| balanced | Sonnet | GPT-6.1 Sol, medium effort | Most coding, tests, ordinary debugging |
| deep | Opus | GPT-6 Astra, medium effort | Architecture, uncertain debugging, demanding work |

These pairs match routing roles, not guaranteed performance or subscription usage.
Model choices live in [models.json](plugins/model-decider/models.json) and the shared
policy in [routing.md](plugins/model-decider/routing.md). Claude uses current aliases;
Codex uses explicit IDs. Named Claude agent profiles must match the configured aliases.

The hook allows one automatic deep subagent launch per user request, including
parallel work. Explicit deep overrides bypass that limit. The guard covers intercepted
Agent/spawn_agent launches, not external processes, every integration or subsequent
messages to an existing agent. With untrusted or disabled hooks, routing is advisory
and automatic logging is inactive.

### Requirements

Python 3.9 or newer, Bash, and a local Linux or macOS runtime. The handler uses the
Python standard library and file locks. Windows and remote/web runtimes are not
verified. The plugin needs no jq, GNU date, API key or separate API billing.

### Claude Code installation

Use the clone's path for unpushed changes:

~~~bash
claude plugin marketplace add /home/ask/dev/skills
claude plugin install model-decider@ask-skills
~~~

For an existing installation:

~~~bash
claude plugin marketplace update ask-skills
claude plugin update model-decider@ask-skills
~~~

Start a new session with Sonnet. The plugin recommends the main model but leaves
selection to you. Once published, replace the local path with AndreKristensen/skills
for installation on other machines.

### Codex installation

Use the native Codex catalog under marketplaces/codex. It points to the same plugin
through a relative symlink, so there is only one implementation to maintain. Its
Codex manifest selects a separate hook configuration. The separate catalog avoids
writing inside an existing protected .agents directory in the repository root.

~~~bash
codex plugin marketplace add /home/ask/dev/skills/marketplaces/codex
codex plugin add model-decider@ask-skills
~~~

Re-add the plugin from the local marketplace after changing its version. For Git
marketplaces, run codex plugin marketplace upgrade ask-skills first. You can also
install through the desktop app's Plugins directory.

If ask-skills was registered at the clone root in Codex, remove that source
registration before adding the native path. This does not change the Claude source:

~~~bash
codex plugin marketplace remove ask-skills
~~~

Start a new session on GPT-6.1 Sol with medium reasoning. Review and trust changed
hooks through /hooks where that UI is available. Installation alone does not trust
hooks. Use normal trust review rather than bypass flags.

See [Codex packaging](https://developers.openai.com/plugins/build/plugins) and
[hook trust](https://learn.chatgpt.com/docs/hooks).

### Usage

| Command | Behavior |
|---|---|
| /tier fast <request> | Force a fast model for this request |
| /tier balanced <request> | Force balanced |
| /tier deep <request> | Explicit deep override, exempt from the automatic limit |
| /tier balanced high <request> | Codex effort override if the host supports it |
| /rate ok | Rate the latest pick in this session |
| /rate should-be fast | Record a different preferred tier |
| /decider-report 7d | Review the last seven days; 7d is the default |

Use the model-decider: prefix if names clash. On Codex use the skill picker or
$model-decider:tier invocation. haiku/sonnet/opus and luna/sol/astra are tier aliases.
Raw rating prompts are handled by hooks without a model response. If a host expands
the skill first, it uses the session helper and costs an ordinary model/tool turn.
Missing hook context produces an explicit error rather than a fabricated rating.

Unavailable fast models fall back to balanced. Unavailable deep models use balanced
where feasible and explain the limitation. A failed deep launch consumes the automatic
allowance. The plugin does not silently select an older model.

### Log and report

Both platforms append to ~/.claude/model-decider/log.jsonl, preserving existing
Claude history. MODEL_DECIDER_HOME selects another directory. State is isolated by
platform and session, and new records have a platform and request ID.

The log stores up to 200 characters of prompts and delegation descriptions. It records
picks, overrides, resolved model IDs when available, failures, fallbacks, blocked launches,
turn contributions and ratings. Requested models remain separate from confirmed models.
Unresolved runs appear as unresolved in reports.

Reports include main-session overhead even when work is delegated. Transcript-derived
usage is best effort and may lag. Absent usage is null. Codex usage can represent only
the last model request and is labeled accordingly. A completed run does not establish
passing tests; ratings and review help judge results. Significant main work after a
subagent is possible rework rather than a confirmed routing mistake.

API prices are not used to invent subscription cost per task. Where account tools exist,
the report skill can show an account-wide allowance snapshot separately. Routing changes
are suggestions for your review.

~~~bash
plugins/model-decider/bin/report 7d
~~~

### Verification and development

~~~bash
plugins/model-decider/tests/test.sh
claude plugin validate plugins/model-decider
claude plugin validate .
~~~

Tests exercise both adapters, concurrent deep launches, overrides and reset, ratings,
resolved models, usage, failure fallback and platform isolation. Live checks need host
authentication and trusted hooks. Bump both manifests together, update the installation,
and start a new session to load changed rules.
