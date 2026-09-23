import argparse
import json
from pathlib import Path

import yaml

from .runner import estimate, run_mock
from .storage import atomic_json


def main():
    parser = argparse.ArgumentParser(description='Space Canary: offline pilot harness')
    parser.add_argument('command', choices=['dry-run', 'estimate', 'analyze', 'calibration',
                                            'recalibrate-haiku', 'validate-v2', 'estimate-v2', 'calibrate-v2', 'main'])
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--output', default='results/mock')
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    if args.command in ['validate-v2', 'estimate-v2', 'calibrate-v2']:
        from .pilot_v2 import validate_v2, estimate_v2, run_live_v2
        run = {'validate-v2': validate_v2, 'estimate-v2': estimate_v2,
               'calibrate-v2': run_live_v2}[args.command]
        print(json.dumps(run(config, args.output), indent=2))
        return
    if args.command == 'main':
        parser.error('Main collection is locked until calibration qualification has been reviewed.')
    if args.command == 'calibration':
        from .live import run_calibration
        print(json.dumps(run_calibration(config, args.output), indent=2))
        return
    if args.command == 'recalibrate-haiku':
        from .live import run_haiku_recalibration
        print(json.dumps(run_haiku_recalibration(config, args.output), indent=2))
        return
    if args.command in ['dry-run', 'estimate']:
        report = estimate(config)
        atomic_json(Path(args.output) / 'cost-estimate.json', report)
        print(json.dumps(report, indent=2))
    if args.command == 'dry-run':
        print(json.dumps(run_mock(config, args.output), indent=2))
    if args.command == 'analyze':
        from .analysis import analyze
        print(json.dumps(analyze(config, args.output), indent=2))


if __name__ == '__main__':
    main()
