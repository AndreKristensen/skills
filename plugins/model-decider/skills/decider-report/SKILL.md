---
name: decider-report
description: Report on how well the model-decider picker is choosing between Haiku, Sonnet and Opus, from its pick log.
argument-hint: "[7d|30d|<N>d]"
disable-model-invocation: true
---

# Model-decider report

## 1. Gather the numbers

Run (period defaults to 7d):

```bash
~/.claude/model-decider/bin/report $ARGUMENTS
```

It prints summary tables, then candidate suspicious picks as JSON lines. If it says the log is empty, tell the user and stop.

## 2. Judge the candidates

For each candidate, decide whether the tier was right, using the rules in the routing section of your context (haiku = found not reasoned; sonnet = clear but needs judgment; opus = uncertainty, tradeoffs or needs conversation history). Use the prompt snippet, description, size numbers and signals. Pick the **10 most clearly wrong** picks.

## 3. Print the report

Print to the terminal, in this shape:

```
## Model-decider report — last 7d

### Tier split
<the per-project table from the script, unchanged>

### Overrides and escalations
<the table from the script, plus one sentence on what stands out>

### Suspicious picks
| # | When | Project | Picked | Should be | Why |
|---|------|---------|--------|-----------|-----|
| 1 | 10-09 14:02 | skills | opus | haiku | 2 tool calls, 300 tokens: a file lookup |

### Suggested routing changes
<only for a pattern seen 3+ times: the exact line to add or change in routing.md, as a diff>
```

If no pattern repeats, write "None — not enough repeated misses." Don't edit `routing.md` yourself; the user decides.
