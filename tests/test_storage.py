import pytest
from space_canary.storage import Ledger, BudgetExceeded


def test_total_cap_is_checked_before_dispatch_and_survives_restart(tmp_path):
    path = tmp_path / 'ledger.db'
    ledger = Ledger(path, total=1, frontier=.5)
    ledger.reserve('a', 'economical', .9)
    restarted = Ledger(path, total=1, frontier=.5)
    with pytest.raises(BudgetExceeded):
        restarted.reserve('b', 'economical', .11)
    with pytest.raises(RuntimeError):
        restarted.reserve('a', 'economical', .01)
    restarted.settle('a', .5)
    restarted.reserve('b', 'economical', .5)
    assert restarted.export()['total_usd'] == 1


def test_frontier_cap_and_invalid_costs(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    ledger.reserve('a', 'frontier', 8)
    with pytest.raises(BudgetExceeded):
        ledger.reserve('b', 'frontier', .000001)
    ledger.reserve('c', 'economical', 17)
    with pytest.raises(ValueError):
        ledger.settle('c', -1)
    with pytest.raises(BudgetExceeded):
        ledger.settle('c', 18)


def test_definitely_rejected_request_releases_reservation(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db', total=1, frontier=.5)
    ledger.reserve('a', 'economical', 1)
    ledger.reject('a', 'http_400')
    ledger.reserve('b', 'economical', 1)
    assert ledger.export()['total_usd'] == 1
