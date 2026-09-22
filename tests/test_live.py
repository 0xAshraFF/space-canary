import json
import io
import urllib.error
from pathlib import Path

import pytest
import yaml

from space_canary.environment import Task
from space_canary.live import LiveRunError, OpenRouterClient, run_calibration


def config():
    value = yaml.safe_load(Path('config.glm.yaml').read_text())
    value['budget_usd'] = 1
    value['frontier_budget_usd'] = .5
    return value


def test_live_lock_blocks_before_client_or_network(tmp_path):
    value = config()
    value['live_enabled'] = False
    with pytest.raises(LiveRunError, match='locked'):
        run_calibration(value, tmp_path)


def test_calibration_uses_narrow_caps(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret')
    value = config()
    client = OpenRouterClient(tmp_path, value, value['calibration_budget_usd'],
                              value['calibration_frontier_budget_usd'])
    assert client.ledger.total == 2_400_000
    assert client.ledger.frontier == 0


def test_payload_pins_provider_price_and_no_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret')
    value = config()
    client = OpenRouterClient(tmp_path, value)
    model = value['models'][0]
    payload = client._payload([{'role': 'user', 'content': 'hello'}], model)
    assert payload['provider']['only'] == ['baidu']
    assert payload['provider']['allow_fallbacks'] is False
    assert payload['provider']['max_price'] == {'prompt': .8918, 'completion': 2.8028}
    assert payload['reasoning_effort'] == 'low'
    assert 'test-secret' not in json.dumps(payload)
    cost, measurement = client._upper_cost([{'role': 'user', 'content': 'hello'}], model)
    assert cost > 0
    assert measurement['tokens'] > 0


def test_hash_changes_with_provider_and_context(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret')
    value = config()
    client = OpenRouterClient(tmp_path, value)
    model = value['models'][0]
    first = client._payload([{'role': 'user', 'content': 'a'}], model)
    second = client._payload([{'role': 'user', 'content': 'b'}], model)
    assert first != second
    task = Task(1, 'brief', 24, 10)
    cost, _ = client._upper_cost([{'role': 'user', 'content': task.brief()}], model)
    assert cost < value['budget_usd']


def test_rate_limit_is_rejected_and_next_call_uses_audited_retry(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret')
    value = config()
    client = OpenRouterClient(tmp_path, value)
    model = value['fallback_models'][0]
    monkeypatch.setattr(client, '_upper_cost', lambda messages, selected: (.01, {'tokens': 1}))
    replies = [
        urllib.error.HTTPError('https://example.test', 429, 'rate limited', {},
                               io.BytesIO(b'{"error":{"message":"rate limit"}}')),
        io.BytesIO(json.dumps({'choices': [{'message': {'content': '{}'}}],
                                  'provider': 'Anthropic', 'id': 'generation-1',
                                  'usage': {'cost': .001}}).encode()),
    ]

    def fake_urlopen(request, timeout):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    task = Task(1, 'brief', 24, 10)
    messages = [{'role': 'user', 'content': task.brief()}]
    with pytest.raises(LiveRunError, match='Rejected before generation'):
        client.call(messages, model, task, 1, 'action', 'config')
    response = client.call(messages, model, task, 1, 'action', 'config')
    assert response['id'] == 'generation-1'
    states = [row['state'] for row in client.ledger.export()['requests']]
    assert states == ['http_429', 'complete'] or states == ['complete', 'http_429']
