import numpy as np
from space_canary.analysis import alarm_threshold, warning_metrics, delta_interval


def test_warning_counts_misses_and_healthy_alarms():
    rows = [{'group': 'a', 'turn': 3, 'first_failure': 5},
            {'group': 'b', 'turn': 3, 'first_failure': 7},
            {'group': 'c', 'turn': 3, 'first_failure': None}]
    metrics = warning_metrics(rows, [True, True, True], 3)
    assert metrics['failure_recall'] == .5
    assert metrics['trajectory_false_alarm_rate'] == 1
    assert metrics['mean_lead_turns_among_detected'] == 2


def test_alarm_threshold_uses_trajectory_maxima_and_abstains_without_negatives():
    rows = [{'group': 'a', 'first_failure': None}, {'group': 'a', 'first_failure': None}]
    assert alarm_threshold([.1, .9], rows, .1) > .9
    assert alarm_threshold([.1], [{'group': 'b', 'first_failure': 4}], .1) == float('inf')


def test_identical_predictors_have_zero_delta():
    rows = [{'group': str(i // 2), 'failure_next_k': i % 2} for i in range(20)]
    pred = np.array([r['failure_next_k'] * .8 + .1 for r in rows])
    result = delta_interval(rows, pred, pred, 100, 3)
    assert result['delta_auc'] == 0
    assert result['ci'] == [0, 0]
