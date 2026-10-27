"""Same-input, same-domain, same-constraints benchmark: baseline vs improved.

Baseline = one-by-one deterministic greedy + full re-check after every placement.
Improved = conflict-cluster focus + bounded local search/backtracking with a
deterministic spatial index and incremental conflict reuse.

Only offline solver work is measured.  EDA rendering, save/reopen, host
connectivity readback and whole-board wall time are NOT RUN and are never claimed.

Speedup is only asserted when quality is equal or better: the improved run must
not leave more hard conflicts and must not move more annotations than the
baseline, and must not introduce a new hard conflict.
"""
from __future__ import annotations

import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .baseline import solve_baseline
from .candidates import generate_candidates
from .conflicts import evaluate_assignment
from .model import (
    SCHEMA_ID,
    TOOL_VERSION,
    Counters,
    Input,
    SearchResult,
    SearchStats,
    canonical_sha256,
)
from .schema import load_input
from .solver import solve
from .verify import independent_violations

BENCHMARK_VERSION = "annotation-layout-benchmark/v1"
LIMITATIONS = [
    "offline solver work only; EDA render/save/reopen/readback and whole-board time NOT RUN",
    "timings are machine-dependent; medians/ranges are reported, not a guarantee",
    "synthetic cases are explicitly labelled and are not evidence about a real board",
    "quality gate requires equal-or-better hard conflicts and not more moved annotations",
]


def _env(seed: int) -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "seed": seed,
        "repeat": None,  # filled by caller
        "notes": "single process; no network/EDA; timing uses time.perf_counter",
    }


def _case_label(path: Path, inp: Input) -> Dict[str, Any]:
    source = inp.source
    return {
        "case": path.name,
        "path": str(path),
        "project": inp.project.to_dict(),
        "source_kind": source.kind,
        "source_notes": source.notes,
        "input_sha256": inp.canonical_sha256,
        "counts": {
            "components": len(inp.components),
            "wires": len(inp.wires),
            "fixed_texts": len(inp.fixed_texts),
            "movable_annotations": len(inp.annotations),
        },
        "real_or_synthetic": "real_frozen" if source.kind == "frozen_fixture" else "synthetic",
    }


def _result_metrics(result: SearchResult, before_hard: int) -> Dict[str, Any]:
    moved = sum(1 for candidate in result.assignment.values()
                if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9)
    displacement = sum(candidate.displacement for candidate in result.assignment.values())
    return {
        "status": result.status,
        "noop": result.noop,
        "hard_after": sum(1 for item in result.violations if item.is_hard),
        "soft_after": sum(1 for item in result.violations if item.severity == "soft"),
        "hard_before": before_hard,
        "unknown": len(result.unknown),
        "moved": moved,
        "total_displacement": round(displacement, 6),
        "candidates_generated": result.stats.candidates_generated,
        "iterations": result.stats.iterations,
        "states": result.stats.states,
        "local_steps": result.stats.local_steps,
        "clusters": result.stats.clusters,
        "budget_exhausted": result.stats.budget_exhausted,
    }


def _timing(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"median_s": None, "min_s": None, "max_s": None, "samples": []}
    return {
        "median_s": round(statistics.median(values), 6),
        "min_s": round(min(values), 6),
        "max_s": round(max(values), 6),
        "samples": [round(value, 6) for value in values],
    }


def _candidate_domains(inp: Input) -> tuple[Dict[str, List[Any]], Dict[str, Any], float]:
    stats = SearchStats()
    counter = Counters()
    started = time.perf_counter()
    domains = generate_candidates(inp, counter=counter, stats=stats)
    elapsed = time.perf_counter() - started
    return domains, stats.to_dict(), elapsed


def _introduced_hard(inp: Input, result: SearchResult) -> int:
    before = {item.key() for item in evaluate_assignment(inp, {}) if item.is_hard}
    after = {item.key() for item in result.violations if item.is_hard}
    return len(after - before)


