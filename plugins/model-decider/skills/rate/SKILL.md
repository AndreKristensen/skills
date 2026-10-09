---
name: rate
description: Rate the model-decider's most recent pick in this session. Handled by a hook; the model never sees it.
argument-hint: "ok | should-be <haiku|sonnet|opus>"
disable-model-invocation: true
---

# Rate the last pick

The model-decider hook records this rating and stops the command before it reaches you. If you are reading this, the hook did not run: tell the user in one line that the rating was **not** recorded and that the model-decider hooks may not be active.
