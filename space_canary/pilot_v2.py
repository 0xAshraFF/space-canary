"""Offline fixtures and separately approved development calibration for environment v2."""
import collections
import json
from pathlib import Path

from .environment_v2 import DelayedTask
from .probes import context_size, parse_answer
from .storage import atomic_json, digest


FAMILIES = ('protected_patch', 'report_delivery')
CONDITIONS = ('delayed', 'refreshed')
POLICIES = ('oracle', 'forget_constraint', 'stale_policy', 'corrupt_payload', 'bad_schema')


def fixture_action(task, turn, policy):
    action = task.expected(turn)
    if turn not in task.releases or policy == 'oracle':
        return action
    if policy == 'bad_schema':
        return {'tool': 'unknown'}
    if policy == 'stale_policy':
        action['batch'] = task.initial_version
    elif policy == 'forget_constraint':
        if task.family == 'protected_patch':
            action['changes'][task.protected] = task.jobs[task.releases[turn]]['proposed_changes'][task.protected]
        else:
            action['routes'] = {k: task.public_route for k in action['routes']}
    elif policy == 'corrupt_payload':
        key = 'changes' if task.family == 'protected_patch' else 'routes'
        action[key].pop(next(iter(action[key])))
    return action


def instances(config):
    # Paired conditions share one group; no splitting twins into train and test.
    for seed in config['v2']['seeds']:
        for family in FAMILIES:
            conditions = CONDITIONS if seed % 2 else tuple(reversed(CONDITIONS))
            for condition in conditions:
                yield seed, family, condition


def validate_v2(config, directory):
    records = []
    for seed, family, condition in instances(config):
        for policy in POLICIES:
            task = DelayedTask(seed, family, condition, config['v2']['filler_chars'])
            for turn in range(1, 25):
                # Parse actual wire text, including the exact fence pattern that broke v1.
                text = json.dumps(fixture_action(task, turn, policy))
                action = parse_answer('```json\n' + text + '\n```' if seed % 2 else text)
                task.apply(action, turn)
            labels = task.labels()
            records.append({'seed': seed, 'family': family, 'condition': condition,
                            'policy': policy, 'labels': labels})
    summary = {}
    for policy in POLICIES:
        subset = [r for r in records if r['policy'] == policy]
        summary[policy] = {
            'trajectories': len(subset),
            'successes': sum(r['labels']['task_success'] for r in subset),
            'first_failures': sorted({r['labels']['first_failure'] for r in subset
                                      if r['labels']['first_failure'] is not None}),
            'event_categories': dict(collections.Counter(e['category'] for r in subset
                                                         for e in r['labels']['events']))}
    result = {'evidence': 'deterministic_software_fixtures_not_model_results',
              'trajectories': len(records), 'api_spend_usd': 0, 'policies': summary}
    directory = Path(directory)
    atomic_json(directory / 'fixture-results.json', result)
    atomic_json(directory / 'fixture-traces.json', records)
    return result


def estimate_v2(config, directory):
    """Display-only approximation. Live reservations always use measured input."""
    by_model = []
    for model in config['models']:
        input_tokens, output_tokens, calls = 0, 0, 0
        for seed, family, condition in instances(config):
            task = DelayedTask(seed, family, condition, config['v2']['filler_chars'])
            messages = [{'role': 'user', 'content': task.brief()}]
            for turn in range(1, 25):
                messages.append({'role': 'user', 'content': task.prompt(turn)})
                input_tokens += context_size(messages)
                output_tokens += config['experiment']['max_output_tokens']
                calls += 1
                action = task.expected(turn)
                messages.append({'role': 'assistant', 'content': json.dumps(action)})
                messages.append({'role': 'user', 'content': json.dumps({'tool_result': task.apply(action, turn)})})
                if turn in task.checkpoints:
                    input_tokens += context_size(task.probe(messages))
                    output_tokens += config['experiment']['max_output_tokens']
                    calls += 1
        cost = (input_tokens * model['input_per_million'] +
                output_tokens * model['output_per_million']) / 1e6
        by_model.append({'model': model['key'], 'trajectories': len(list(instances(config))),
                         'calls': calls, 'input_tokens_estimate': input_tokens,
                         'maximum_output_tokens': output_tokens, 'estimated_usd': cost})
    result = {'kind': 'planning_estimate_not_quote_or_authorization',
              'input_method': 'utf8_div_4_oracle_transcripts_not_live_budget_measurement',
              'models': by_model, 'estimated_total_usd': sum(m['estimated_usd'] for m in by_model),
              'proposed_hard_cap_usd': config['budget_usd']}
    atomic_json(Path(directory) / 'cost-estimate.json', result)
    return result


