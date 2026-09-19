"""Grouped out-of-fold diagnostics. Mock data can never produce a research PASS."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .storage import atomic_json


def features(rows, types=()):
    return np.array([[np.log1p(r['tokens_estimate']), np.log1p(r['tokens_estimate']) ** 2,
                      r['turn'], int(r['family'] == 'cleaning')]
                     + [r['scores'][kind] for kind in types] for r in rows], dtype=float)


def fit_predict(x, y, test):
    if len(set(y)) < 2:
        return np.full(len(test), float(np.mean(y)))
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1000, random_state=0))
    model.fit(x, y)
    return model.predict_proba(test)[:, 1]


def alarm_threshold(scores, rows, target):
    # Threshold trained using maximum score of completely failure-free trajectories.
    negatives = {}
    for score, row in zip(scores, rows):
        if row['first_failure'] is None:
            negatives[row['group']] = max(negatives.get(row['group'], -1), float(score))
    if not negatives:
        return float('inf')
    values = np.array(list(negatives.values()))
    for threshold in sorted(set(values.tolist())):
        threshold = float(np.nextafter(threshold, np.inf))
        if np.mean(values >= threshold) <= target:
            return threshold
    return float('inf')


def oof(rows, types, folds, target):
    groups = np.array([r['group'] for r in rows])
    x = features(rows, types)
    y = np.array([r['failure_next_k'] for r in rows])
    predictions = np.full(len(rows), np.nan)
    alarms = np.zeros(len(rows), dtype=bool)
    n = min(folds, len(set(groups)))
    if n < 2:
        return predictions, alarms
    for train, test in GroupKFold(n_splits=n).split(x, y, groups):
        assert not set(groups[train]) & set(groups[test])
        predictions[test] = fit_predict(x[train], y[train], x[test])
        # Inner grouped OOF predictions avoid selecting thresholds on fitted scores.
        inner = np.full(len(train), np.nan)
        inner_groups = groups[train]
        inner_n = min(folds, len(set(inner_groups)))
        if inner_n < 2:
            continue
        for itrain, ival in GroupKFold(inner_n).split(x[train], y[train], inner_groups):
            inner[ival] = fit_predict(x[train][itrain], y[train][itrain], x[train][ival])
        threshold = alarm_threshold(inner, [rows[i] for i in train], target)
        alarms[test] = predictions[test] >= threshold
    return predictions, alarms


def delta_interval(rows, baseline, augmented, samples, seed, confidence=.95):
    y = np.array([r['failure_next_k'] for r in rows])
    if len(set(y)) < 2 or not np.isfinite(baseline).all() or not np.isfinite(augmented).all():
        return None
    group_names = sorted(set(r['group'] for r in rows))
    indices = {g: np.array([i for i, r in enumerate(rows) if r['group'] == g]) for g in group_names}
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(samples):
        chosen = rng.choice(group_names, len(group_names), replace=True)
        selected = np.concatenate([indices[g] for g in chosen])
        if len(set(y[selected])) == 2:
            deltas.append(roc_auc_score(y[selected], augmented[selected]) - roc_auc_score(y[selected], baseline[selected]))
    if len(deltas) < samples // 2:
        return None
    alpha = (1 - confidence) / 2
    return {'delta_auc': float(roc_auc_score(y, augmented) - roc_auc_score(y, baseline)),
            'ci': np.quantile(deltas, [alpha, 1-alpha]).tolist(),
            'confidence': confidence, 'valid_bootstraps': len(deltas),
            'baseline_auc': float(roc_auc_score(y, baseline)),
            'augmented_auc': float(roc_auc_score(y, augmented))}


def descriptive_auc(rows, baseline, augmented):
    y = np.array([r['failure_next_k'] for r in rows])
    if len(set(y)) < 2 or not np.isfinite(baseline).all() or not np.isfinite(augmented).all():
        return None
    base = float(roc_auc_score(y, baseline))
    aug = float(roc_auc_score(y, augmented))
    return {'delta_auc': aug - base, 'baseline_auc': base, 'augmented_auc': aug,
            'ci': None, 'descriptive_only': True}


def warning_metrics(rows, alarms, horizon):
    grouped = {}
    for row, alarm in zip(rows, alarms):
        grouped.setdefault(row['group'], []).append((row, alarm))
    failed, healthy, detected, false_alarms, lead = 0, 0, 0, 0, []
    for group in grouped.values():
        failure = group[0][0]['first_failure']
        if failure is None:
            healthy += 1
            false_alarms += int(any(alarm for _, alarm in group))
        else:
            failed += 1
            warnings = [r['turn'] for r, alarm in group if alarm and 0 < failure-r['turn'] <= horizon]
            if warnings:
                detected += 1
                lead.append(failure-min(warnings))
    return {'failed_trajectories_with_checkpoints': failed, 'healthy_trajectories': healthy,
            'failure_recall': detected / failed if failed else None,
            'trajectory_false_alarm_rate': false_alarms / healthy if healthy else None,
            'mean_lead_turns_among_detected': float(np.mean(lead)) if lead else None}


def analyze(config, directory):
    directory = Path(directory)
    records = [json.loads(line) for line in (directory / 'raw.jsonl').read_text().splitlines()]
    if any(record['mode'] != 'mock' for record in records):
        raise ValueError('This analysis milestone is only validated on mock fixtures')
    exp = config['experiment']
    results, plotted = {}, []
    for model in config['models']:
        rows = []
        for record in records:
            if record['model'] != model['key']:
                continue
            for cp in record['checkpoints']:
                if cp['pre_failure']:
                    rows.append(dict(cp, group=record['group'], family=record['family'],
                                     first_failure=record['labels']['first_failure']))
        if not rows:
            results[model['key']] = {'status': 'not_evaluable'}
            continue
        base, base_alarms = oof(rows, (), exp['folds'], exp['false_alarm_target'])
        per_type = {}
        for types in [('arbitrary',), ('relevant',), ('constraint',), ('arbitrary', 'relevant', 'constraint')]:
            aug, alarms = oof(rows, types, exp['folds'], exp['false_alarm_target'])
            name = '+'.join(types)
            auc = (descriptive_auc(rows, base, aug) if model['tier'] == 'frontier' else
                   delta_interval(rows, base, aug, exp['bootstrap_samples'], config['seed']))
            per_type[name] = {'auc': auc,
                              'gate2': warning_metrics(rows, alarms, exp['horizon'])}
            if len(types) == 3 and model['tier'] != 'frontier':
                per_type[name]['decision_interval'] = delta_interval(
                    rows, base, aug, exp['bootstrap_samples'], config['seed'], confidence=.975)
                if per_type[name]['auc']:
                    plotted.append((model['key'], per_type[name]['auc']))
        results[model['key']] = {'status': 'mock_only', 'checkpoints': len(rows),
                                  'trajectories': len(set(r['group'] for r in rows)),
                                  'baseline_gate2': warning_metrics(rows, base_alarms, exp['horizon']),
                                  'variants': per_type}
    report = {'mode': 'mock', 'verdict': 'INCONCLUSIVE',
              'reason': 'Scripted mock responses; no empirical evidence about language models.',
              'endpoint': 'any failure within K turns, pre-first-failure checkpoints only',
              'ci_limitation': 'Cluster bootstrap of fixed OOF predictions; does not refit models per bootstrap.',
              'models': results}
    atomic_json(directory / 'analysis.json', report)
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, (name, result) in enumerate(plotted):
        low, high = result['ci']
        ax.plot([low, high], [i, i], color='steelblue')
        ax.scatter([result['delta_auc']], [i], label=name)
    ax.set_yticks(range(len(plotted)))
    ax.set_yticklabels([name for name, _ in plotted])
    ax.axvline(.05, color='gray', linestyle='--')
    ax.set(xlabel='Delta AUROC (95% cluster interval)', title='MOCK ONLY — not research evidence')
    fig.tight_layout()
    fig.savefig(directory / 'delta-auc.png', dpi=150)
    plt.close(fig)
    for plot_kind in ['depth', 'time']:
        fig, ax = plt.subplots(figsize=(7, 4))
        for kind in ['arbitrary', 'relevant', 'constraint']:
            x, y = [], []
            for record in records:
                for cp in record['checkpoints']:
                    x.append(next(p['relative_depth_estimate'] for p in cp['positions'] if p['type'] == kind)
                             if plot_kind == 'depth' else cp['turn'])
                    y.append(cp['scores'][kind])
            ax.scatter(x, y, s=8, alpha=.2, label=kind)
        if plot_kind == 'time':
            times = sorted(set(c['turn'] for r in records for c in r['checkpoints']))
            rates = [np.mean([c['failure_next_k'] for r in records for c in r['checkpoints'] if c['turn'] == t]) for t in times]
            ax.plot(times, rates, color='black', label='failure within K turns')
        ax.set(title='MOCK ONLY — recall and scripted failures',
               xlabel='Estimated relative depth' if plot_kind == 'depth' else 'Turn', ylabel='Recall / failure rate')
        ax.legend()
        fig.tight_layout()
        fig.savefig(directory / ('recall-' + plot_kind + '.png'), dpi=150)
        plt.close(fig)
    lines = ['# Findings — mock dry run', '', '**Verdict: INCONCLUSIVE. No paid/model experiment has run.**', '',
             f'{len(records)} scripted trajectories; manufactured probe/failure correlation. Actual API spend: $0.', '',
             '| Mock model | Delta AUROC | 95% interval |', '| --- | ---: | --- |']
    for name, result in plotted:
        lines.append(f"| {name} | {result['delta_auc']:.3f} | [{result['ci'][0]:.3f}, {result['ci'][1]:.3f}] |")
    descriptive = []
    for name, model_result in results.items():
        auc = model_result.get('variants', {}).get('arbitrary+relevant+constraint', {}).get('auc')
        if auc and auc.get('descriptive_only'):
            descriptive.append(f"{name}: mock delta AUROC {auc['delta_auc']:.3f}, descriptive only; no interval")
    if descriptive:
        lines += ['', *descriptive]
    lines += ['', 'Gate 2 metrics and per-type ablations are in results/mock/analysis.json. '
              'These describe a scripted fixture only. The fixture deliberately includes warnings before failures.', '',
              'The cost estimate exceeds both requested caps; a paid run must be resized or repriced first. '
              'Provider tokenization, live transport, provider pinning and scientific sample sufficiency remain unvalidated.']
    (directory / 'FINDINGS.md').write_text('\n'.join(lines) + '\n')
    return report
