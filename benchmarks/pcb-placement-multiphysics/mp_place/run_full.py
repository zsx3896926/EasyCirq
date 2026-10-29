"""P4.11: end-to-end "no-human" runner and policy leaderboard.

``run_full`` runs one template through ``run_pipeline(policy=...)``, produces the
verify certificate and (for the default policy) asserts the pipeline defaults.
``--all-goals`` runs the five executable policies over all templates at a small
budget and writes a leaderboard so the maintainer can see the whole trade-off
surface in one table.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence

from . import policy as policy_mod
from . import verify as verify_mod
from .pipeline import run_pipeline
from .templates import instantiate, template_names

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = "buck"


def run_full(template: str = DEFAULT_TEMPLATE, policy: Optional[str] = None, seed: int = 0, steps: int = 800) -> Dict:
    started = time.time()
    report = run_pipeline(template, budget_steps=steps, seed=seed, policy=policy)
    scenario = instantiate(template, seed=seed)
    placement = report["placement"] if "placement" in report else None
    cert = None
    if placement is not None:
        try:
            cert = verify_mod.certificate(scenario, placement, extra={"policy": policy, "seed": seed, "steps": steps})
        except Exception as exc:  # noqa: BLE001
            cert = {"error": f"{type(exc).__name__}: {exc}"}
    defaults_ok = None
    if policy is None:
        try:
            policy_mod.assert_defaults()
            defaults_ok = True
        except AssertionError as exc:
            defaults_ok = False
            cert = (cert or {}) | {"defaults_error": str(exc)}
    return {
        "template": template,
        "policy": policy or "balanced",
        "seed": seed,
        "steps": steps,
        "feasible": report.get("feasible"),
        "truth_v2": report.get("truth_v2"),
        "router": report.get("router", {}),
        "intent_replay_ok": report.get("intent_replay_ok"),
        "fixed_fields": report.get("fixed_fields"),
        "defaults_ok": defaults_ok,
        "certificate_schema": (cert or {}).get("schema"),
        "certificate_verdict": (cert or {}).get("verdict"),
        "runtime_s": round(time.time() - started, 3),
        "report_digest": (report.get("placement_digest") or "")[:12],
    }


def run_all_goals(steps: int = 400, seed: int = 0) -> Dict:
    names = list(template_names())
    goals = list(policy_mod.POLICY_GOALS)
    started = time.time()
    rows: List[Dict] = []
    for name in names:
        for goal in goals:
            report = run_pipeline(name, budget_steps=steps, seed=seed, policy=goal)
            router = report.get("router", {})
            rows.append(
                {
                    "template": name,
                    "goal": goal,
                    "feasible": report.get("feasible"),
                    "truth_v2": report.get("truth_v2"),
                    "completion": router.get("completion"),
                    "runtime_s": report.get("runtime_s"),
                }
            )
            print(f"[run_full] {name} {goal}: truth={report.get('truth_v2')} comp={router.get('completion')}")
    return {
        "config": {"templates": names, "goals": goals, "steps": steps, "seed": seed},
        "rows": rows,
        "runtime_s": round(time.time() - started, 2),
    }


def _goal_means(data: Dict) -> Dict:
    by_goal: Dict[str, List[Dict]] = {}
    for r in data["rows"]:
        by_goal.setdefault(r["goal"], []).append(r)
    out = {}
    for goal, rs in by_goal.items():
        truth = [r["truth_v2"] for r in rs if isinstance(r["truth_v2"], (int, float))]
        comp = [r["completion"] for r in rs if isinstance(r["completion"], (int, float))]
        out[goal] = {
            "truth_v2": round(sum(truth) / len(truth), 4) if truth else None,
            "completion": round(sum(comp) / len(comp), 4) if comp else None,
            "all_feasible": all(r["feasible"] for r in rs),
        }
    return out


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_full.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# P4.11：端到端 leaderboard\n"]
    lines.append(f"- 配置：{data['config']}；运行 {data['runtime_s']} s\n")
    lines.append("## 各 policy 均值（8 模板）\n")
    lines.append("| policy | truth_v2 | completion | 全硬可行 |")
    lines.append("|---|---|---|---|")
    for goal, m in _goal_means(data).items():
        lines.append(f"| {goal} | {m['truth_v2']} | {m['completion']} | {m['all_feasible']} |")
    lines.append("\n> 边界：伪物理 truth / 1mm 2层离线 router；真实 DRC/布线/SI-PI/热 `NOT RUN`。")
    (out_dir / "report_full.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[run_full] wrote {out_dir / 'report_full.md'} / report_full.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end no-human pipeline + policy leaderboard")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--all-goals", action="store_true")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    if args.all_goals:
        write_report(run_all_goals(steps=args.steps, seed=args.seed), pathlib.Path(args.out))
    else:
        data = {"rows": [], "config": {"templates": [args.template], "goals": [args.policy or "balanced"], "steps": args.steps, "seed": args.seed},
                "runtime_s": 0.0, "single": run_full(args.template, args.policy, args.seed, args.steps)}
        text = json.dumps(data["single"], ensure_ascii=False, indent=2, sort_keys=True)
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
