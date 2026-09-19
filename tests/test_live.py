import json
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
