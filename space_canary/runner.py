"""Offline checkpoint runner. This milestone intentionally has no paid transport."""
import copy
import json
import random
from pathlib import Path

from .environment import Task
from .probes import context_size, fork_probe, label_checkpoints, parse_answer, positions, score_probe
from .storage import Ledger, atomic_json, digest


PROTOCOL_VERSION = 1


class MockClient:
    """Scripted fixture with synthetic correlated failures, not a language model."""
    def __init__(self, directory, config):
        self.directory = Path(directory)
        self.ledger = Ledger(self.directory / 'ledger.sqlite', config['budget_usd'], config['frontier_budget_usd'])
        self.new_calls = 0
        self.cache_hits = 0

    def call(self, messages, model, task, turn, kind, config_hash):
        request = {'protocol': PROTOCOL_VERSION, 'mode': 'mock', 'model': model['id'],
                   'seed': task.seed, 'turn': turn, 'kind': kind, 'messages': copy.deepcopy(messages),
                   'config_hash': config_hash}
        request_hash = digest(request)
        path = self.directory / 'cache' / (request_hash + '.json')
        if path.exists():
            cached = json.loads(path.read_text())
            if cached['request'] != request:
                raise RuntimeError('Cache request mismatch')
            self.ledger.settle(request_hash, 0)
            self.cache_hits += 1
            return cached['response']
        self.ledger.reserve(request_hash, model['tier'], 0)
        rng = random.Random(task.seed + (100 if model['tier'] == 'frontier' else 0))
        vulnerable = rng.random() < (0.2 if model['tier'] == 'frontier' else 0.6)
        onset = rng.randrange(5, task.turns)
        if kind == 'probe':
            answer = {'arbitrary': task.code, 'relevant': str(task.multiplier),
                      'constraint': 'Do not edit schema.sql'}
            if vulnerable and turn >= onset - config_probe_lead():
                answer[rng.choice(['arbitrary', 'relevant', 'constraint'])] = 'unknown'
        else:
            answer = task.correct_action(turn)
            if vulnerable and turn >= onset:
                if task.seed % 2:
                    answer = {'tool': 'write_file', 'path': 'schema.sql', 'content': 'changed'}
                else:
                    answer['content'] = answer['content'].replace(task.project, 'WRONG')
        response = {'content': json.dumps(answer), 'usage': {'input_tokens_estimate': context_size(messages)},
                    'mode': 'mock', 'request_hash': request_hash, 'actual_cost_usd': 0}
        atomic_json(path, {'request': request, 'response': response})
        self.ledger.settle(request_hash, 0)
        self.new_calls += 1
        return response


def config_probe_lead():
    # Manufactured warning in the fixture exercises analysis, never scientific evidence.
    return 3


