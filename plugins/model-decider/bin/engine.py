#!/usr/bin/env python3
"""Shared hook adapters and reports. Python standard library; Linux/macOS."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
MODELS = json.loads((ROOT / 'models.json').read_text())
ALIASES = {'haiku': 'fast', 'luna': 'fast', 'sonnet': 'balanced',
           'sol': 'balanced', 'opus': 'deep', 'astra': 'deep'}
EFFORTS = {'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}


def tier(value):
    value = str(value or '').lower()
    if value in ('fast', 'balanced', 'deep'):
        return value
    for name, role in ALIASES.items():
        if re.search(r'(^|[-:])' + name + r'($|[-:])', value):
            return role
    return 'other'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def data_dir():
    # Retain the existing global location and history for upgrades.
    return Path(os.environ.get('MODEL_DECIDER_HOME', '~/.claude/model-decider')).expanduser()


def emit(event, **fields):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, **fields}}))


def deny(reason):
    emit('PreToolUse', permissionDecision='deny', permissionDecisionReason=reason)


def read_jsonl(path):
    try:
        with Path(path).expanduser().open() as stream:
            for line in stream:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # A partially flushed transcript is normal.
    except (OSError, TypeError):
        return


def transcript_stats(path, platform, request_id):
    """Best-effort, version-sensitive usage. Never turn absent usage into zero."""
    rows = list(read_jsonl(path)) if path else []
    if platform == 'claude':
        starts = [i for i, r in enumerate(rows) if r.get('type') == 'user'
                  and not r.get('isSidechain') and
                  (r.get('promptId') == request_id or
                   isinstance(r.get('message', {}).get('content'), str))]
        exact = [i for i in starts if rows[i].get('promptId') == request_id]
        # All tool-result messages can share promptId. Start at the first match,
        # not the last result, or main-model usage disappears.
        rows = rows[exact[0] if exact else (starts or [len(rows)])[-1]:]
        messages = {}
        for r in rows:
            if r.get('type') == 'assistant' and not r.get('isSidechain'):
                m = r.get('message', {})
                messages[m.get('id', r.get('uuid', str(len(messages))))] = m
        models = [m.get('model') for m in messages.values()
                  if m.get('model') and m.get('model') != '<synthetic>']
        usages = [m['usage'] for m in messages.values() if isinstance(m.get('usage'), dict)]
        efforts = [r.get('perTurnEffort') or r.get('effort') for r in rows
                   if r.get('type') == 'assistant' and (r.get('perTurnEffort') or r.get('effort'))]
        usage = {k: sum(u.get(k, 0) for u in usages) for k in
                 ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')}
        return {'model': models[-1] if models else None, 'effort': efforts[-1] if efforts else None,
                'usage': usage if usages else None,
                'usage_source': 'transcript_best_effort' if usages else 'unavailable'}
    # Codex rollout formats vary. Only use usage explicitly associated with this turn.
    active = False
    usage = None
    model = None
    effort = None
    for r in rows:
        p = r.get('payload', {})
        if not isinstance(p, dict):
            continue
        if r.get('type') == 'turn_context':
            active = p.get('turn_id') == request_id
            if active:
                model, effort = p.get('model'), p.get('effort')
        if active and p.get('type') == 'token_count':
            usage = (p.get('info') or {}).get('last_token_usage')
    return {'model': model, 'effort': effort, 'usage': usage,
            'usage_source': 'transcript_last_request' if usage else 'unavailable'}


def response_object(value):
    if isinstance(value, dict):
        if isinstance(value.get('structuredContent'), dict):
            return value['structuredContent']
        for block in value.get('content', []):
            if isinstance(block, dict) and block.get('type') == 'text':
                parsed = response_object(block.get('text'))
                if parsed:
                    return parsed
        return value
    if isinstance(value, str):
        try:
            return response_object(json.loads(value))
        except json.JSONDecodeError:
            pass
    return {}


class Store:
    def __init__(self, payload, platform):
        self.p = payload
        self.platform = platform
        self.session = str(payload.get('session_id') or 'unknown')
        self.directory = data_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'state').mkdir(exist_ok=True)
        key = hashlib.sha256((platform + ':' + self.session).encode()).hexdigest()
        self.path = self.directory / 'state' / (key + '.json')

    def __enter__(self):
        # One transaction lock covers state, budget reservation and log append.
        self.lock = (self.directory / 'transaction.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        return self

    def __exit__(self, *error):
        try:
            if not error[0]:
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(self.state))
                temporary.replace(self.path)
        finally:
            self.lock.close()

    def log(self, event, **fields):
        record = {'ts': now(), 'schema_version': 2, 'platform': self.platform,
                  'session': self.session, 'project': self.p.get('cwd'),
                  'request_id': self.state.get('request_id'), 'turn_id': self.state.get('turn_id'),
                  'event': event, **fields}
        with (self.directory / 'log.jsonl').open('a') as stream:
            stream.write(json.dumps(record) + '\n')
        return record

    def begin(self):
        rid = str(self.p.get('turn_id') or self.p.get('prompt_id') or uuid.uuid4())
        if self.state.get('request_id') != rid:
            last = self.state.get('last_pick')
            self.state = {'request_id': rid, 'last_pick': last, 'picks': {},
                          'turn_id': rid, 'deep_calls': 0, 'tool_calls': 0, 'tools_after_agent': 0}
        return rid

    def command(self, name, arguments):
        bits = arguments.split()
        if name == 'tier':
            if len(bits) < 2 or tier(bits[0]) == 'other':
                return {'decision': 'block', 'reason': 'Usage: /tier fast|balanced|deep [effort] <request>'}
            role = tier(bits[0])
            effort = bits[1] if bits[1] in EFFORTS else None
            if effort and (self.platform != 'codex' or len(bits) < 3):
                return {'decision': 'block', 'reason': 'Effort requires Codex and a request.'}
            signature = [self.state.get('request_id'), arguments]
            if self.state.get('override_signature') != signature:
                self.state.update(override=role, effort_override=effort, override_signature=signature)
                self.log('override', tier=role, effort=effort, prompt=arguments[:200])
            return {'hookSpecificOutput': {'hookEventName': self.p['hook_event_name'],
                    'additionalContext': f'Explicit one-shot tier override: {role}; effort: {effort or "medium"}. Follow the platform configuration.'}}
        if name == 'rate':
            last = self.state.get('last_pick')
            if not last:
                return {'decision': 'block', 'reason': 'No pick to rate in this session yet.'}
            should = tier(bits[1]) if len(bits) == 2 and bits[0] == 'should-be' else None
            if bits != ['ok'] and should not in ('fast', 'balanced', 'deep'):
                return {'decision': 'block', 'reason': 'Usage: /rate ok | should-be fast|balanced|deep'}
            verdict = 'ok' if should is None or should == last['tier'] else 'should-be'
            self.log('rate', pick_id=last['id'], picked=last['tier'], verdict=verdict,
                     should_be=should if verdict != 'ok' else None)
            return {'decision': 'block', 'reason': f'Rated {last["tier"]}: {verdict}' }
        return None


def hook(p, platform):
    event = p.get('hook_event_name')
    if p.get('agent_id') and event != 'SubagentStop':
        return
    with Store(p, platform) as db:
        st = db.state
        if event == 'SessionStart':
            config = MODELS[platform]
            text = (ROOT / 'routing.md').read_text() + '\nPlatform: ' + platform
            text += '\nModel configuration: ' + json.dumps(config)
            text += '\nReport script: ' + str(ROOT / 'bin/report')
            text += '\nHook helper: ' + str(ROOT / 'bin/engine.py')
            text += '\nCurrent session ID: ' + db.session
            text += '\nDeep limit: enforced on intercepted agent launches; advisory on other paths.'
            if p.get('model') and tier(p['model']) != 'balanced':
                text += '\nCurrent main model: ' + p['model'] + '. Recommend ' + config['balanced']['model'] + '.'
            emit(event, additionalContext=text)
        elif event in ('UserPromptSubmit', 'UserPromptExpansion'):
            prompt = p.get('prompt', '')
            match = re.match(r'^[/\$](?:model-decider:)?(tier|rate)\s+(.*)', prompt, re.S)
            name = p.get('command_name', '').split(':')[-1] if event == 'UserPromptExpansion' else None
            args = p.get('command_args', '')
            if match:
                name, args = match.groups()
            if name != 'rate':
                if event == 'UserPromptSubmit':
                    continuation = prompt.lstrip().startswith(('<task-notification>', '<subagent_notification>'))
                    if continuation and st.get('request_id'):
                        st['turn_id'] = str(p.get('turn_id') or p.get('prompt_id') or uuid.uuid4())
                        st['continuation'] = True
                        st['turn_tool_start'] = st.get('tool_calls', 0)
                        st['turn_agent_start'] = len(st.get('picks', {}))
                    else:
                        db.begin()
                        st = db.state
                        st['continuation'] = False
                        st['prompt'] = prompt[:200]
                elif not st.get('request_id'):
                    db.begin()
                    st = db.state
            if name in ('tier', 'rate'):
                result = db.command(name, args)
                if result:
                    print(json.dumps(result))
            elif event == 'UserPromptSubmit':
                emit(event, additionalContext='Model-decider request ID: ' + db.state['request_id'] + '; main model: ' + str(p.get('model') or 'unknown') + '.')
        elif event == 'PreToolUse':
            name = p.get('tool_name', '')
            agent = name == 'Agent' or name.split('__')[-1] == 'spawn_agent'
            if not st.get('request_id'):
                db.begin()
                st = db.state
            if not agent:
                st['tool_calls'] = st.get('tool_calls', 0) + 1
                if st.get('picks'):
                    st['tools_after_agent'] = st.get('tools_after_agent', 0) + 1
                return
            i = p.get('tool_input') or {}
            description = i.get('description') or i.get('message') or i.get('prompt') or ''
            if not description and isinstance(i.get('items'), list):
                description = ' '.join(x.get('text', '') for x in i['items'] if isinstance(x, dict))
            agent_type = i.get('subagent_type')
            selected = i.get('model')
            if not selected and platform == 'claude':
                selected = next((v['model'] for v in MODELS['claude'].values()
                                 if v['agent'] == agent_type), p.get('model'))
            selected = selected or p.get('model')
            role = tier(selected)
            if platform == 'codex' and role != 'other' and selected != MODELS['codex'][role]['model']:
                deny('Use the configured ' + role + ' model: ' + MODELS['codex'][role]['model'] + '. Older model substitution is disabled.')
                return
            call_id = p.get('tool_use_id') or str(uuid.uuid4())
            if call_id in st.get('picks', {}):
                return
            reason_match = re.match(r'\s*\[([^\]]+)\]', description)
            reason = reason_match[1] if reason_match else None
            override = st.get('override')
            if override and role != override:
                db.log('blocked', tier=role, reason='override_mismatch')
                deny('Explicit /tier requires ' + override + '. Retry with the configured model.')
                return
            if role == 'deep' and override != 'deep' and st.get('deep_calls', 0) >= 1:
                db.log('blocked', tier=role, reason='deep_limit')
                deny('One automatic deep launch already used for this request. Continue on balanced or ask for an explicit /tier deep request.')
                return
            if role == 'deep' and override != 'deep':
                st['deep_calls'] = st.get('deep_calls', 0) + 1
            effort = i.get('reasoning_effort')
            if not effort and isinstance(p.get('effort'), dict):
                effort = p['effort'].get('level')
            if platform == 'codex' and role != 'other':
                expected_effort = st.get('effort_override') or 'medium'
                if effort != expected_effort:
                    # Deny and ask the agent to retry. No automatic permission approval.
                    if role == 'deep' and override != 'deep':
                        st['deep_calls'] -= 1
                    deny('Set reasoning_effort to ' + expected_effort + ' for this routed task.')
                    return
            escalation = re.match(r'escalate from (\w+)', reason or '')
            failures = [x for x in st.get('picks', {}).values() if x.get('failed')]
            if failures and role == 'balanced':
                db.log('fallback', from_pick=failures[-1]['id'], from_tier=failures[-1]['tier'],
                       to_tier=role, reason='balanced_after_failed_agent')
            pick = db.log('pick', id=call_id, tier=role, agent=agent_type or name,
                          requested_model=selected, model=None, effort=effort,
                          override=override, reason=reason, desc=description[:200],
                          prompt=st.get('prompt'), escalate_from=tier(escalation[1]) if escalation else None,
                          limit_mode='intercepted_tool', usage=None)
            st.setdefault('picks', {})[call_id] = pick
            st['last_pick'] = pick
            st['tool_calls'] = st.get('tool_calls', 0) + 1
            st['tools_after_agent'] = 0
        elif event in ('PostToolUse', 'PostToolUseFailure'):
            call_id = p.get('tool_use_id')
            pick = st.get('picks', {}).get(call_id)
            if not pick:
                return
            r = response_object(p.get('tool_response'))
            failed = event == 'PostToolUseFailure' or r.get('isError') is True or r.get('error') is not None
            model = r.get('resolvedModel') or r.get('model')
            agent_id = r.get('agentId') or r.get('agent_id')
            if agent_id:
                pick['agent_id'] = agent_id
            pick['failed'] = failed
            db.log('resolved', id=call_id, model=model, agent_id=agent_id,
                   effort=r.get('reasoning_effort'), usage=r.get('usage'),
                   status='failed' if failed else r.get('status'), outcome_source='tool_response')
            if failed:
                db.log('failure', pick_id=call_id, tier=pick['tier'],
                       reason=str(p.get('error') or r.get('error') or 'agent tool reported an error')[:200])
        elif event == 'SubagentStop':
            picks = [x for x in st.get('picks', {}).values() if x.get('agent_id') == p.get('agent_id')]
            if picks:
                stats = transcript_stats(p.get('agent_transcript_path'), platform, p.get('turn_id'))
                db.log('resolved', id=picks[-1]['id'], model=stats.get('model') or p.get('model'),
                       effort=stats.get('effort'), usage=stats.get('usage'),
                       usage_source=stats['usage_source'], status='completed')
            print('{}')
        elif event == 'Stop':
            rid = st.get('turn_id') or st.get('request_id')
            incoming = p.get('turn_id') or p.get('prompt_id')
            if incoming and incoming != rid:
                return
            if not rid or st.get('stopped') == rid:
                return
            stats = transcript_stats(p.get('transcript_path'), platform, rid) if not st.get('continuation') else {'usage_source': 'unavailable'}
            model = stats.get('model') or p.get('model') or st.get('main_model')
            st['main_model'] = model
            db.log('turn', id=rid, main_model=model, effort=stats.get('effort'),
                   usage=stats.get('usage'), usage_source=stats['usage_source'],
                   tool_calls=st.get('tool_calls', 0) - st.get('turn_tool_start', 0),
                   delegations=len(st.get('picks', {})) - st.get('turn_agent_start', 0),
                   tools_after_last_agent=st.get('tools_after_agent', 0),
                   suspected_escalation=bool(st.get('picks')) and st.get('tools_after_agent', 0) > 5)
            if not st.get('picks'):
                pick = db.log('pick', id=rid, tier=tier(model), model=model, agent='main',
                              override=st.get('override'), prompt=st.get('prompt'),
                              reason='main_session', effort=stats.get('effort'), usage=stats.get('usage'))
                st['last_pick'] = pick
            st['stopped'] = rid
            # Keep the request's budget and override through background completion.
            # The next actual user prompt creates fresh state in begin().


def report(period):
    if not re.fullmatch(r'[1-9]\d*d', period):
        raise ValueError('Period must look like 7d or 30d')
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(period[:-1]))).isoformat(timespec='seconds').replace('+00:00', 'Z')
    rows = [r for r in read_jsonl(data_dir() / 'log.jsonl') if r.get('ts', '') >= cutoff]
    if not rows:
        print('Log is empty for this period: ' + str(data_dir() / 'log.jsonl'))
        return
    def key(r, field='id'):
        return (r.get('platform', 'claude'), r.get('session'), r.get(field))
    resolved = {}
    ratings = {}
    for r in rows:
        if r.get('event') == 'resolved':
            current = resolved.setdefault(key(r), {})
            current.update({k: v for k, v in r.items() if v is not None})
        elif r.get('event') == 'rate':
            ratings[key(r, 'pick_id')] = r
    picks = [r for r in rows if r.get('event') == 'pick']
    print(f'Model-decider report, last {period}. {len(picks)} picks.')
    print('Subscription cost per task: unavailable. Token counts are usage evidence only.')
    print('| Platform | Project | Fast | Balanced | Deep | Other | Unresolved |')
    print('|---|---|---:|---:|---:|---:|---:|')
    groups = sorted({(r.get('platform', 'claude'), r.get('project') or '') for r in picks})
    for platform, project in groups:
        counts = dict.fromkeys(('fast', 'balanced', 'deep', 'other', 'unresolved'), 0)
        for r in picks:
            if (r.get('platform', 'claude'), r.get('project') or '') != (platform, project):
                continue
            model = resolved.get(key(r), {}).get('model') or r.get('model')
            counts[tier(model) if model else 'unresolved'] += 1
        print('| ' + ' | '.join([platform, project] + [str(v) for v in counts.values()]) + ' |')
    for platform in ('claude', 'codex'):
        subset = [r for r in picks if r.get('platform', 'claude') == platform]
        outcomes = [r for r in ratings.values() if r.get('platform', 'claude') == platform]
        blocked = [r for r in rows if r.get('platform', 'claude') == platform and r.get('event') == 'blocked']
        failures = [r for r in rows if r.get('platform', 'claude') == platform and r.get('event') == 'failure']
        fallbacks = [r for r in rows if r.get('platform', 'claude') == platform and r.get('event') == 'fallback']
        print(f'{platform}: {sum(bool(r.get("override")) for r in subset)} override picks; '
              f'{sum(bool(r.get("escalate_from")) for r in subset)} tagged escalations; '
              f'{len(blocked)} blocked launches; {len(failures)} failures; {len(fallbacks)} fallbacks; {len(outcomes)} ratings, '
              f'{sum(r.get("verdict") == "should-be" for r in outcomes)} rated wrong.')
    print('Main-session contributions, including dispatcher overhead:')
    for r in rows:
        if r.get('event') == 'turn':
            print(json.dumps({k: r.get(k) for k in ('platform', 'session', 'id', 'main_model', 'effort', 'usage', 'usage_source', 'tool_calls', 'delegations', 'suspected_escalation')}))
    print('Candidate picks for review:')
    for r in picks:
        rating = ratings.get(key(r))
        signals = []
        if rating and rating.get('verdict') == 'should-be':
            signals.append('rated should be ' + str(rating.get('should_be')))
        if r.get('escalate_from'):
            signals.append('tagged escalation from ' + str(r['escalate_from']))
        if r.get('agent') != 'main' and not r.get('reason'):
            signals.append('missing reason tag')
        if signals:
            print(json.dumps({**r, 'signals': signals}))
    print('Subagent contributions; requested and confirmed models are separate:')
    for r in picks:
        if r.get('agent') != 'main':
            result = resolved.get(key(r), {})
            print(json.dumps({'platform': r.get('platform', 'claude'), 'session': r.get('session'),
                              'request_id': r.get('request_id') or r.get('prompt_id'), 'id': r['id'],
                              'tier': tier(r.get('tier')), 'requested_model': r.get('requested_model'),
                              'model': result.get('model') or r.get('model'),
                              'requested_effort': r.get('effort'), 'resolved_effort': result.get('effort'),
                              'usage': result.get('usage'), 'status': result.get('status')}))
    print('Completed agent runs and passing checks are different. Ratings and review establish quality.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['hook', 'report', 'command'])
    parser.add_argument('argument', nargs='?', default='7d')
    parser.add_argument('--session')
    parser.add_argument('--command', choices=['tier', 'rate'])
    parser.add_argument('--arguments', default='')
    args = parser.parse_args()
    if args.mode == 'report':
        report(args.argument)
    elif args.mode == 'command':
        if args.argument not in MODELS or not args.session or not args.command:
            parser.error('command requires platform, --session and --command')
        payload = {'session_id': args.session, 'cwd': os.getcwd(), 'hook_event_name': 'UserPromptSubmit'}
        with Store(payload, args.argument) as db:
            if not db.state.get('request_id'):
                parser.error('No hook state for this session. Trust hooks and start a new session first.')
            print(json.dumps(db.command(args.command, args.arguments)))
    elif args.argument in MODELS:
        hook(json.load(sys.stdin), args.argument)
    else:
        parser.error('hook requires claude or codex')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError) as error:
        print('model-decider: ' + str(error), file=sys.stderr)
        sys.exit(2)
