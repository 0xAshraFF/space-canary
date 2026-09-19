"""OpenRouter calibration transport with pinned routing and pre-dispatch budgets."""
import copy
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .environment import Task
from .probes import context_size, fork_probe, label_checkpoints, parse_answer, positions, score_probe
from .storage import Ledger, atomic_json, digest


class LiveRunError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, directory, config):
        self.directory = Path(directory)
        self.config = config
        self.api_key = os.environ.get('OPENROUTER_API_KEY')
        if not self.api_key:
            raise LiveRunError('OPENROUTER_API_KEY is not set')
        self.ledger = Ledger(self.directory / 'ledger.sqlite', config['budget_usd'], config['frontier_budget_usd'])
        self.new_calls = 0
        self.cache_hits = 0

    def _payload(self, messages, model):
        live = self.config['live_request']
        return {
            'model': model['id'],
            'messages': copy.deepcopy(messages),
            'temperature': live['temperature'],
            'max_tokens': self.config['experiment']['max_output_tokens'],
            'reasoning': {'enabled': live['reasoning_enabled']},
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

    def _upper_cost(self, payload, model):
        # Every tokenizer token consumes at least one serialized UTF-8 byte. The
        # 8K allowance covers provider-rendered framing not present in the JSON.
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        input_upper = len(serialized) + 8192
        if input_upper > model['context_limit']:
            raise LiveRunError('Conservative input bound exceeds pinned endpoint context limit')
        output_upper = self.config['experiment']['max_output_tokens']
        return (input_upper * model['input_per_million'] +
                output_upper * model['output_per_million']) / 1_000_000

    def call(self, messages, model, task, turn, kind, config_hash):
        payload = self._payload(messages, model)
        request_record = {'transport': 'openrouter', 'payload': payload, 'task_seed': task.seed,
                          'turn': turn, 'kind': kind, 'config_hash': config_hash}
        request_hash = digest(request_record)
        cache_path = self.directory / 'cache' / (request_hash + '.json')
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if cached['request'] != request_record:
                raise LiveRunError('Cache request mismatch')
            self.cache_hits += 1
            return cached['response']

        self.ledger.reserve(request_hash, model['tier'], self._upper_cost(payload, model))
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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
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
                    'request_hash': request_hash, 'actual_cost_usd': float(actual)}
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


def run_calibration(config, directory):
    if not config.get('live_enabled'):
        raise LiveRunError('Live calls are locked: live_enabled is false')
    if not config.get('preregistration_commit'):
        raise LiveRunError('Missing preregistration commit')
    if not config.get('approval'):
        raise LiveRunError('Missing explicit allocation approval')
    if not config.get('paid_cost_approval'):
        raise LiveRunError('Missing explicit paid calibration cost approval')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {'mode': 'live', 'phase': 'calibration', 'config': config}
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise LiveRunError('Configuration changed: use a new output directory')
    atomic_json(manifest_path, manifest)
    client = OpenRouterClient(directory, config)
    records = []
    for model in config['models']:
        records.extend(_run_model(config, directory, client, model))

    qualification = {}
    for model in config['models']:
        model_records = [r for r in records if r['model'] == model['key']]
        failures = sum(not r['labels']['task_success'] for r in model_records)
        rate = failures / len(model_records)
        qualification[model['key']] = {'failures': failures, 'trajectories': len(model_records),
                                       'failure_rate': rate,
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
                                  'decision': 'qualifies' if minimum <= rate <= maximum else 'not_evaluable'}
    else:
        qualification['glm']['decision'] = ('qualifies' if qualification['glm']['failure_rate'] <= maximum
                                             else 'not_evaluable')
    qualification['deepseek']['decision'] = (
        'qualifies' if minimum <= qualification['deepseek']['failure_rate'] <= maximum else 'not_evaluable')
    qualification['opus']['decision'] = 'descriptive_only'

    raw = directory / 'raw.jsonl.tmp'
    raw.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
    raw.replace(directory / 'raw.jsonl')
    atomic_json(directory / 'qualification.json', qualification)
    atomic_json(directory / 'cost-ledger.json', client.ledger.export())
    return {'phase': 'calibration', 'trajectories': len(records), 'qualification': qualification,
            'new_calls': client.new_calls, 'cache_hits': client.cache_hits,
            'actual_spend_usd': client.ledger.export()['total_usd']}
