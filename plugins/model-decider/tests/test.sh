#!/usr/bin/env bash
# Feeds fake hook payloads to bin/decider and checks the log lines it writes.
# Usage: tests/test.sh
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export MODEL_DECIDER_HOME=$(mktemp -d)
trap '[ -n "${KEEP:-}" ] || rm -rf "$MODEL_DECIDER_HOME"' EXIT
LOG="$MODEL_DECIDER_HOME/log.jsonl"
TP="$MODEL_DECIDER_HOME/transcript.jsonl"
fails=0

hook() { "$ROOT/bin/decider"; }
check() {
  local name=$1 filter=$2
  if jq -se "$filter" "$LOG" >/dev/null 2>&1; then echo "ok   $name"; else echo "FAIL $name"; fails=$((fails + 1)); fi
}
base() { jq -cn --arg tp "$TP" '{session_id: "s1", cwd: "/home/u/proj", transcript_path: $tp} + $ARGS.named' "$@"; }
assistant() { jq -cn --arg id "$1" --argjson c "$2" --argjson out "$3" \
  '{type: "assistant", message: {id: $id, model: "claude-opus-5-5", content: $c, usage: {output_tokens: $out}}}'; }

# SessionStart prints routing rules and links bin/.
out=$(base --arg hook_event_name SessionStart | hook)
[[ "$out" == *"Model routing"* ]] && echo "ok   session start prints routing" || { echo "FAIL session start prints routing"; fails=$((fails + 1)); }
[ -x "$MODEL_DECIDER_HOME/bin/report" ] && echo "ok   session start links bin" || { echo "FAIL session start links bin"; fails=$((fails + 1)); }

# Turn 1: delegation to haiku with a reason tag, resolved to an exact model.
base --arg hook_event_name UserPromptSubmit --arg prompt "where is the auth middleware?" --arg prompt_id p1 | hook
base --arg hook_event_name PreToolUse --arg tool_name Agent --arg tool_use_id t1 \
  --argjson tool_input '{"description":"[simple lookup] Find auth middleware","prompt":"...","subagent_type":"model-decider:haiku"}' | hook
base --arg hook_event_name PostToolUse --arg tool_name Agent --arg tool_use_id t1 \
  --argjson tool_response '{"agentId":"a1","resolvedModel":"claude-haiku-5-5"}' | hook
{
  echo '{"type":"user","promptId":"p1","message":{"content":"where is the auth middleware?"}}'
  assistant m1 '[{"type":"tool_use","name":"Agent"}]' 50
  echo '{"type":"user","promptId":"p1","message":{"content":[{"type":"tool_result"}]}}'
  assistant m2 '[{"type":"text","text":"It is in src/auth.ts"}]' 40
} >"$TP"
base --arg hook_event_name Stop --arg prompt_id p1 | hook

check "haiku pick logged with reason and prompt" \
  'map(select(.event=="pick" and .id=="t1")) | .[0] | .tier=="haiku" and .reason=="simple lookup" and .prompt=="where is the auth middleware?" and .prompt_id=="p1"'
check "resolved model logged" 'any(.event=="resolved" and .id=="t1" and .model=="claude-haiku-5-5")'
check "turn with delegation is not an opus pick" '(map(select(.event=="pick" and .tier=="opus")) | length) == 0'
check "turn stats" 'map(select(.event=="turn" and .id=="p1")) | .[0] | .delegations==1 and .tool_calls==1 and .output_tokens==90'

# Naming the picked tier counts as ok.
base --arg hook_event_name UserPromptExpansion --arg command_name rate --arg command_args "should-be haiku" | hook >/dev/null
check "should-be same tier is ok" 'map(select(.event=="rate")) | first | .verdict=="ok" and .should_be==null'

# Rate the haiku pick (latest rating wins).
out=$(base --arg hook_event_name UserPromptExpansion --arg command_name model-decider:rate --arg command_args "should-be sonnet" | hook)
[[ $(jq -r .decision <<<"$out") == block ]] && echo "ok   rate blocks the prompt" || { echo "FAIL rate blocks the prompt"; fails=$((fails + 1)); }
check "rate logged against last pick" 'any(.event=="rate" and .pick_id=="t1" and .should_be=="sonnet")'
out=$(base --arg hook_event_name UserPromptExpansion --arg command_name rate --arg command_args "great" | hook)
[[ $(jq -r .reason <<<"$out") == Usage* ]] && echo "ok   bad rate shows usage" || { echo "FAIL bad rate shows usage"; fails=$((fails + 1)); }

