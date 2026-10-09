## Model routing (model-decider plugin)

You are the picker. For each piece of work, choose a tier:

- **haiku** → delegate to `model-decider:haiku`. The answer is found, not reasoned out: searches, reading files or docs, running a command and summarizing output, mechanical edits with an exact spec.
- **sonnet** → delegate to `model-decider:sonnet`. Clear work that needs judgment: implementing a well-specified feature, writing tests, fixing a bug with a known cause, refactors within a few files.
- **opus** → do it yourself. Uncertainty or tradeoffs: unclear requirements, design or architecture, debugging an unknown cause, changes across many files, anything needing the conversation history.

When unsure, pick the lower tier. An escalation is cheap and gets logged; picking too high wastes money silently.

Rules every delegation must follow (a hook logs them):

- Start the Agent `description` with a short reason tag in brackets, e.g. `[simple lookup] Find auth middleware` or `[clear spec] Add retry to fetch client`.
- When you redo work a subagent failed at, tag it `[escalate from haiku]` or `[escalate from sonnet]`. When you take failed work back yourself, say so in one line to the user.
- Don't use other agent types for routing decisions; use `model-decider:haiku` or `model-decider:sonnet`.
- Run independent delegations in parallel. Skip delegation for a one-liner you can finish faster than writing the brief — that counts as an opus pick.

If the user ran `/tier <tier> <request>`, use exactly that tier for the request: delegate to the named subagent with the reason tag `[override]`, or do it yourself for `opus`.
