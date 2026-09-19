import argparse
import json
from pathlib import Path

import yaml

from .runner import estimate, run_mock
from .storage import atomic_json


def main():
    parser = argparse.ArgumentParser(description='Space Canary: offline pilot harness')
    parser.add_argument('command', choices=['dry-run', 'estimate', 'analyze', 'calibration', 'main'])
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--output', default='results/mock')
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    if args.command in ['calibration', 'main']:
        parser.error('Paid transport is not enabled in the dry-run milestone. Review and commit PREREGISTRATION.md, '
                     'approve a provider-pinned cost estimate, then implement/validate live dispatch guards.')
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
