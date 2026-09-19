"""Transactional reservations: unresolved requests retain their full charge."""
import hashlib
import json
import os
import sqlite3
from decimal import Decimal, ROUND_CEILING
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def micros(dollars):
    amount = Decimal(str(dollars))
    if not amount.is_finite() or amount < 0:
        raise ValueError('Cost must be finite and nonnegative')
    return int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING))


class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    def __init__(self, path, total=25, frontier=8):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.execute('CREATE TABLE IF NOT EXISTS requests '
                        '(hash TEXT PRIMARY KEY, tier TEXT, reserved INTEGER, charged INTEGER, state TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS limits (total INTEGER, frontier INTEGER)')
        existing = self.db.execute('SELECT total,frontier FROM limits').fetchone()
        limits = (micros(total), micros(frontier))
        if existing and existing != limits:
            raise ValueError('Ledger caps cannot change on resume')
        if not existing:
            self.db.execute('INSERT INTO limits VALUES (?,?)', limits)
        self.db.commit()
        self.total, self.frontier = limits

    def reserve(self, request_hash, tier, upper_usd):
        if tier not in ['economical', 'frontier']:
            raise ValueError('Unknown tier')
        upper = micros(upper_usd)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.db.execute('SELECT 1 FROM requests WHERE hash=?', (request_hash,)).fetchone():
                raise RuntimeError('Request already reserved; recover cache or reconcile, never blindly retry')
            total, frontier = self.db.execute(
                "SELECT COALESCE(SUM(charged),0), COALESCE(SUM(CASE WHEN tier='frontier' THEN charged ELSE 0 END),0) FROM requests"
            ).fetchone()
            if total + upper > self.total or (tier == 'frontier' and frontier + upper > self.frontier):
                raise BudgetExceeded('Request refused before dispatch: budget would be exceeded')
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',
                            (request_hash, tier, upper, upper, 'pending'))

    def settle(self, request_hash, actual_usd):
        actual = micros(actual_usd)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT reserved FROM requests WHERE hash=?', (request_hash,)).fetchone()
            if not row:
                raise RuntimeError('Cannot settle an unreserved request')
            if actual > row[0]:
                raise BudgetExceeded('Actual cost exceeded reserved bound; retain reservation and halt for reconciliation')
            self.db.execute("UPDATE requests SET charged=?, state='complete' WHERE hash=?", (actual, request_hash))

    def reject(self, request_hash, reason='rejected'):
        if not reason.startswith('http_') and reason != 'manually_reconciled_rejected':
            raise ValueError('Invalid rejection reason')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT state FROM requests WHERE hash=?', (request_hash,)).fetchone()
            if not row:
                raise RuntimeError('Cannot reject an unreserved request')
            if row[0] == 'complete':
                raise RuntimeError('Cannot reject a completed request')
            self.db.execute('UPDATE requests SET charged=0, state=? WHERE hash=?', (reason, request_hash))

    def export(self):
        rows = self.db.execute('SELECT hash,tier,reserved,charged,state FROM requests ORDER BY hash').fetchall()
        return {'total_usd': sum(r[3] for r in rows) / 1e6,
                'frontier_usd': sum(r[3] for r in rows if r[1] == 'frontier') / 1e6,
                'requests': [dict(zip(['hash', 'tier', 'reserved_microusd', 'charged_microusd', 'state'], r)) for r in rows]}
