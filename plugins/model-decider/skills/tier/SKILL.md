---
name: tier
description: Force the model tier for one request, overriding the model-decider picker. The override is logged.
argument-hint: "<haiku|sonnet|opus> <request>"
disable-model-invocation: true
---

# Forced tier

The user overrode the picker: `$ARGUMENTS`

The first word is the tier; the rest is the request.

- `haiku` or `sonnet`: delegate the whole request to `model-decider:<tier>` with an Agent `description` starting with `[override]`. Relay its result.
- `opus`: do the request yourself without delegating.

Don't second-guess the tier. If it turns out wrong, finish anyway and say in one line which tier would have fit.
