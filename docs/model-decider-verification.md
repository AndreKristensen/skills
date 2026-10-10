# model-decider 0.3.1 verification

Checked on 2026-10-10, Linux. Source changes are uncommitted.

## Automated checks

- 15 standard-library tests pass for both platform payload formats.
- The concurrent-launch test starts six hook processes. One automatic deep launch
  is admitted and five are denied within the same request.
- Tests cover one-shot aliases and effort, request reset, background completion
  budget preservation, ratings, platform isolation, unresolved models, main-model
  attribution, duplicate transcript blocks, failure fallback and old-model denial.
- Claude plugin and marketplace validators pass. Git whitespace checks pass.

## Live checks

- Claude ran Sonnet 5.5 as the main model and Haiku 5.5 as the fast subagent.
  The hook log recorded the override, pick, resolved Haiku model and main Sonnet
  contribution. Two small read-only runs used scratch logs under /tmp.
- The first Claude run exposed an incorrect transcript boundary when tool results
  shared a prompt ID. The parser now starts at the first matching prompt, and a
  regression test covers a trailing tool result with that same ID.
- The second Claude run completed the fast delegation in the background. Completion
  notifications now retain the original request budget. This is covered by a test.
- Codex ran one GPT-6 Luna subagent at medium effort from a GPT-6.1 Sol main session.
  That run did not produce a plugin hook log. It verifies model delegation, not live
  hook execution or deep-limit enforcement. Hook trust review remains required.
- Both host installations were refreshed to v0.3.1. Codex uses the native catalog
  under marketplaces/codex; Claude retains the original marketplace at the clone root.

## Remaining activation check

Start a fresh Codex session, review the plugin's hooks through /hooks, and trust the
current definitions. Run a fast task and verify that its codex pick and resolved
model appear in the shared log. Then inspect /decider-report. No trust-bypass flag
was used, and the plugin does not change the selected main model automatically.

## Limits

Deep launch enforcement covers intercepted tools. Existing-agent messages, external
processes and specialized paths are outside that boundary. Transcript usage is
best effort. Subscription cost per task is unavailable. macOS, Windows and remote
runtimes have not had live checks.