def run_case(path: Path, repeat: int) -> Dict[str, Any]:
    inp = load_input(path)
    domains, domain_stats, domain_seconds = _candidate_domains(inp)
    before_hard = sum(1 for item in evaluate_assignment(inp, {}) if item.is_hard)
    baseline_times: List[float] = []
    improved_times: List[float] = []
    baseline_counters: List[Dict[str, int]] = []
    improved_counters: List[Dict[str, int]] = []
    baseline_result: Optional[SearchResult] = None
    improved_result: Optional[SearchResult] = None
    for _ in range(max(1, repeat)):
        baseline_counter = Counters()
        started = time.perf_counter()
        baseline_result = solve_baseline(inp, candidates=domains,
                                         counter=baseline_counter)
        baseline_times.append(time.perf_counter() - started)
        baseline_counters.append(baseline_counter.snapshot())
        improved_counter = Counters()
        started = time.perf_counter()
        improved_result = solve(inp, candidates=domains, counter=improved_counter)
        improved_times.append(time.perf_counter() - started)
        improved_counters.append(improved_counter.snapshot())
    assert baseline_result is not None and improved_result is not None
    baseline_metrics = _result_metrics(baseline_result, before_hard)
    improved_metrics = _result_metrics(improved_result, before_hard)
    baseline_introduced = _introduced_hard(inp, baseline_result)
    improved_introduced = _introduced_hard(inp, improved_result)

    # Independent geometric recheck (not the solver's own cost) for both results.
    baseline_boxes = {ann.id: ann.current.bbox for ann in inp.annotations}
    for identity, candidate in baseline_result.assignment.items():
        baseline_boxes[identity] = candidate.bbox
    improved_boxes = {ann.id: ann.current.bbox for ann in inp.annotations}
    for identity, candidate in improved_result.assignment.items():
        improved_boxes[identity] = candidate.bbox
    independent_baseline = independent_violations(inp, baseline_boxes)
    independent_improved = independent_violations(inp, improved_boxes)
    independent_baseline_hard = sum(1 for item in independent_baseline
                                    if item["severity"] == "hard")
    independent_improved_hard = sum(1 for item in independent_improved
                                    if item["severity"] == "hard")

    quality_equal = (
        improved_metrics["hard_after"] == 0
        and improved_metrics["hard_after"] <= baseline_metrics["hard_after"]
        and improved_metrics["moved"] <= baseline_metrics["moved"]
        and improved_introduced == 0
        and independent_improved_hard == 0
    )
    baseline_median = statistics.median(baseline_times)
    improved_median = statistics.median(improved_times)
    speedup_claim = bool(quality_equal and improved_median < baseline_median
                         and improved_median > 0)
    return {
        **_case_label(path, inp),
        "before_hard": before_hard,
        "candidate_domain": {
            "generated": domain_stats["candidates_generated"],
            "possible": domain_stats["candidates_possible"],
            "truncated": domain_stats["candidates_truncated"],
            "generation_seconds": round(domain_seconds, 6),
        },
        "baseline": {
            **baseline_metrics,
            "timing": _timing(baseline_times),
            "counters": baseline_counters[0] if baseline_counters else {},
            "introduced_hard": baseline_introduced,
            "independent_hard_after": independent_baseline_hard,
        },
        "improved": {
            **improved_metrics,
            "timing": _timing(improved_times),
            "counters": improved_counters[0] if improved_counters else {},
            "introduced_hard": improved_introduced,
            "independent_hard_after": independent_improved_hard,
        },
        "comparison": {
            "quality_equal_or_better": quality_equal,
            "speedup_claimed": speedup_claim,
            "speedup_ratio": round(baseline_median / improved_median, 3)
            if speedup_claim and improved_median > 0 else None,
            "baseline_median_s": round(baseline_median, 6),
            "improved_median_s": round(improved_median, 6),
            "collision_checks": {
                "baseline": baseline_counters[-1].get("collision_checks")
                if baseline_counters else None,
                "improved": improved_counters[-1].get("collision_checks")
                if improved_counters else None,
            },
        },
    }


