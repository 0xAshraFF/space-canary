import copy
import json
from pathlib import Path

import pytest
import yaml

from space_canary.environment_v2 import DelayedTask
from space_canary.pilot_v2 import FAMILIES, POLICIES, fixture_action, run_live_v2, validate_v2


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('policy,category', [
    ('oracle', None), ('forget_constraint', 'constraint'), ('stale_policy', 'policy_update'),
    ('corrupt_payload', 'delayed_dependency'), ('bad_schema', 'format_or_action')])
def test_delayed_outcomes_have_distinct_causes(family, policy, category):
    task = DelayedTask(42, family, filler_chars=10)
    for turn in range(1, 25):
        task.apply(fixture_action(task, turn, policy), turn)
    if category is None:
        assert task.labels()['task_success']
    else:
        assert task.labels()['first_failure'] == 13
        assert {e['category'] for e in task.events} == {category}
        assert [e['turn'] for e in task.events] == [13, 19, 24]


def test_pair_only_changes_policy_reminders():
    delayed = DelayedTask(42, FAMILIES[0], 'delayed', 100)
    refreshed = DelayedTask(42, FAMILIES[0], 'refreshed', 100)
    assert delayed.brief() == refreshed.brief()
    for turn in range(1, 25):
        a, b = json.loads(delayed.prompt(turn)), json.loads(refreshed.prompt(turn))
        reminder = b.pop('controller_policy_reminder', None)
        assert a == b
        assert bool(reminder) == (turn in refreshed.refresh_turns)
        if reminder:
            assert reminder == refreshed.policy(turn)
        assert delayed.expected(turn) == refreshed.expected(turn)
    assert 'protected_field' not in delayed.prompt(13)


def test_probe_isolation_and_invalid_schema_is_missing_not_forgetting():
    task = DelayedTask(42, FAMILIES[1])
    messages = [{'role': 'user', 'content': task.brief()}]
    original = copy.deepcopy(messages)
    fork = task.probe(messages)
    fork[0]['content'] = 'changed'
    assert messages == original
    wrong_keys = {'code': task.code, 'batch': task.updated_version, 'route': task.private_route}
    score = task.score_probe(json.dumps(wrong_keys), 12)
    assert score == {'schema_valid': False, 'scores': dict.fromkeys(['arbitrary', 'relevant', 'constraint'])}
    answer = json.dumps(task.probe_target(12))
    assert all(task.score_probe('```json\n' + answer + '\n```', 12)['scores'].values())


def test_attempted_violation_is_irreversible_and_duplicate_turn_rejected():
    task = DelayedTask(42, FAMILIES[0])
    task.apply(fixture_action(task, 13, 'forget_constraint'), 13)
    with pytest.raises(ValueError, match='replay'):
        task.apply(task.expected(13), 13)
    assert not task.labels()['constraint_adherence']
    assert not task.labels()['task_success']


def test_corrupted_value_separated_from_constraint_attempt():
    task = DelayedTask(42, FAMILIES[0])
    action = task.expected(13)
    action['changes'][next(iter(action['changes']))] = 'wrong'
    task.apply(action, 13)
    assert task.events == [{'turn': 13, 'category': 'delayed_dependency', 'kind': 'wrong_payload_value'}]


@pytest.mark.parametrize('family', FAMILIES)
def test_success_constructed_only_from_visible_controller_messages(family):
    task = DelayedTask(42, family, filler_chars=0)
    policy_text = task.brief().split('Initial policy: ')[1].split('\nDiagnostic code:')[0]
    policy = json.loads(policy_text)
    queued = {}
    for turn in range(1, 25):
        body = json.loads(task.prompt(turn))
        if 'POLICY_UPDATE' in body:
            policy.update(body['POLICY_UPDATE'])
        if 'queued_job' in body:
            queued[body['queued_job']['job_id']] = body['queued_job']
        if body['event'] == 'INDEX':
            action = {'tool': 'index', 'ids': [x['id'] for x in body['work_items']
                                              if x['status'] == 'ready']}
        else:
            job = queued[body['job_id']]
            action = {'job_id': job['job_id'], 'batch': policy['batch']}
            if family == 'protected_patch':
                action.update(tool='patch', changes={k: v for k, v in job['proposed_changes'].items()
                                                      if k != policy['protected_field']})
            else:
                action.update(tool='deliver', routes={r['id']: policy['private_route']
                    if r['topic'] == policy['restricted_topic'] else policy['public_route']
                    for r in job['reports']})
        task.apply(action, turn)
    assert task.labels()['task_success']


def test_v2_lock_precedes_client_construction(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('Client must not be constructed while locked')
    monkeypatch.setattr('space_canary.live.OpenRouterClient', forbidden)
    config = yaml.safe_load(Path('config.v2.yaml').read_text())
    with pytest.raises(RuntimeError, match='locked'):
        run_live_v2(config, tmp_path)


def test_v2_runner_reconstructs_partial_trajectory_from_cache(monkeypatch, tmp_path):
    from space_canary.storage import digest
    config = yaml.safe_load(Path('config.v2.yaml').read_text())
    config['v2'].update(live_enabled=True, paid_cost_approval='test', public_protocol_commit='test',
                        seeds=[42], filler_chars=10)
    config['models'] = config['models'][:1]
    cache = {}
    fresh = []

    class FakeClient:
        def __init__(self, *args):
            self.ledger = self

        def export(self):
            return {'total_usd': 0}

        def call(self, messages, model, task, turn, kind, config_hash):
            key = digest(messages)
            if key not in cache:
                fresh.append(key)
                answer = task.expected(turn) if kind == 'v2-action' else task.probe_target(turn)
                cache[key] = {'content': json.dumps(answer), 'request_hash': key,
                              'pre_dispatch_measurement': {'tokens': 1}}
            return cache[key]

    monkeypatch.setattr('space_canary.live.OpenRouterClient', FakeClient)
    first = run_live_v2(config, tmp_path)
    count = len(fresh)
    for path in (tmp_path / 'trajectories').glob('*.json'):
        path.unlink()
    second = run_live_v2(config, tmp_path)
    assert count == len(fresh)
    assert first == second
    assert first['models']['deepseek']['delayed']['failed_trajectories'] == 0
    groups = [json.loads(p.read_text())['group'] for p in (tmp_path / 'trajectories').glob('*.json')]
    assert len(set(groups)) == 2 and len(groups) == 4
