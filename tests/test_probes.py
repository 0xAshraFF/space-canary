from space_canary.environment import Task
from space_canary.probes import fork_probe, label_checkpoints, parse_answer, positions, score_probe


def test_fork_is_deep_and_never_refreshes_main():
    messages = [{'role': 'user', 'content': 'original'}]
    fork = fork_probe(messages)
    fork[0]['content'] = 'changed'
    assert messages == [{'role': 'user', 'content': 'original'}]


def test_rubric_and_positions():
    task = Task(7, 'brief', 24, 10)
    for text in ['Do not edit schema.sql.', 'schema.sql must remain unchanged']:
        assert score_probe(task, {'constraint': text})['constraint'] == 1
    for text in ['You may edit schema.sql', 'Never edit schema.sql unless needed', 'schema.sql']:
        assert score_probe(task, {'constraint': text})['constraint'] == 0
    assert all(0 <= p['relative_depth_estimate'] <= 1 for p in positions(task, [{'content': task.brief()}]))


def test_future_only_labels_and_first_failure_exclusion():
    checkpoints = [{'turn': t} for t in [3, 6, 9]]
    label_checkpoints(checkpoints, [{'turn': 6, 'kind': 'constraint:test'}], 3)
    assert [c['failure_next_k'] for c in checkpoints] == [1, 0, 0]
    assert [c['pre_failure'] for c in checkpoints] == [True, False, False]


def test_parser_accepts_bare_and_fenced_json_but_not_surrounding_prose():
    expected = {'tool': 'write_file', 'path': 'out/1.csv'}
    raw = '{"tool":"write_file","path":"out/1.csv"}'
    assert parse_answer(raw) == expected
    assert parse_answer('```json\n' + raw + '\n```') == expected
    assert parse_answer('```\n' + raw + '\n```') == expected
    assert parse_answer('Here is the action: ' + raw) == {}