def _cli_timing(path: Path, repeat: int) -> Dict[str, Any]:
    scripts = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(scripts) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    times: List[float] = []
    statuses: List[str] = []
    commands: List[str] = []
    with tempfile.TemporaryDirectory() as temp:
        out_dir = Path(temp) / "out"
        command = [sys.executable, "-m", "annotation_layout", "plan", str(path),
                   "--out-dir", str(out_dir)]
        for _ in range(max(1, repeat)):
            started = time.perf_counter()
            completed = subprocess.run(command, cwd=str(scripts), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", timeout=600)
            times.append(time.perf_counter() - started)
            try:
                payload = json.loads(completed.stdout.strip().splitlines()[-1])
                statuses.append(str(payload.get("status")))
            except (IndexError, json.JSONDecodeError):
                statuses.append(f"exit_{completed.returncode}")
            commands.append(" ".join(command))
    return {
        "command": commands[0] if commands else "",
        "exit_statuses": statuses,
        "timing": _timing(times),
        "note": "python CLI round trip only; EDA host round trip/save/reopen NOT RUN",
    }


def discover_cases(suite: Path) -> List[Path]:
    if not suite.is_dir():
        raise FileNotFoundError(f"benchmark suite directory not found: {suite}")
    cases = sorted(path for path in suite.glob("*.json")
                   if path.name not in ("result.json", "manifest.json", "MANIFEST.json")
                   and "manifest" not in path.name.lower())
    if not cases:
        raise FileNotFoundError(f"no *.json cases in {suite}")
    return cases


def run_benchmark(suite: Path, *, repeat: int = 5, seed: int = 20261027,
                  cli_timing: bool = True) -> Dict[str, Any]:
    repeat = max(1, int(repeat))
    cases = discover_cases(Path(suite))
    environment = _env(seed)
    environment["repeat"] = repeat
    started = time.perf_counter()
    records = [run_case(path, repeat) for path in cases]
    cli_records = []
    if cli_timing:
        for path in cases:
            cli_records.append({"case": path.name, **_cli_timing(path, min(repeat, 3))})
    total_seconds = time.perf_counter() - started

    real = [record for record in records if record["real_or_synthetic"] == "real_frozen"]
    synthetic = [record for record in records if record["real_or_synthetic"] != "real_frozen"]
    claims = [record for record in records if record["comparison"]["speedup_claimed"]]

    def aggregate(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not group:
            return {"cases": 0}
        return {
            "cases": len(group),
            "baseline_median_s": round(statistics.median(
                [record["baseline"]["timing"]["median_s"] for record in group]), 6),
            "improved_median_s": round(statistics.median(
                [record["improved"]["timing"]["median_s"] for record in group]), 6),
            "quality_equal_cases": sum(1 for record in group
                                       if record["comparison"]["quality_equal_or_better"]),
            "speedup_claimed_cases": sum(1 for record in group
                                         if record["comparison"]["speedup_claimed"]),
        }

    return {
        "schema": BENCHMARK_VERSION,
        "tool": {"name": "annotation_layout", "version": TOOL_VERSION},
        "seed": seed,
        "repeat": repeat,
        "environment": environment,
        "suite": {
            "path": str(suite),
            "cases": len(records),
            "real_frozen": len(real),
            "synthetic": len(synthetic),
        },
        "summary": {
            "real_frozen": aggregate(real),
            "synthetic": aggregate(synthetic),
            "all": aggregate(records),
            "speedup_claimed_cases": len(claims),
            "quality_gate": "improved hard_after=0, moved<=baseline moved, "
                            "no introduced hard, independent recheck clean",
        },
        "cases": records,
        "cli_round_trip": cli_records,
        "not_run": [
            "NOT RUN: EDA render / official export",
            "NOT RUN: host write / save / reopen / connectivity readback",
            "NOT RUN: whole-board / host round-trip wall time",
        ],
        "total_wall_seconds": round(total_seconds, 6),
        "limitations": LIMITATIONS,
        "environment_note": "timings are not compared across machines; medians/ranges only",
    }


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# annotation-layout benchmark report",
        "",
        f"- schema: `{result.get('schema')}`",
        f"- tool: `annotation_layout` {result.get('tool', {}).get('version')}",
        f"- repeat: {result.get('repeat')} (median + min/max)",
        f"- seed: {result.get('seed')}",
        f"- python: {result.get('environment', {}).get('python')} on "
        f"{result.get('environment', {}).get('platform')}",
        f"- cases: {result.get('suite', {}).get('cases')} "
        f"(real frozen {result.get('suite', {}).get('real_frozen')}, "
        f"synthetic {result.get('suite', {}).get('synthetic')})",
        "",
        "Baseline = deterministic per-annotation greedy + full recheck after each "
        "placement. Improved = bounded focus/cluster search with spatial index and "
        "local search. Same candidate domains, spacing, font and displacement limits.",
        "",
        "## Summary",
        "",
        "| group | cases | baseline median s | improved median s | quality-equal | speedup claimed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, group in (("real frozen", result.get("summary", {}).get("real_frozen")),
                        ("synthetic", result.get("summary", {}).get("synthetic")),
                        ("all", result.get("summary", {}).get("all"))):
        if not isinstance(group, Mapping) or not group.get("cases"):
            continue
        lines.append(f"| {name} | {group.get('cases')} | {group.get('baseline_median_s')} | "
                     f"{group.get('improved_median_s')} | {group.get('quality_equal_cases')} | "
                     f"{group.get('speedup_claimed_cases')} |")
    lines += [
        "",
        "## Per case",
        "",
        "| case | kind | before hard | baseline hard/moved | improved hard/moved | "
        "baseline median s (min–max) | improved median s (min–max) | quality met | speedup |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in result.get("cases") or []:
        baseline = record["baseline"]
        improved = record["improved"]
        lines.append(
            f"| {record['case']} | {record['real_or_synthetic']} | {record['before_hard']} | "
            f"{baseline['hard_after']}/{baseline['moved']} | "
            f"{improved['hard_after']}/{improved['moved']} | "
            f"{baseline['timing']['median_s']} ({baseline['timing']['min_s']}–"
            f"{baseline['timing']['max_s']}) | "
            f"{improved['timing']['median_s']} ({improved['timing']['min_s']}–"
            f"{improved['timing']['max_s']}) | "
            f"{record['comparison']['quality_equal_or_better']} | "
            f"{record['comparison']['speedup_ratio'] if record['comparison']['speedup_claimed'] else 'not claimed'} |")
    lines += [
        "",
        "## CLI round trip",
        "",
    ]
    for entry in result.get("cli_round_trip") or []:
        timing = entry.get("timing") or {}
        lines.append(f"- `{entry.get('case')}`: median {timing.get('median_s')} s "
                     f"({timing.get('min_s')}–{timing.get('max_s')}), "
                     f"statuses {entry.get('exit_statuses')}")
    lines += [
        "",
        "## NOT RUN / limitations",
        "",
    ]
    for item in result.get("not_run") or []:
        lines.append(f"- NOT RUN: {item}")
    for item in result.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
