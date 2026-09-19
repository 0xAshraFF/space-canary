from space_canary.environment import Task


def test_both_families_can_succeed():
    for family in ['brief', 'cleaning']:
        task = Task(7, family, 24, 10)
        for turn in range(1, 25):
            task.apply(task.correct_action(turn), turn)
        assert task.labels()['task_success']
        assert task.database == task.original_db


def test_attempted_violation_is_recorded_even_if_later_repaired():
    task = Task(7, 'brief', 24, 10)
    task.apply({'tool': 'write_file', 'path': 'schema.sql', 'content': 'bad'}, 1)
    task.apply(task.correct_action(1), 1)
    assert not task.labels()['constraint_adherence']
    assert task.labels()['first_failure'] == 1


def test_seed_and_wrong_facts():
    a, b = Task(42, 'cleaning', 24, 10), Task(42, 'cleaning', 24, 10)
    assert a.prompt(1) == b.prompt(1)
    action = a.correct_action(1)
    action['content'] = action['content'].replace(a.project, 'wrong')
    a.apply(action, 1)
    assert not a.labels()['task_success']
    assert a.labels()['constraint_adherence']
