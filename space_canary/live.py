"""OpenRouter calibration transport with pinned routing and pre-dispatch budgets."""
import copy
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .environment import Task
from .probes import context_size, fork_probe, label_checkpoints, parse_answer, positions, score_probe
from .storage import Ledger, atomic_json, digest
from .token_counting import InputTokenCounter


class LiveRunError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, directory, config, total_cap=None, frontier_cap=None):
        self.directory = Path(directory)
        self.config = config
        self.api_key = os.environ.get('OPENROUTER_API_KEY')
        if not self.api_key:
            raise LiveRunError('OPENROUTER_API_KEY is not set')
        self.ledger = Ledger(self.directory / 'ledger.sqlite',
                             config['budget_usd'] if total_cap is None else total_cap,
                             config['frontier_budget_usd'] if frontier_cap is None else frontier_cap)
        self.new_calls = 0
        self.cache_hits = 0
        self.token_counter = InputTokenCounter()
        self.last_dispatch = {}

    def _payload(self, messages, model):
        live = self.config['live_request']
        return {
            'model': model['id'],
            'messages': copy.deepcopy(messages),
            'temperature': live['temperature'],
            'max_tokens': self.config['experiment']['max_output_tokens'],
            'reasoning_effort': model['reasoning_effort'],
            'provider': {
                'only': [model['provider']],
                'allow_fallbacks': live['allow_fallbacks'],
                'require_parameters': True,
                'data_collection': live['data_collection'],
                'quantizations': [model['quantization']] if model['quantization'] != 'unknown' else None,
                'max_price': {
                    'prompt': model['input_per_million'],
                    'completion': model['output_per_million'],
                },
            },
        }

    def _upper_cost(self, messages, model):
        measurement = self.token_counter.count(messages, model)
        measured_input = measurement['tokens']
        if measured_input + self.config['experiment']['max_output_tokens'] > model['context_limit']:
            raise LiveRunError('Conservative input bound exceeds pinned endpoint context limit')
        output_upper = self.config['experiment']['max_output_tokens']
        cost = (measured_input * model['input_per_million'] +
                output_upper * model['output_per_million']) / 1_000_000
        return cost, measurement

    def call(self, messages, model, task, turn, kind, config_hash):
        payload = self._payload(messages, model)
        base_record = {'transport': 'openrouter', 'payload': payload, 'task_seed': task.seed,
                       'turn': turn, 'kind': kind, 'config_hash': config_hash}
        attempt = 0
        while True:
            request_record = dict(base_record)
            if attempt:
                request_record['retry_after_rejection'] = attempt
            request_hash = digest(request_record)
            cache_path = self.directory / 'cache' / (request_hash + '.json')
            if cache_path.exists():
                cached = json.loads(cache_path.read_text())
                if cached['request'] != request_record:
                    raise LiveRunError('Cache request mismatch')
                self.cache_hits += 1
                return cached['response']
            state = self.ledger.state(request_hash)
            if state and state.startswith('http_'):
                attempt += 1
                continue
            break

        upper_cost, measurement = self._upper_cost(messages, model)
        self.ledger.reserve(request_hash, model['tier'], upper_cost)
        # New OpenRouter accounts are limited to 20 Haiku requests/minute.
        minimum_interval = 3.1 if model['key'] == 'haiku' else 0
        previous = self.last_dispatch.get(model['key'])
        if previous is not None and minimum_interval:
            time.sleep(max(0, minimum_interval - (time.monotonic() - previous)))
        self.last_dispatch[model['key']] = time.monotonic()
        request = urllib.request.Request(
            self.config['live_request']['endpoint'],
            data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.api_key,
                     'Content-Type': 'application/json',
                     'HTTP-Referer': 'https://github.com/0xAshraFF/space-canary',
                     'X-OpenRouter-Title': 'space-canary'},
            method='POST')
        try:
            with urllib.request.urlopen(request, timeout=300) as raw:
                result = json.load(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            atomic_json(self.directory / 'errors' / (request_hash + '.json'),
                        {'request_hash': request_hash, 'status': exc.code, 'body': body})
            if exc.code in [400, 401, 403, 404, 422, 429]:
                self.ledger.reject(request_hash, f'http_{exc.code}')
                raise LiveRunError(f'Rejected before generation {request_hash}: HTTP {exc.code}: {body}') from exc
            raise LiveRunError(f'Uncertain paid request {request_hash}; no automatic retry: {exc}') from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            # The request may have reached the provider. Its full reservation is
            # intentionally retained and the caller must reconcile before retry.
            raise LiveRunError(f'Uncertain paid request {request_hash}; no automatic retry: {exc}') from exc

        choices = result.get('choices') or []
        if not choices:
            raise LiveRunError(f'Paid response {request_hash} had no choices; reservation retained')
        provider = result.get('provider')
        if provider and provider.casefold().replace(' ', '') != model['provider_display'].casefold().replace(' ', ''):
            raise LiveRunError(f'Pinned provider mismatch for {request_hash}: {provider!r}; reservation retained')
        usage = result.get('usage') or {}
        actual = usage.get('cost')
        if actual is None:
            actual = (int(usage.get('prompt_tokens', 0)) * model['input_per_million'] +
                      int(usage.get('completion_tokens', 0)) * model['output_per_million']) / 1_000_000
        response = {'content': choices[0].get('message', {}).get('content') or '',
                    'usage': usage, 'provider': provider, 'id': result.get('id'),
                    'request_hash': request_hash, 'actual_cost_usd': float(actual),
                    'pre_dispatch_measurement': measurement,
                    'reserved_cost_usd': upper_cost}
        atomic_json(cache_path, {'request': request_record, 'response': response})
        self.ledger.settle(request_hash, float(actual))
        self.new_calls += 1
        return response


def _run_model(config, output_dir, client, model):
    exp = config['experiment']
    records = []
    for index in range(exp['calibration_per_model']):
        family = ['brief', 'cleaning'][index % 2]
        seed = config['seed'] + index
        group = f'calibration-{seed}-{family}'
        trajectory = model['key'] + '-' + group
        output = output_dir / 'trajectories' / (trajectory + '.json')
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
                if digest(messages) != before:
                    raise LiveRunError('Probe contaminated the main context')
                checkpoints.append({'turn': turn, 'tokens_estimate': context_size(messages),
                                    'scores': score_probe(task, parse_answer(probe['content'])),
                                    'positions': positions(task, messages),
                                    'probe_answer': probe['content'], 'request_hash': probe['request_hash']})
        labels = task.labels()
        record = {'mode': 'live', 'model': model['key'], 'tier': model['tier'],
                  'trajectory': trajectory, 'group': group, 'family': family, 'seed': seed,
                  'phase': 'calibration', 'labels': labels, 'trace': trace,
                  'checkpoints': label_checkpoints(checkpoints, task.events, exp['horizon'])}
        atomic_json(output, record)
        records.append(record)
    return records


def _failure_breakdown(records):
    categories = {'context_or_constraint': 0, 'arithmetic_or_value': 0, 'format_or_action': 0}
    kinds = {}
    for record in records:
        for event in record['labels']['events']:
            kind = event['kind']
            kinds[kind] = kinds.get(kind, 0) + 1
            if kind.startswith('constraint:') or kind in ['task:wrong_multiplier', 'task:project_fact']:
                categories['context_or_constraint'] += 1
            elif kind == 'task:arithmetic_value':
                categories['arithmetic_or_value'] += 1
            else:
                categories['format_or_action'] += 1
    total = sum(categories.values())
    return {'events_by_kind': kinds, 'events_by_category': categories,
            'context_or_constraint_fraction': categories['context_or_constraint'] / total if total else None,
            'mostly_non_context': bool(total and categories['context_or_constraint'] <= total / 2)}


def run_calibration(config, directory):
    if not config.get('live_enabled'):
        raise LiveRunError('Live calls are locked: live_enabled is false')
    if not config.get('preregistration_commit'):
        raise LiveRunError('Missing preregistration commit')
    if not config.get('approval'):
        raise LiveRunError('Missing explicit allocation approval')
    if not config.get('paid_cost_approval'):
        raise LiveRunError('Missing explicit paid calibration cost approval')
    if config.get('calibration_stage') != 'A':
        raise LiveRunError('Only approved calibration Stage A is implemented')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {'mode': 'live', 'phase': 'calibration-stage-a', 'config': config}
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise LiveRunError('Configuration changed: use a new output directory')
    atomic_json(manifest_path, manifest)
    client = OpenRouterClient(directory, config, config['calibration_budget_usd'],
                              config['calibration_frontier_budget_usd'])
    records = []
    stage_keys = set(config['stage_a_models'])
    stage_models = [model for model in config['models'] if model['key'] in stage_keys]
    if {model['key'] for model in stage_models} != stage_keys:
        raise LiveRunError('Stage A model key is missing from config')
    if any(model['tier'] == 'frontier' for model in stage_models):
        raise LiveRunError('Stage A cannot dispatch a frontier model')
    for model in stage_models:
        records.extend(_run_model(config, directory, client, model))

    qualification = {}
    for model in stage_models:
        model_records = [r for r in records if r['model'] == model['key']]
        failures = sum(not r['labels']['task_success'] for r in model_records)
        rate = failures / len(model_records)
        qualification[model['key']] = {'failures': failures, 'trajectories': len(model_records),
                                       'failure_rate': rate,
                                       'failure_breakdown': _failure_breakdown(model_records),
                                       'analysis_role': 'descriptive_only' if model['tier'] == 'frontier' else 'candidate'}

    minimum = config['qualification']['minimum_failure_rate']
    maximum = config['qualification']['maximum_failure_rate']
    if qualification['glm']['failure_rate'] < minimum:
        fallback = config['fallback_models'][0]
        fallback_records = _run_model(config, directory, client, fallback)
        records.extend(fallback_records)
        failures = sum(not r['labels']['task_success'] for r in fallback_records)
        rate = failures / len(fallback_records)
        qualification['glm']['decision'] = 'replace_with_haiku'
        qualification['haiku'] = {'failures': failures, 'trajectories': len(fallback_records),
                                  'failure_rate': rate,
                                  'failure_breakdown': _failure_breakdown(fallback_records),
                                  'decision': 'qualifies' if minimum <= rate <= maximum else 'not_evaluable'}
    else:
        qualification['glm']['decision'] = ('qualifies' if qualification['glm']['failure_rate'] <= maximum
                                             else 'not_evaluable')
    qualification['deepseek']['decision'] = (
        'qualifies' if minimum <= qualification['deepseek']['failure_rate'] <= maximum else 'not_evaluable')
    qualification['opus'] = {'decision': 'stage_b_locked', 'trajectories': 0,
                             'analysis_role': 'descriptive_only'}

    raw = directory / 'raw.jsonl.tmp'
    raw.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
    raw.replace(directory / 'raw.jsonl')
    atomic_json(directory / 'qualification.json', qualification)
    atomic_json(directory / 'cost-ledger.json', client.ledger.export())
    return {'phase': 'calibration-stage-a', 'trajectories': len(records), 'qualification': qualification,
            'new_calls': client.new_calls, 'cache_hits': client.cache_hits,
            'actual_spend_usd': client.ledger.export()['total_usd']}


def run_haiku_recalibration(config, directory):
    repair = config.get('haiku_recalibration') or {}
    if not repair.get('live_enabled'):
        raise LiveRunError('Haiku recalibration is locked: live_enabled is false')
    if not repair.get('amendment_commit'):
        raise LiveRunError('Missing public parser-amendment commit')
    if not repair.get('paid_cost_approval'):
        raise LiveRunError('Missing explicit paid Haiku recalibration approval')
    if repair.get('frontier_budget_usd') != 0:
        raise LiveRunError('Haiku recalibration cannot allocate a frontier budget')

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {'mode': 'live', 'phase': 'haiku-recalibration', 'config': config}
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise LiveRunError('Configuration changed: use a new output directory')
    atomic_json(manifest_path, manifest)

    fallback_models = config.get('fallback_models') or []
    if len(fallback_models) != 1 or fallback_models[0].get('key') != 'haiku':
        raise LiveRunError('Expected exactly one pinned Haiku fallback model')
    model = fallback_models[0]
    if model.get('tier') != 'economical':
        raise LiveRunError('Haiku recalibration cannot dispatch a frontier model')
    client = OpenRouterClient(directory, config, repair['budget_usd'], 0)
    records = _run_model(config, directory, client, model)
    failures = sum(not record['labels']['task_success'] for record in records)
    rate = failures / len(records)
    minimum = config['qualification']['minimum_failure_rate']
    maximum = config['qualification']['maximum_failure_rate']
    qualification = {
        'haiku': {
            'failures': failures,
            'trajectories': len(records),
            'failure_rate': rate,
            'failure_breakdown': _failure_breakdown(records),
            'decision': 'qualifies' if minimum <= rate <= maximum else 'not_evaluable',
        },
        'deepseek': {'decision': 'not_evaluable_from_stage_a', 'failure_rate': 0.0},
        'opus': {'decision': 'stage_b_locked', 'trajectories': 0,
                 'analysis_role': 'descriptive_only'},
    }
    raw = directory / 'raw.jsonl.tmp'
    raw.write_text(''.join(json.dumps(record, sort_keys=True) + '\n' for record in records))
    raw.replace(directory / 'raw.jsonl')
    atomic_json(directory / 'qualification.json', qualification)
    atomic_json(directory / 'cost-ledger.json', client.ledger.export())
    return {'phase': 'haiku-recalibration', 'trajectories': len(records),
            'qualification': qualification, 'new_calls': client.new_calls,
            'cache_hits': client.cache_hits,
            'actual_spend_usd': client.ledger.export()['total_usd']}