# Turn 2: /tier opus override, handled in the main session (no delegation) => opus pick.
base --arg hook_event_name UserPromptSubmit --arg prompt "/tier opus redesign the cache" --arg prompt_id p2 | hook
base --arg hook_event_name UserPromptExpansion --arg command_name model-decider:tier --arg command_args "opus redesign the cache" | hook
{
  echo '{"type":"user","promptId":"p2","message":{"content":"/tier opus redesign the cache"}}'
  assistant m3 '[{"type":"tool_use","name":"Read"}]' 100
  assistant m3 '[{"type":"tool_use","name":"Edit"}]' 100
  assistant m4 '[{"type":"text","text":"done"}]' 200
} >>"$TP"
base --arg hook_event_name Stop --arg prompt_id p2 | hook
base --arg hook_event_name Stop --arg prompt_id p2 | hook

check "override logged" 'any(.event=="override" and .tier=="opus")'
check "no-delegation turn logged as opus pick with size" \
  'map(select(.event=="pick" and .id=="p2")) | length==1 and .[0].tier=="opus" and .[0].override=="opus" and .[0].tool_calls==2 and .[0].output_tokens==300 and .[0].model=="claude-opus-5-5"'
[ "$(jq -r .override "$MODEL_DECIDER_HOME/state/s1.json")" = null ] && echo "ok   override state cleared" || { echo "FAIL override state cleared"; fails=$((fails + 1)); }

# Turn 3: escalation tag + suspected escalation (main does >5 tool calls after the subagent).
base --arg hook_event_name UserPromptSubmit --arg prompt "fix the flaky test" --arg prompt_id p3 | hook
base --arg hook_event_name PreToolUse --arg tool_name Agent --arg tool_use_id t3 \
  --argjson tool_input '{"description":"[escalate from haiku] Fix flaky test","prompt":"...","subagent_type":"model-decider:sonnet"}' | hook
{
  echo '{"type":"user","promptId":"p3","message":{"content":"fix the flaky test"}}'
  assistant m5 '[{"type":"tool_use","name":"Agent"}]' 10
  for i in 1 2 3 4 5 6; do assistant "m6$i" '[{"type":"tool_use","name":"Bash"}]' 10; done
} >>"$TP"
base --arg hook_event_name Stop --arg prompt_id p3 | hook

check "escalate tag parsed" 'any(.event=="pick" and .id=="t3" and .tier=="sonnet" and .escalate_from=="haiku")'
check "suspected escalation flagged" 'any(.event=="turn" and .id=="p3" and .suspected_escalation==true and .tools_after_last_agent==6)'

# Bad /tier shows usage; nested agent calls are ignored.
out=$(base --arg hook_event_name UserPromptExpansion --arg command_name tier --arg command_args "gpt do it" | hook)
[[ $(jq -r .reason <<<"$out") == Usage* ]] && echo "ok   bad tier shows usage" || { echo "FAIL bad tier shows usage"; fails=$((fails + 1)); }
base --arg hook_event_name PreToolUse --arg tool_name Agent --arg tool_use_id t9 --arg agent_id sub1 \
  --argjson tool_input '{"description":"x","subagent_type":"Explore"}' | hook
check "nested agent ignored" 'all(.id != "t9")'

# Report runs over the log.
report=$("$ROOT/bin/report" 7d)
[[ "$report" == *"| proj | 1 | 1 | 1 | 0 |"* ]] && echo "ok   report tier split" || { echo "FAIL report tier split"; echo "$report"; fails=$((fails + 1)); }
[[ "$report" == *'"signals":["rated should be sonnet"]'* ]] && echo "ok   report flags rated pick" || { echo "FAIL report flags rated pick"; echo "$report"; fails=$((fails + 1)); }

echo
[ "$fails" = 0 ] && echo "All passed" || { echo "$fails failed"; exit 1; }
