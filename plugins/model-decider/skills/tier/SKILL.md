---
name: tier
description: Force fast, balanced or deep for one request on Claude Code or Codex.
argument-hint: "<fast|balanced|deep> [Codex effort] <request>"
disable-model-invocation: true
---

# Force a tier

Use the user's invocation arguments. On Claude Code they are also supplied as
$ARGUMENTS. Normalize haiku/luna to fast, sonnet/sol to balanced, opus/astra to deep.
Read ../../models.json relative to this skill's directory for the platform mapping.
Use the active host tools to determine whether this is Claude Code or Codex.

1. Require a valid tier and a nonempty request. Codex accepts an optional effort
   after the tier: low, medium, high, xhigh, max or ultra if supported by the host.
2. If hook context confirms "Explicit one-shot tier override", the override is
   already registered. Otherwise, if SessionStart supplied a helper and session
   ID, run its command mode before delegating:
   python3 <helper> command <claude|codex> --session <session-id> --command tier --arguments '<arguments>'
   Use safe shell quoting. This call is idempotent. If the helper cannot run but
   override context confirms registration, keep that registration and continue.
3. Claude: invoke the configured named Agent profile with [override] in description.
   Codex: invoke spawn_agent with the configured model, explicit reasoning_effort
   equal to the user's effort or medium, and [override] at the start of message.
   If this tier already matches the main model, handling it locally is allowed.
4. Relay results and relevant checks. If the model is unavailable, explain the
   failure and follow the balanced fallback rule in routing.md.

If hook context is absent, explain that logging and automatic budget enforcement are
inactive. Honor the requested tier only if the host permits the explicit model choice.
Never claim that a log entry was written without confirmation.
