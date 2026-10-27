#!/usr/bin/env python3
"""Offline power audit, width candidates and multi-width route search.

No EDA access. Exit 0 is only a covered model result/candidate, never live proof;
1 means an unmet modeled requirement, 2 incomplete or invalid inputs.
"""
import argparse
import sys
from power_preflight import power_path_audit, route_corridor, widen_plan


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    modes = {'audit': power_path_audit.main, 'widen': widen_plan.main, 'corridor': route_corridor.main}
    if argv and argv[0] in modes:
        return modes[argv[0]](argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('audit', 'widen', 'corridor'))
    args, rest = parser.parse_known_args(argv)
    return {'audit': power_path_audit.main, 'widen': widen_plan.main,
            'corridor': route_corridor.main}[args.mode](rest)


if __name__ == '__main__':
    raise SystemExit(main())