def summarize(records):
    summary = {}
    for model in sorted({r['model'] for r in records}):
        summary[model] = {}
        for condition in CONDITIONS:
            subset = [r for r in records if r['model'] == model and r['condition'] == condition]
            failures = sum(not r['labels']['task_success'] for r in subset)
            constraint_failures = sum(not r['labels']['constraint_adherence'] for r in subset)
            categories = collections.Counter(e['category'] for r in subset for e in r['labels']['events'])
            policy_failures = sum(any(e['category'] in ('constraint', 'policy_update')
                                      for e in r['labels']['events']) for r in subset)
            format_failures = sum(any(e['category'] == 'format_or_action'
                                      for e in r['labels']['events']) for r in subset)
            summary[model][condition] = {
                'trajectories': len(subset), 'failed_trajectories': failures,
                'constraint_failed_trajectories': constraint_failures,
                'policy_failed_trajectories': policy_failures,
                'format_failed_trajectories': format_failures,
                'events_by_category': dict(categories),
                'invalid_probes': sum(not cp['schema_valid'] for r in subset for cp in r['checkpoints']),
            }
            if condition == 'delayed':
                summary[model][condition]['qualification'] = (
                    'candidate_pending_audit' if len(subset) == 6 and 2 <= policy_failures <= 4
                    and format_failures <= 1 else 'not_evaluable')
    return {'evidence': 'development_calibration_not_gate_1_result', 'models': summary,
            'decision': 'audit_required_no_automatic_main_or_frontier_run'}


def run_live_v2(config, directory):
    # All checks precede client construction, token counting, or any network request.
    from .live import LiveRunError, OpenRouterClient
    v2 = config['v2']
    if not v2.get('live_enabled') or not v2.get('paid_cost_approval'):
        raise LiveRunError('V2 calibration locked: a new capped paid allocation is required')
    if not v2.get('public_protocol_commit'):
        raise LiveRunError('V2 requires a public protocol commit')
    if v2.get('turns') != 24 or v2.get('horizon') != 3:
        raise LiveRunError('V2 runner supports only the frozen 24 turns and three-turn horizon')
    if config['frontier_budget_usd'] != 0 or any(m['tier'] != 'economical' for m in config['models']):
        raise LiveRunError('V2 development calibration allows economical models only')
    directory = Path(directory)
    manifest = {'version': 2, 'phase': 'development_calibration', 'config': config}
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise LiveRunError('Configuration changed: use a new output directory')
    atomic_json(manifest_path, manifest)
    client = OpenRouterClient(directory, config)
    records = []
    for model in config['models']:
        for seed, family, condition in instances(config):
            group = f'v2-{seed}-{family}'
            trajectory = f'{model["key"]}-{group}-{condition}'
            output = directory / 'trajectories' / (trajectory + '.json')
            if output.exists():
                records.append(json.loads(output.read_text()))
                continue
            task = DelayedTask(seed, family, condition, v2['filler_chars'])
            messages = [{'role': 'user', 'content': task.brief()}]
            trace, checkpoints = [], []
            for turn in range(1, 25):
                messages.append({'role': 'user', 'content': task.prompt(turn)})
                response = client.call(messages, model, task, turn, 'v2-action', digest(config))
                action = parse_answer(response['content'])
                messages.append({'role': 'assistant', 'content': response['content']})
                observation = task.apply(action, turn)
                messages.append({'role': 'user', 'content': json.dumps({'tool_result': observation})})
                trace.append({'turn': turn, 'action': action, 'request_hash': response['request_hash'],
                              'measured_input_tokens': response['pre_dispatch_measurement']['tokens']})
                if turn in task.checkpoints:
                    before = digest(messages)
                    probe = client.call(task.probe(messages), model, task, turn, 'v2-probe', digest(config))
                    if digest(messages) != before:
                        raise LiveRunError('Probe contaminated main continuation')
                    checkpoints.append(dict(task.score_probe(probe['content'], turn), turn=turn,
                                            request_hash=probe['request_hash'], raw_answer=probe['content'],
                                            tokens_estimate=context_size(messages)))
            for cp in checkpoints:
                cp['pre_failure'] = not any(e['turn'] <= cp['turn'] for e in task.events)
                cp['constraint_next_k'] = int(any(cp['turn'] < e['turn'] <= cp['turn'] + 3
                    and e['category'] == 'constraint' for e in task.events))
                cp['any_failure_next_k'] = int(any(cp['turn'] < e['turn'] <= cp['turn'] + 3
                                                 for e in task.events))
            record = {'mode': 'live', 'version': 2, 'phase': 'development_calibration',
                      'model': model['key'], 'seed': seed, 'family': family, 'condition': condition,
                      'group': group, 'trajectory': trajectory, 'labels': task.labels(),
                      'trace': trace, 'checkpoints': checkpoints}
            atomic_json(output, record)
            records.append(record)
    result = dict(summarize(records), actual_spend_usd=client.ledger.export()['total_usd'])
    atomic_json(directory / 'report.json', result)
    atomic_json(directory / 'cost-ledger.json', client.ledger.export())
    return result
