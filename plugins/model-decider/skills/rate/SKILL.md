---
name: rate
description: Rate the most recent pick in the current session across Claude Code and Codex.
argument-hint: "ok | should-be <fast|balanced|deep>"
disable-model-invocation: true
---

# Rate the last pick

The prompt hook handles raw /rate and $rate commands. Claude also handles command
expansion. If a hook stops this command, the rating is already recorded.

If these instructions reach the model, use the hook helper and current session ID
from SessionStart context:

python3 <helper> command <claude|codex> --session <session-id> --command rate --arguments '<user arguments>'

Quote arguments safely. Report the returned confirmation or error. If hook context
is absent, state that the rating was not recorded and the user must trust the hooks
and start a new session. Never guess a session ID or rate a different session.