def run_mock(config, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {'mode': 'mock', 'config': config, 'protocol': PROTOCOL_VERSION}
    path = directory / 'manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise RuntimeError('Configuration changed: use a new output directory')
    atomic_json(path, manifest)
    client = MockClient(directory, config)
    exp = config['experiment']
    records = []
    for model in config['models']:
        for index in range(exp['mock_per_model']):
            family = ['brief', 'cleaning'][index % 2]
            # Same base instance across models. All its checkpoints share this group.
            seed = config['seed'] + index
            group = f'mock-{seed}-{family}'
            trajectory = model['key'] + '-' + group
            output = directory / 'trajectories' / (trajectory + '.json')
            if output.exists():
                records.append(json.loads(output.read_text()))
                continue
            task = Task(seed, family, exp['turns'], exp['filler_chars'])
            messages = [{'role': 'user', 'content': task.brief()}]
            checkpoints, trace = [], []
            for turn in range(1, exp['turns'] + 1):
                messages.append({'role': 'user', 'content': task.prompt(turn)})
                response = client.call(messages, model, task, turn, 'action', digest(config))
                action = parse_answer(response['content'])
                messages.append({'role': 'assistant', 'content': response['content']})
                observation = task.apply(action, turn)
                messages.append({'role': 'user', 'content': json.dumps({'tool_result': observation})})
                trace.append({'turn': turn, 'action': action, 'request_hash': response['request_hash']})
                if turn % exp['checkpoint_every'] == 0 and turn + exp['horizon'] <= exp['turns']:
                    before = digest(messages)
                    probe = client.call(fork_probe(messages), model, task, turn, 'probe', digest(config))
                    assert digest(messages) == before, 'Probe contaminated main context'
                    checkpoints.append({'turn': turn, 'tokens_estimate': context_size(messages),
                                        'scores': score_probe(task, parse_answer(probe['content'])),
                                        'positions': positions(task, messages),
                                        'probe_answer': probe['content'], 'request_hash': probe['request_hash']})
            labels = task.labels()
            record = {'mode': 'mock', 'model': model['key'], 'tier': model['tier'],
                      'trajectory': trajectory, 'group': group, 'family': family, 'seed': seed,
                      'phase': 'mock', 'labels': labels, 'trace': trace,
                      'checkpoints': label_checkpoints(checkpoints, task.events, exp['horizon'])}
            atomic_json(output, record)
            records.append(record)
    # Derived export; rebuilding from completed records makes resume idempotent.
    tmp = directory / 'raw.jsonl.tmp'
    tmp.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
    tmp.replace(directory / 'raw.jsonl')
    atomic_json(directory / 'cost-ledger.json', client.ledger.export())
    return {'mode': 'mock', 'trajectories': len(records), 'new_calls': client.new_calls,
            'cache_hits': client.cache_hits, 'actual_spend_usd': client.ledger.export()['total_usd']}


def estimate(config):
    """Planning estimate using successful fixture traces, no network or keys."""
    exp = config['experiment']
    task = Task(config['seed'], 'cleaning', exp['turns'], exp['filler_chars'])
    messages = [{'role': 'user', 'content': task.brief()}]
    input_tokens, calls = 0, 0
    for turn in range(1, exp['turns'] + 1):
        messages.append({'role': 'user', 'content': task.prompt(turn)})
        input_tokens += context_size(messages)
        calls += 1
        messages.append({'role': 'assistant', 'content': json.dumps(task.correct_action(turn))})
        messages.append({'role': 'user', 'content': json.dumps({'tool_result': {'accepted': True}})})
        if turn % exp['checkpoint_every'] == 0 and turn + exp['horizon'] <= exp['turns']:
            input_tokens += context_size(fork_probe(messages))
            calls += 1
    rows = []
    for model in config['models']:
        count = exp['main_frontier'] if model['tier'] == 'frontier' else exp['main_economical']
        cost = (input_tokens * model['input_per_million'] + calls * exp['max_output_tokens'] * model['output_per_million']) / 1e6
        rows.append({'model': model['key'], 'tier': model['tier'], 'calls_per_trajectory': calls,
                     'estimated_input_tokens_per_trajectory': input_tokens,
                     'calibration_trajectories': exp['calibration_per_model'], 'main_trajectories': count,
                     'calibration_usd': round(cost * exp['calibration_per_model'], 6),
                     'main_usd': round(cost * count, 6)})
    total = sum(r['calibration_usd'] + r['main_usd'] for r in rows)
    frontier = sum(r['calibration_usd'] + r['main_usd'] for r in rows if r['tier'] == 'frontier')
    fallback = None
    if config.get('fallback_models'):
        model = config['fallback_models'][0]
        count = exp['calibration_per_model']
        cost = (input_tokens * model['input_per_million'] +
                calls * exp['max_output_tokens'] * model['output_per_million']) / 1e6
        fallback = {'model': model['key'], 'conditional_calibration_trajectories': count,
                    'conditional_calibration_usd': round(cost * count, 6)}
    return {'kind': 'planning_estimate_not_quote_or_spending_authorization', 'models': rows,
            'estimated_total_usd': round(total, 4), 'estimated_frontier_usd': round(frontier, 4),
            'conditional_fallback': fallback,
            'estimated_calibration_usd': round(sum(r['calibration_usd'] for r in rows), 4),
            'estimated_calibration_with_fallback_usd': round(
                sum(r['calibration_usd'] for r in rows) +
                (fallback['conditional_calibration_usd'] if fallback else 0), 4),
            'within_planning_caps': total <= config['budget_usd'] and frontier <= config['frontier_budget_usd'],
            'assumptions': ['UTF-8/4 input estimate from successful fixture traces',
                            'Maximum configured output tokens per call',
                            'No prompt-cache discounts or retries',
                            'No calibration retuning rounds included',
                            'Input estimates are not safe upper bounds for enforcing live budgets',
                            ('Providers pinned in config with fallbacks disabled' if
                             all(m.get('provider') for m in config['models']) else
                             'Backend not yet pinned')]}
