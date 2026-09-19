import copy
import json
from pathlib import Path
import yaml
from space_canary.runner import run_mock


def test_resume_and_replay_after_interruption(tmp_path):
    config = yaml.safe_load(Path('config.yaml').read_text())
    config['experiment']['mock_per_model'] = 2
    config['experiment']['turns'] = 9
    config['experiment']['filler_chars'] = 10
    first = run_mock(config, tmp_path)
    raw = (tmp_path / 'raw.jsonl').read_bytes()
    for file in (tmp_path / 'trajectories').glob('*.json'):
        file.unlink()
    replay = run_mock(config, tmp_path)
    assert replay['new_calls'] == 0
    assert replay['cache_hits'] == first['new_calls']
    assert raw == (tmp_path / 'raw.jsonl').read_bytes()
    assert run_mock(config, tmp_path)['new_calls'] == 0
    assert first['actual_spend_usd'] == 0


def test_config_change_cannot_reuse_results(tmp_path):
    import pytest
    config = yaml.safe_load(Path('config.yaml').read_text())
    config['experiment']['mock_per_model'] = 0
    run_mock(config, tmp_path)
    config['seed'] += 1
    with pytest.raises(RuntimeError, match='Configuration changed'):
        run_mock(config, tmp_path)
