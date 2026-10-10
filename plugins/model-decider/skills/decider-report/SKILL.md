---
name: decider-report
description: Review model usage, overrides, escalations and ratings across Claude Code and Codex.
argument-hint: "[7d|30d|<N>d]"
disable-model-invocation: true
---

# Review model routing

1. Run ../../bin/report relative to this skill's directory, using the user's period
   or 7d. The script reads the shared local log. If it is empty, report that and stop.
2. Show the tier counts separately by platform and project, with unresolved models
   labeled unresolved. Include dispatcher usage, overrides, tagged escalations,
   blocked launches and ratings. Tokens do not establish subscription cost per task.
3. Review up to ten candidate picks using their prompt snippet and reason. Distinguish
   requested models from resolved models, completed runs from passing checks, and
   possible rework from confirmed failed routing. Tiny local balanced answers are
   allowed and should not be flagged just for being small.
4. Suggest changes to ../../routing.md only when the same issue appears at least
   three times. Present suggestions for review and leave the rules unchanged.

If account allowance tools are available, show a read-only snapshot separately and
label it account-wide. Do not attribute its consumption to a particular task.
