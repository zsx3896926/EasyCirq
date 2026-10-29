"""P4.14: structured CCG diagnostics for template/constraint authoring.

Parses the human-readable strings produced by ``intent.intent_violations`` into
structured records, and runs a strict-mode plan on one template to report
exactly which constraints block convergence (used when a new template cannot
reach ``ccg_final == 0`` in strict mode).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
from typing import Dict, List, Optional, Sequence

from .intent import build_intent, intent_violations
from .intent_solver import plan_from_intent
from .solver import random_feasible_placement
from .templates import instantiate

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
_VIOLATION_RE = re.compile(
    r"^(?P<id>ccg-\d+):(?P<type>near|clearance|cluster|edge):(?P<a>\w+):(?P<b>\w+):"
    r"(?P<detail>[\d.]+)(?P<op>>|<)(?P<limit>[\d.]+)$"
)


def parse_violations(violations: Sequence[str]) -> List[Dict]:
    rows: List[Dict] = []
    for text in violations:
        m = _VIOLATION_RE.match(text)
        if not m:
            rows.append({"raw": text})
            continue
        rows.append(
            {
                "id": m.group("id"),
                "type": m.group("type"),
                "a": m.group("a"),
                "b": m.group("b"),
                "actual": float(m.group("detail")),
                "op": m.group("op"),
                "limit": float(m.group("limit")),
            }
        )
    return rows


def diagnose_template(name: str, seed: int = 1, steps: int = 800) -> Dict:
    sc = instantiate(name, seed=0)
    reference = random_feasible_placement(sc, random.Random(0))
    intent = build_intent(sc, reference)
    rng = random.Random(42)
    jiggled = dict(reference)
    movable = [r for r, c in sc.components.items() if not c.fixed]
    for ref in movable:
        x, y, rot = jiggled[ref]
        jiggled[ref] = (x + rng.uniform(-2.0, 2.0), y + rng.uniform(-2.0, 2.0), rot)
    from .model import hard_violations

    if hard_violations(sc, jiggled):
        jiggled = reference
    perturbed = json.loads(json.dumps(intent))
    coords = perturbed.get("coordinates")
    if isinstance(coords, dict):
        for ref, (x, y, rot) in jiggled.items():
            if ref in coords:
                coords[ref] = [x, y, rot]
    plan, stats = plan_from_intent(sc, perturbed, seed=seed, steps=steps)
    return {
        "template": name,
        "ccg_initial": stats.get("ccg_initial"),
        "ccg_final": stats.get("ccg_final"),
        "hard_feasible": stats.get("hard_feasible"),
        "residual": parse_violations(stats.get("ccg_residual", [])),
        "raw_residual": stats.get("ccg_residual", []),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Structured CCG diagnosis for one template")
    parser.add_argument("--template", default="buck")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--steps", type=int, default=800)
    args = parser.parse_args(argv)
    result = diagnose_template(args.template, seed=args.seed, steps=args.steps)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ccg_final"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
