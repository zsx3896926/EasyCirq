"""Build the real-verification PCB plan from an observation, a raw dump and a contract.

The plan embeds the exact observation and the raw ``pcb dump --include-copper``
payload so ``feedback/scope.py`` can bind the write to the live board before any
CLI call.  This helper only assembles JSON; it never calls EasyEDA.
"""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--observation', required=True)
    parser.add_argument('--dump', required=True)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--designator', required=True)
    parser.add_argument('--x', type=float)
    parser.add_argument('--y', type=float)
    parser.add_argument('--rotation', type=float)
    parser.add_argument('--layer', type=int)
    parser.add_argument('--reason', default='')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    observation = load(args.observation)
    dump = load(args.dump)
    contract = load(args.contract)
    component = next(
        item for item in observation['pcb']['components']
        if item.get('designator') == args.designator)
    source = {
        'x': component['x'],
        'y': component['y'],
        'rotation': component.get('rotation', 0),
        'layer': component.get('layer', 1),
    }
    target = {
        'x': args.x if args.x is not None else source['x'],
        'y': args.y if args.y is not None else source['y'],
        'rotation': args.rotation if args.rotation is not None
        else source['rotation'],
        'layer': args.layer if args.layer is not None else source['layer'],
    }
    op = {
        'op': 'place',
        'designator': args.designator,
        'primitive_id': component.get('primitive_id'),
        'from': source,
        'to': target,
        'reason': args.reason,
    }
    plan = {
        'base': {'semantic_sha256':
                 (contract.get('baseline') or {}).get('semantic_sha256')},
        'observation': observation,
        'before_dump': dump,
        'partial': True,
        'scope': {'designators': [args.designator], 'nets': []},
        'ops': [op],
    }
    Path(args.out).write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps({'ok': True, 'out': args.out, 'op': op},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
