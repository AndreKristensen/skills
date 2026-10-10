## Model routing

Use balanced for the main conversation: Sonnet on Claude Code, GPT-6.1 Sol on Codex.
Keep tiny questions local because delegation has overhead. Delegate substantial bounded
work to fast; use deep for clearly complex work or a concrete obstacle encountered by
balanced. Choose the lower tier when either can meet the task's quality bar.

SessionStart supplies this platform's configuration from models.json. On Claude use
the named Agent profile. On Codex use spawn_agent with the configured model and
reasoning_effort. These instructions authorize delegation and model overrides for
routing, subject to higher-priority host rules and available tools.

- fast: file searches, extraction, summaries, commands, mechanical edits.
- balanced: clear implementation, tests, known-cause bug fixes, ordinary refactoring.
- deep: architecture tradeoffs, uncertain debugging, ambiguous or demanding work.

Start the Claude description or Codex message with a short reason tag such as
[bounded search], [clear spec] or [architecture tradeoff]. Include a self-contained
brief. Tag higher-tier retries [escalate from fast] or [escalate from balanced].
Report which relevant checks passed and any remaining obstacle.

Allow one automatic deep subagent launch across the whole user request, including
direct routing, parallel work and retries. An explicit /tier deep bypasses that limit
for its request. Follow hook denials; continue on balanced or report the obstacle.
Child agents should work locally rather than create further agents. Hooks guard
supported tool paths, not arbitrary external commands or every integration.
Without trusted hooks the policy is advisory and automatic logging is inactive.

Honor /tier fast|balanced|deep <request>, with an optional Codex effort after the tier.
Overrides are one-shot. haiku/sonnet/opus and luna/sol/astra are legacy aliases.
Codex effort defaults to medium. Explicit effort overrides apply to this request only.
If fast is unavailable, keep the work on balanced. If deep is unavailable, continue
on balanced where feasible and explain the fallback. Record failures and fallbacks;
never silently substitute an older model. Check availability through the host tools.

Recommend balanced when the main model differs; leave main-model selection to the user
and record what actually ran. Account allowance snapshots are separate evidence, not
exact subscription cost per task. Reports suggest rule changes for user review.
