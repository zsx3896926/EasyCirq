"""P4.9: realboard regression benchmark (freeze the 4-board suite, detect drift).

This module turns a real-board suite run (``mp_place.realboard.run_all_v3``) into
a *regression baseline* and compares later runs against it with the P4.9
tolerances:

* **truth_v2 relative degradation** -- optimized/repair truth may not get worse
  than the frozen baseline by more than ``+5%`` (lower truth is better);
* **completion drop** -- optimized/repair router completion may not drop by more
  than ``0.02`` absolute;
* **board count must not decrease** -- the suite may gain boards but losing a
  real board from auto-discovery is a hard drift.

Artifacts
---------
``python -m mp_place.realboard_benchmark --update-baseline``
    runs the suite (4 real EasyCirq boards on this machine), freezes the suite
    metrics into ``docs/REALBOARD_BASELINE.json`` and writes the markdown report
    ``docs/REALBOARD.md``.  It only freezes when every board's optimized and
    repaired placement is hard-feasible.
``python -m mp_place.realboard_benchmark --check``
    runs the suite again, compares against the frozen baseline and writes
    ``docs/REALBOARD.md`` with PASS/FAIL per check plus the drift list.  A
    missing baseline reports ``NO BASELINE`` gracefully; missing cases report
    ``SKIP`` (nothing to measure, nothing crashes).

The markdown report contains the suite means, per-board best/worst, the
per-board metric trend (baseline -> current) and the full drift list; the JSON
baseline records schema, generation time/environment, per-board source SHA256
and the frozen suite metrics.

Everything is offline and uses the deterministic realboard comparison; only
wall-clock fields are non-deterministic (they are not part of the frozen
baseline and are stripped by :func:`strip_volatile_baseline` for tests).

Boundary: the router is the offline 1mm/2-layer grid-maze oracle and
``physics_v2`` is a pseudo-physics truth model -- this is a regression guard for
the offline suite, not a DRC/routability/manufacturing sign-off.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import pathlib
import platform
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import realboard

BASELINE_SCHEMA = "mp_place.realboard-baseline/v1"
COMPARISON_SCHEMA = "mp_place.realboard-benchmark-comparison/v1"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_PATH = PROJECT_ROOT / "docs" / "REALBOARD_BASELINE.json"
DEFAULT_MD_PATH = PROJECT_ROOT / "docs" / "REALBOARD.md"

DEFAULT_STEPS = realboard.DEFAULT_STEPS_V3
DEFAULT_SEED = realboard.DEFAULT_SEED
DEFAULT_MAX_ROUTES = realboard.DEFAULT_MAX_ROUTES
MIN_EXPECTED_BOARDS = 4

TOLERANCES: Dict[str, float] = {
    "truth_relative_degradation": 0.05,
    "completion_drop": 0.02,
    "board_count_drop": 0.0,
}

MAX_BOARD_COUNT = 10_000
_EPS = 1e-9

BENCHMARK_LIMITS: Tuple[str, ...] = (
    "offline regression guard for the realboard suite; not DRC and not a routability proof",
    "physics_v2 truth is an offline pseudo-physics model, not a measurement",
    "router completion is the offline 1mm/2-layer grid-maze oracle",
    "capture bbox includes silk/courtyard; polygon/keepout handling follows realboard v3 limits",
    "the baseline freezes one machine/configuration; refresh it with --update-baseline after intended changes",
)


class BenchmarkError(Exception):
    """Raised for corrupted baselines / unusable suite runs."""


# --------------------------------------------------------------------------- #
# small JSON helpers
# --------------------------------------------------------------------------- #
def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _finite(value: Any, digits: int = 6) -> Optional[float]:
    number = _number(value)
    return None if number is None else round(number, digits)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _write_text_atomic(path: pathlib.Path, text: str) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix="." + path.name + "-", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _default_environment() -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "root": str(PROJECT_ROOT),
    }


# --------------------------------------------------------------------------- #
# baseline extraction
# --------------------------------------------------------------------------- #
def _metric_group(metrics: Any) -> Dict[str, Any]:
    metrics = metrics if isinstance(metrics, dict) else {}
    router = metrics.get("router") if isinstance(metrics.get("router"), dict) else {}
    return {
        "completion": _finite(router.get("completion")),
        "truth_v2": _finite(metrics.get("truth_v2")),
        "feasible": bool(metrics.get("feasible")),
    }


def _metric_of(board: Dict[str, Any], group: str) -> Dict[str, Any]:
    return _metric_group(board.get(group))


def _suite_block(report: Dict[str, Any]) -> Dict[str, Any]:
    suite = report.get("suite") if isinstance(report.get("suite"), dict) else {}

    def pick(item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        return {
            "name": item.get("name"),
            "case": item.get("case"),
            "completion_original": _finite(item.get("completion_original")),
            "completion_optimized": _finite(item.get("completion_optimized")),
            "completion_repair": _finite(item.get("completion_repair")),
            "truth_v2_original": _finite(item.get("truth_v2_original")),
            "truth_v2_optimized": _finite(item.get("truth_v2_optimized")),
            "truth_v2_repair": _finite(item.get("truth_v2_repair")),
            "completion_gain_repair": _finite(item.get("completion_gain_repair")),
            "truth_reduction_pct_repair": _finite(
                item.get("truth_reduction_pct_repair")
            ),
        }

    def number_dict(value: Any) -> Dict[str, Optional[float]]:
        if not isinstance(value, dict):
            return {}
        return {str(key): _finite(item) for key, item in value.items()}

    return {
        "n_boards": int(suite.get("n_boards") or 0),
        "mean_completion": number_dict(suite.get("mean_completion")),
        "mean_truth_v2": number_dict(suite.get("mean_truth_v2")),
        "mean_completion_gain": number_dict(suite.get("mean_completion_gain")),
        "mean_truth_reduction_pct": number_dict(
            suite.get("mean_truth_reduction_pct")
        ),
        "all_feasible": {
            str(key): value
            for key, value in (suite.get("all_feasible") or {}).items()
        },
        "best_board": pick(suite.get("best_board")),
        "worst_board": pick(suite.get("worst_board")),
        "ranking": suite.get("ranking"),
    }


def collect_baseline(
    report: Dict[str, Any],
    *,
    generated_at: Optional[str] = None,
    environment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn a realboard v3 suite report into a frozen baseline payload."""
    if not isinstance(report, dict):
        raise BenchmarkError("suite report must be a JSON object")
    if report.get("schema") != realboard.REALBOARD_SCHEMA_V3:
        raise BenchmarkError(
            "suite report schema must be "
            f"{realboard.REALBOARD_SCHEMA_V3!r}, got {report.get('schema')!r}"
        )
    raw_boards = report.get("boards")
    if not isinstance(raw_boards, list) or not raw_boards:
        raise BenchmarkError("suite report has no boards to freeze")
    boards: List[Dict[str, Any]] = []
    for row in raw_boards:
        if not isinstance(row, dict):
            continue
        conversion = row.get("conversion") if isinstance(row.get("conversion"), dict) else {}
        polygon = conversion.get("polygon") if isinstance(conversion.get("polygon"), dict) else {}
        keepouts = conversion.get("keepouts") if isinstance(conversion.get("keepouts"), dict) else {}
        boards.append(
            {
                "name": str(row.get("name") or ""),
                "case": row.get("case"),
                "source": row.get("source"),
                "source_sha256": row.get("source_sha256"),
                "components": int(conversion.get("components_kept") or 0),
                "nets": int(conversion.get("nets_kept") or 0),
                "polygon_points": int(polygon.get("points") or 0),
                "keepout_status": keepouts.get("status"),
                "keepouts": int(keepouts.get("count") or 0),
                "mechanical_fixed_count": int(
                    conversion.get("mechanical_fixed_count") or 0
                ),
                "metrics": {
                    "original": _metric_of(row, "original"),
                    "optimized": _metric_of(row, "optimized"),
                    "repair": _metric_of(row, "repair"),
                },
            }
        )
    boards = [board for board in boards if board["name"]]
    if not boards:
        raise BenchmarkError("suite report boards have no names to freeze")
    config = report.get("config") if isinstance(report.get("config"), dict) else {}
    discovery = report.get("discovery") if isinstance(report.get("discovery"), dict) else {}
    timestamp = generated_at or datetime.datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %z"
    )
    payload: Dict[str, Any] = {
        "schema": BASELINE_SCHEMA,
        "generated_at": timestamp,
        "generated_by": "python -m mp_place.realboard_benchmark --update-baseline",
        "environment": environment if environment is not None else _default_environment(),
        "config": {
            "steps": config.get("steps"),
            "seed": config.get("seed"),
            "max_routes": config.get("max_routes"),
            "solver": config.get("solver"),
            "objective": config.get("objective"),
            "repair": config.get("repair"),
            "router": config.get("router"),
            "discovery_mode": discovery.get("mode"),
            "cases_root": discovery.get("cases_root"),
        },
        "tolerances": dict(TOLERANCES),
        "boards": boards,
        "suite": _suite_block(report),
    }
    return _json_safe(payload)


# --------------------------------------------------------------------------- #
# baseline validation / IO
# --------------------------------------------------------------------------- #
_REQUIRED_TOLERANCE_KEYS = (
    "truth_relative_degradation",
    "completion_drop",
    "board_count_drop",
)
_GROUP_KEYS = ("original", "optimized", "repair")


def validate_baseline(payload: Any, path: Optional[object] = None) -> None:
    """Raise :class:`BenchmarkError` unless ``payload`` is a valid baseline."""
    where = f" ({path})" if path is not None else ""
    if not isinstance(payload, dict):
        raise BenchmarkError(f"realboard baseline{where} must be a JSON object")
    if payload.get("schema") != BASELINE_SCHEMA:
        raise BenchmarkError(
            f"realboard baseline{where} schema must be {BASELINE_SCHEMA!r}, "
            f"got {payload.get('schema')!r}"
        )
    boards = payload.get("boards")
    if not isinstance(boards, list) or not boards:
        raise BenchmarkError(f"realboard baseline{where} has no 'boards' list")
    seen = set()
    for board in boards:
        if not isinstance(board, dict):
            raise BenchmarkError(f"realboard baseline{where} board entries must be objects")
        name = board.get("name")
        if not isinstance(name, str) or not name:
            raise BenchmarkError(f"realboard baseline{where} board has no name")
        if name in seen:
            raise BenchmarkError(f"realboard baseline{where} duplicate board {name!r}")
        seen.add(name)
        metrics = board.get("metrics")
        if not isinstance(metrics, dict):
            raise BenchmarkError(f"realboard baseline{where} {name}: missing metrics")
        for group in _GROUP_KEYS:
            entry = metrics.get(group)
            if not isinstance(entry, dict):
                raise BenchmarkError(
                    f"realboard baseline{where} {name}: missing metrics.{group}"
                )
            for key in ("truth_v2", "completion"):
                if _number(entry.get(key)) is None:
                    raise BenchmarkError(
                        f"realboard baseline{where} {name}.{group}.{key} "
                        "must be a finite number"
                    )
            if not isinstance(entry.get("feasible"), bool):
                raise BenchmarkError(
                    f"realboard baseline{where} {name}.{group}.feasible must be a bool"
                )
    suite = payload.get("suite")
    if not isinstance(suite, dict):
        raise BenchmarkError(f"realboard baseline{where} has no 'suite' object")
    if not isinstance(suite.get("n_boards"), int) or suite["n_boards"] < 1:
        raise BenchmarkError(f"realboard baseline{where} suite.n_boards must be >= 1")
    for key in ("mean_completion", "mean_truth_v2", "all_feasible"):
        if not isinstance(suite.get(key), dict):
            raise BenchmarkError(f"realboard baseline{where} suite.{key} must be an object")
    tolerances = payload.get("tolerances")
    if not isinstance(tolerances, dict):
        raise BenchmarkError(f"realboard baseline{where} has no 'tolerances' object")
    for key in _REQUIRED_TOLERANCE_KEYS:
        if _number(tolerances.get(key)) is None:
            raise BenchmarkError(
                f"realboard baseline{where} tolerances.{key} must be a finite number"
            )
    for key in ("generated_at", "config", "environment"):
        if key not in payload:
            raise BenchmarkError(f"realboard baseline{where} is missing {key!r}")


def load_baseline(path: object = DEFAULT_BASELINE_PATH) -> Dict[str, Any]:
    """Read and validate the frozen realboard baseline JSON."""
    target = pathlib.Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise BenchmarkError(f"cannot read realboard baseline {target}: {exc}") from exc
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BenchmarkError(
            f"realboard baseline {target} is not valid JSON: {exc}"
        ) from exc
    validate_baseline(payload, path=target)
    return payload


def save_baseline(
    payload: Dict[str, Any],
    path: object = DEFAULT_BASELINE_PATH,
) -> pathlib.Path:
    """Validate and atomically write a realboard baseline JSON."""
    validate_baseline(payload, path=path)
    target = pathlib.Path(path)
    text = json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text_atomic(target, text)
    return target


def read_baseline_status(path: object = DEFAULT_BASELINE_PATH) -> Dict[str, Any]:
    """Never-raising probe: status in ``OK`` / ``MISSING`` / ``INVALID``."""
    target = pathlib.Path(path)
    try:
        baseline = load_baseline(target)
    except FileNotFoundError:
        return {
            "path": str(target),
            "status": "MISSING",
            "readable": False,
            "exists": target.exists(),
            "error": None,
            "baseline": None,
        }
    except BenchmarkError as exc:
        return {
            "path": str(target),
            "status": "INVALID",
            "readable": False,
            "exists": target.exists(),
            "error": str(exc),
            "baseline": None,
        }
    return {
        "path": str(target),
        "status": "OK",
        "readable": True,
        "exists": True,
        "error": None,
        "baseline": baseline,
    }


def strip_volatile_baseline(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy without ``generated_at``/``environment`` (determinism tests)."""
    volatile = {"generated_at", "environment", "runtime_s", "elapsed_s", "timings_s"}

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): clean(item)
                for key, item in value.items()
                if key not in volatile
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(_json_safe(payload))


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #
def _merge_tolerances(tolerances: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    merged = dict(TOLERANCES)
    if tolerances:
        for key, value in tolerances.items():
            number = _number(value)
            if number is not None and number >= 0.0:
                merged[str(key)] = number
    return merged


def _add_check(
    checks: List[Dict[str, Any]],
    name: str,
    kind: str,
    baseline_value: Any,
    current_value: Any,
    passed: bool,
    tolerance: Any = None,
    severity: str = "hard",
    note: str = "",
) -> None:
    delta: Optional[float] = None
    base_number = _number(baseline_value) if not isinstance(baseline_value, bool) else None
    cur_number = _number(current_value) if not isinstance(current_value, bool) else None
    if base_number is not None and cur_number is not None:
        delta = round(cur_number - base_number, 6)
    checks.append(
        {
            "name": name,
            "kind": kind,
            "baseline": baseline_value,
            "current": current_value,
            "delta": delta,
            "tolerance": tolerance,
            "severity": severity,
            "passed": bool(passed),
            "note": note,
        }
    )


def _truth_check(
    checks: List[Dict[str, Any]],
    name: str,
    baseline_value: Any,
    current_value: Any,
    tolerance: float,
) -> None:
    base = _number(baseline_value)
    cur = _number(current_value)
    if base is None or cur is None:
        _add_check(
            checks, name, "truth_relative", baseline_value, current_value, False,
            tolerance=f"+{tolerance:.1%}", note="truth metric missing",
        )
        return
    if abs(base) <= _EPS:
        passed = abs(cur - base) <= _EPS
        relative = 0.0 if passed else float("inf")
    else:
        relative = (cur - base) / abs(base)
        passed = relative - tolerance <= _EPS
    _add_check(
        checks, name, "truth_relative", round(base, 6), round(cur, 6), passed,
        tolerance=f"+{tolerance:.1%}", note=f"relative {relative:+.2%}",
    )


def _completion_check(
    checks: List[Dict[str, Any]],
    name: str,
    baseline_value: Any,
    current_value: Any,
    tolerance: float,
) -> None:
    base = _number(baseline_value)
    cur = _number(current_value)
    if base is None or cur is None:
        _add_check(
            checks, name, "completion", baseline_value, current_value, False,
            tolerance=f"drop <= {tolerance:g}", note="completion metric missing",
        )
        return
    drop = base - cur
    passed = drop - tolerance <= _EPS
    _add_check(
        checks, name, "completion", round(base, 6), round(cur, 6), passed,
        tolerance=f"drop <= {tolerance:g}", note=f"drop {drop:+.4f}",
    )


def _flag_check(
    checks: List[Dict[str, Any]],
    name: str,
    baseline_value: Any,
    current_value: Any,
) -> None:
    passed = bool(current_value) if bool(baseline_value) else True
    _add_check(
        checks, name, "flag", bool(baseline_value), bool(current_value), passed,
        tolerance="true", note="feasibility must be preserved",
    )


def compare_to_baseline(
    current: Optional[Dict[str, Any]],
    baseline: Optional[Dict[str, Any]] = None,
    tolerances: Optional[Dict[str, Any]] = None,
    *,
    skip_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare a current frozen-metrics payload with the baseline.

    ``baseline is None`` -> ``NO BASELINE``; ``current is None`` -> ``SKIP``
    (e.g. the EasyCirq cases directory is not available).  Otherwise the
    tolerance checks below are run and any hard drift fails the comparison:

    * board count must not decrease;
    * per-board optimized/repair truth_v2 may not degrade by more than +5%;
    * per-board optimized/repair completion may not drop by more than 0.02;
    * optimized/repair hard feasibility must be preserved;
    * suite means are checked with the same truth/completion tolerances.

    Source-SHA256 changes and new boards are reported as warnings (they mean the
    baseline is stale / the suite grew, not that quality regressed).
    """
    tol = _merge_tolerances(tolerances)
    if baseline is None:
        return {
            "schema": COMPARISON_SCHEMA,
            "status": "NO BASELINE",
            "baseline": None,
            "tolerances": tol,
            "checks": [],
            "drifts": [],
            "hard_drifts": 0,
            "warnings": 0,
            "summary": "no realboard baseline frozen yet; run `python -m mp_place.realboard_benchmark --update-baseline`",
        }
    validate_baseline(baseline)
    if current is None:
        return {
            "schema": COMPARISON_SCHEMA,
            "status": "SKIP",
            "baseline": {
                "schema": baseline.get("schema"),
                "generated_at": baseline.get("generated_at"),
            },
            "tolerances": tol,
            "checks": [],
            "drifts": [],
            "hard_drifts": 0,
            "warnings": 0,
            "summary": "suite not measured; skipping comparison"
            + (f" ({skip_reason})" if skip_reason else ""),
        }
    validate_baseline(current)

    checks: List[Dict[str, Any]] = []
    base_boards = {board["name"]: board for board in baseline["boards"]}
    cur_boards = {board["name"]: board for board in current["boards"]}

    # --- suite size -------------------------------------------------------
    base_count = len(base_boards)
    cur_count = len(cur_boards)
    passed = cur_count + _EPS >= base_count - tol["board_count_drop"]
    _add_check(
        checks, "suite.n_boards", "count", base_count, cur_count, passed,
        tolerance=f">= baseline - {tol['board_count_drop']:g}",
        note=f"delta {cur_count - base_count:+d}",
    )

    # --- per-board checks -------------------------------------------------
    for name in sorted(base_boards):
        base_board = base_boards[name]
        cur_board = cur_boards.get(name)
        if cur_board is None:
            _add_check(
                checks, f"board.{name}.missing", "presence", True, False, False,
                tolerance="present", note="board disappeared from the suite",
            )
            continue
        base_sha = base_board.get("source_sha256")
        cur_sha = cur_board.get("source_sha256")
        if base_sha and cur_sha and base_sha != cur_sha:
            _add_check(
                checks, f"board.{name}.source_sha256", "source", base_sha, cur_sha,
                False, tolerance="unchanged", severity="warning",
                note="source dump changed; refresh the baseline if intended",
            )
        base_metrics = base_board["metrics"]
        cur_metrics = cur_board["metrics"]
        for group in ("optimized", "repair"):
            label = f"board.{name}.{group}"
            _truth_check(
                checks, f"{label}.truth_v2",
                base_metrics[group].get("truth_v2"),
                cur_metrics[group].get("truth_v2"),
                tol["truth_relative_degradation"],
            )
            _completion_check(
                checks, f"{label}.completion",
                base_metrics[group].get("completion"),
                cur_metrics[group].get("completion"),
                tol["completion_drop"],
            )
            _flag_check(
                checks, f"{label}.feasible",
                base_metrics[group].get("feasible"),
                cur_metrics[group].get("feasible"),
            )
    for name in sorted(set(cur_boards) - set(base_boards)):
        _add_check(
            checks, f"board.{name}.new", "presence", False, True, False,
            tolerance="baseline may grow", severity="warning",
            note="new board is not part of the frozen baseline",
        )

    # --- suite means ------------------------------------------------------
    base_suite = baseline.get("suite") or {}
    cur_suite = current.get("suite") or {}
    for group in ("optimized", "repair"):
        _truth_check(
            checks, f"suite.mean_truth_v2.{group}",
            (base_suite.get("mean_truth_v2") or {}).get(group),
            (cur_suite.get("mean_truth_v2") or {}).get(group),
            tol["truth_relative_degradation"],
        )
        _completion_check(
            checks, f"suite.mean_completion.{group}",
            (base_suite.get("mean_completion") or {}).get(group),
            (cur_suite.get("mean_completion") or {}).get(group),
            tol["completion_drop"],
        )
    for group in ("optimized", "repair"):
        _flag_check(
            checks, f"suite.all_feasible.{group}",
            (base_suite.get("all_feasible") or {}).get(group),
            (cur_suite.get("all_feasible") or {}).get(group),
        )

    hard_drifts = [
        check for check in checks if not check["passed"] and check["severity"] == "hard"
    ]
    warnings = [
        check for check in checks if not check["passed"] and check["severity"] == "warning"
    ]
    drifts = hard_drifts + warnings
    status = "FAIL" if hard_drifts else "PASS"
    return {
        "schema": COMPARISON_SCHEMA,
        "status": status,
        "baseline": {
            "schema": baseline.get("schema"),
            "generated_at": baseline.get("generated_at"),
        },
        "tolerances": tol,
        "checks": checks,
        "drifts": drifts,
        "hard_drifts": len(hard_drifts),
        "warnings": len(warnings),
        "summary": (
            f"{len(checks)} checks: {len(hard_drifts)} hard drift(s), "
            f"{len(warnings)} warning(s); n_boards {base_count}->{cur_count}"
        ),
    }


# --------------------------------------------------------------------------- #
# suite evaluation / CLI operations
# --------------------------------------------------------------------------- #
def run_suite(
    sources: Optional[Sequence[object]] = None,
    *,
    cases_root: Optional[object] = None,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Run the realboard v3 suite (thin wrapper around ``run_all_v3``)."""
    return realboard.run_all_v3(
        sources=sources,
        cases_root=cases_root,
        steps=steps,
        seed=seed,
        max_routes=max_routes,
        optimise=optimise,
    )


def evaluate_current(
    sources: Optional[Sequence[object]] = None,
    *,
    cases_root: Optional[object] = None,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Run the suite and return ``{"status", "report", "baseline", "reason"}``.

    ``status`` is ``OK`` when at least one board was measured and ``SKIP`` when
    the cases directory is missing / has no usable dumps (nothing to compare).
    """
    try:
        report = run_suite(
            sources,
            cases_root=cases_root,
            steps=steps,
            seed=seed,
            max_routes=max_routes,
            optimise=optimise,
        )
    except (OSError, ValueError, KeyError) as exc:
        return {
            "status": "SKIP",
            "report": None,
            "baseline": None,
            "reason": f"suite failed to run: {type(exc).__name__}: {exc}",
        }
    boards = report.get("boards") or []
    if not boards:
        skipped = report.get("skipped_cases") or []
        reason = "no real boards measured"
        if skipped:
            reason += "; " + "; ".join(
                f"{item.get('case')}: {item.get('reason')}" for item in skipped[:4]
            )
        return {"status": "SKIP", "report": report, "baseline": None, "reason": reason}
    baseline = collect_baseline(report)
    return {"status": "OK", "report": report, "baseline": baseline, "reason": None}


def _all_solver_feasible(baseline: Dict[str, Any]) -> bool:
    for board in baseline.get("boards") or []:
        metrics = board.get("metrics") or {}
        for group in ("optimized", "repair"):
            if not bool((metrics.get(group) or {}).get("feasible")):
                return False
    return True


def update_baseline(
    *,
    baseline_path: object = DEFAULT_BASELINE_PATH,
    md_path: object = DEFAULT_MD_PATH,
    sources: Optional[Sequence[object]] = None,
    cases_root: Optional[object] = None,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
) -> Dict[str, Any]:
    """Run the suite and freeze the measured metrics into the baseline JSON."""
    started = time.perf_counter()
    evaluation = evaluate_current(
        sources,
        cases_root=cases_root,
        steps=steps,
        seed=seed,
        max_routes=max_routes,
        optimise=optimise,
    )
    if evaluation["status"] != "OK":
        raise BenchmarkError(evaluation.get("reason") or "suite produced no boards")
    baseline = evaluation["baseline"]
    if not _all_solver_feasible(baseline):
        raise BenchmarkError(
            "refusing to freeze: an optimized/repaired placement is not hard-feasible"
        )
    target = save_baseline(baseline, baseline_path)
    result = {
        "mode": "update-baseline",
        "schema": COMPARISON_SCHEMA,
        "status": "UPDATED",
        "runtime_s": round(time.perf_counter() - started, 2),
        "baseline_path": str(target),
        "md_path": str(md_path),
        "baseline": baseline,
        "report": evaluation["report"],
        "summary": (
            f"frozen {len(baseline['boards'])} boards: mean completion "
            f"{_fmt_triple(baseline['suite']['mean_completion'])}"
        ),
    }
    write_markdown(result, mode="update", path=md_path)
    return _json_safe(result)


def check_baseline(
    *,
    baseline_path: object = DEFAULT_BASELINE_PATH,
    md_path: object = DEFAULT_MD_PATH,
    sources: Optional[Sequence[object]] = None,
    cases_root: Optional[object] = None,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    max_routes: int = DEFAULT_MAX_ROUTES,
    optimise: bool = True,
    tolerances: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the suite and compare it with the frozen baseline; write the report."""
    started = time.perf_counter()
    status_info = read_baseline_status(baseline_path)
    if status_info["status"] == "INVALID":
        result = {
            "mode": "check",
            "schema": COMPARISON_SCHEMA,
            "status": "INVALID",
            "runtime_s": round(time.perf_counter() - started, 2),
            "baseline_path": str(baseline_path),
            "md_path": str(md_path),
            "baseline_status": status_info,
            "comparison": None,
            "current": None,
            "summary": "baseline file is unreadable: " + str(status_info.get("error")),
        }
        write_markdown(result, mode="check", path=md_path)
        return _json_safe(result)
    evaluation = evaluate_current(
        sources,
        cases_root=cases_root,
        steps=steps,
        seed=seed,
        max_routes=max_routes,
        optimise=optimise,
    )
    current = evaluation["baseline"]
    comparison = compare_to_baseline(
        current,
        status_info["baseline"],
        tolerances=tolerances,
        skip_reason=evaluation.get("reason"),
    )
    result = {
        "mode": "check",
        "schema": COMPARISON_SCHEMA,
        "status": comparison["status"],
        "runtime_s": round(time.perf_counter() - started, 2),
        "baseline_path": str(baseline_path),
        "md_path": str(md_path),
        "baseline_status": {
            key: status_info.get(key) for key in ("path", "status", "readable", "error")
        },
        "comparison": comparison,
        "current": current,
        "current_suite": evaluation["report"].get("suite") if evaluation["report"] else None,
        "skip_reason": evaluation.get("reason"),
        "summary": comparison["summary"],
    }
    write_markdown(result, mode="check", path=md_path)
    return _json_safe(result)


# --------------------------------------------------------------------------- #
# markdown report
# --------------------------------------------------------------------------- #
def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_delta(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.4f}"


def _fmt_triple(block: Any) -> str:
    block = block if isinstance(block, dict) else {}
    return (
        f"orig {_fmt(block.get('original'))} / "
        f"opt {_fmt(block.get('optimized'))} / "
        f"repair {_fmt(block.get('repair'))}"
    )


def _board_table(boards: Sequence[Dict[str, Any]]) -> List[str]:
    lines = [
        "| 板 | case | 源 SHA256 | 器件 | nets | 多边形点 | keepouts | 机械固定 | "
        "completion orig/opt/repair | truth_v2 orig/opt/repair |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for board in boards:
        metrics = board.get("metrics") or {}
        orig = metrics.get("original") or {}
        opt = metrics.get("optimized") or {}
        rep = metrics.get("repair") or {}
        lines.append(
            f"| {board.get('name')} | `{board.get('case')}` | "
            f"`{str(board.get('source_sha256') or '')[:12]}` | {board.get('components')} | "
            f"{board.get('nets')} | {board.get('polygon_points')} | "
            f"{board.get('keepout_status')}/{board.get('keepouts')} | "
            f"{board.get('mechanical_fixed_count')} | "
            f"{_fmt(orig.get('completion'))}/{_fmt(opt.get('completion'))}/"
            f"{_fmt(rep.get('completion'))} | "
            f"{_fmt(orig.get('truth_v2'))}/{_fmt(opt.get('truth_v2'))}/"
            f"{_fmt(rep.get('truth_v2'))} |"
        )
    return lines


def _check_table(comparison: Dict[str, Any]) -> List[str]:
    lines = [
        "| 检查 | 类型 | 基线 | 当前 | Δ | 容差 | 级别 | 结果 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for check in comparison.get("checks") or []:
        lines.append(
            f"| {check.get('name')} | {check.get('kind')} | "
            f"{_fmt(check.get('baseline'))} | {_fmt(check.get('current'))} | "
            f"{_fmt_delta(check.get('delta'))} | {check.get('tolerance')} | "
            f"{check.get('severity')} | "
            f"{'PASS' if check.get('passed') else ('WARN' if check.get('severity') == 'warning' else 'FAIL')} |"
        )
    return lines


def _drift_table(drifts: Sequence[Dict[str, Any]]) -> List[str]:
    if not drifts:
        return ["（无漂移，全部检查在容差内）"]
    lines = [
        "| 级别 | 检查 | 基线 | 当前 | Δ | 说明 |",
        "|---|---|---|---|---|---|",
    ]
    for drift in drifts:
        lines.append(
            f"| {drift.get('severity')} | {drift.get('name')} | "
            f"{_fmt(drift.get('baseline'))} | {_fmt(drift.get('current'))} | "
            f"{_fmt_delta(drift.get('delta'))} | {drift.get('note')} |"
        )
    return lines


def render_markdown(result: Dict[str, Any], mode: Optional[str] = None) -> str:
    """Render the realboard benchmark markdown report (``docs/REALBOARD.md``)."""
    mode = mode or result.get("mode", "check")
    lines: List[str] = []
    if mode == "update":
        baseline = result.get("baseline") or {}
        config = baseline.get("config") or {}
        suite = baseline.get("suite") or {}
        lines.append("# P4.9 真实板回归基准（冻结快照）\n")
        lines.append(f"- 状态：**UPDATED**（{len(baseline.get('boards') or [])} 板已冻结）")
        lines.append(f"- 基线文件：`{result.get('baseline_path')}`")
        lines.append(f"- 生成时间：{baseline.get('generated_at')}")
        lines.append(
            f"- 配置：steps={config.get('steps')}，seed={config.get('seed')}，"
            f"max_routes={config.get('max_routes')}；objective=`{config.get('objective')}`"
        )
        lines.append(
            f"- 环境：{baseline.get('environment')}"
        )
        lines.append(f"- 容差：{baseline.get('tolerances')}")
        lines.append(f"- 运行耗时：{result.get('runtime_s')} s\n")
        lines.append("## suite 均值\n")
        lines.append("| 指标 | original | optimized | repair |")
        lines.append("|---|---|---|---|")
        for key, label in (("mean_completion", "mean completion"), ("mean_truth_v2", "mean truth_v2")):
            block = suite.get(key) or {}
            lines.append(
                f"| {label} | {_fmt(block.get('original'))} | "
                f"{_fmt(block.get('optimized'))} | {_fmt(block.get('repair'))} |"
            )
        lines.append("")
        best = suite.get("best_board") or {}
        worst = suite.get("worst_board") or {}
        lines.append(
            f"- 最好板：**{best.get('name')}**（repair completion "
            f"{_fmt(best.get('completion_original'))}→{_fmt(best.get('completion_repair'))}，"
            f"truth_v2 {_fmt(best.get('truth_v2_original'))}→{_fmt(best.get('truth_v2_repair'))}）"
        )
        lines.append(
            f"- 最差板：**{worst.get('name')}**（repair completion "
            f"{_fmt(worst.get('completion_original'))}→{_fmt(worst.get('completion_repair'))}，"
            f"truth_v2 {_fmt(worst.get('truth_v2_original'))}→{_fmt(worst.get('truth_v2_repair'))}）"
        )
        lines.append(f"- 排名规则：{suite.get('ranking') or '—'}\n")
        lines.append("## 板级指标\n")
        lines.extend(_board_table(baseline.get("boards") or []))
        lines.append("")
    else:
        lines.append("# P4.9 真实板回归检查（baseline vs current）\n")
        comparison = result.get("comparison") or {}
        baseline = result.get("current")
        baseline_status = result.get("baseline_status") or {}
        lines.append(f"- 状态：**{result.get('status')}**")
        lines.append(f"- 基线文件：`{result.get('baseline_path')}`（{baseline_status.get('status')}）")
        lines.append(f"- 报告文件：`{result.get('md_path')}`")
        lines.append(f"- 运行耗时：{result.get('runtime_s')} s")
        if result.get("status") in ("NO BASELINE", "SKIP", "INVALID"):
            lines.append(f"- 说明：{comparison.get('summary') or result.get('summary')}")
            if result.get("skip_reason"):
                lines.append(f"- 跳过原因：{result.get('skip_reason')}")
            lines.append("")
            lines.append("> 未执行漂移比较；运行 `python -m mp_place.realboard_benchmark --update-baseline` 冻结基线。")
            return "\n".join(lines) + "\n"
        meta = comparison.get("baseline") or {}
        lines.append(f"- 基线生成：{meta.get('generated_at')}（schema `{meta.get('schema')}`）")
        lines.append(
            f"- 容差：truth 相对劣化 ≤+{100 * float((comparison.get('tolerances') or {}).get('truth_relative_degradation', 0.05)):.1f}%；"
            f"completion 下降 ≤{(comparison.get('tolerances') or {}).get('completion_drop', 0.02)}；"
            f"板数不减少"
        )
        lines.append(f"- {comparison.get('summary')}\n")
        current = result.get("current") or {}
        checks = comparison.get("checks") or []
        check_index = {check.get("name"): check for check in checks}

        def check_value(name, field):
            entry = check_index.get(name) or {}
            return entry.get(field)

        lines.append("## suite 均值（baseline vs current）\n")
        lines.append("| 指标 | baseline | current | Δ |")
        lines.append("|---|---|---|---|")
        for group in ("optimized", "repair"):
            for key, label in (("mean_completion", "mean completion"), ("mean_truth_v2", "mean truth_v2")):
                name = f"suite.{key}.{group}"
                lines.append(
                    f"| {label}（{group}） | {_fmt(check_value(name, 'baseline'))} | "
                    f"{_fmt(check_value(name, 'current'))} | "
                    f"{_fmt_delta(check_value(name, 'delta'))} |"
                )
        lines.append("")
        lines.append("## 板级指标（current）\n")
        lines.extend(_board_table(current.get("boards") or []))
        lines.append("")
        lines.append("## 漂移项\n")
        lines.extend(_drift_table(comparison.get("drifts") or []))
        lines.append("")
        lines.append("## 检查明细\n")
        lines.extend(_check_table(comparison))
        lines.append("")
    lines.append("## 边界与限制\n")
    for item in BENCHMARK_LIMITS:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(
        "> 本文件由 `python -m mp_place.realboard_benchmark` 自动生成；"
        "源 dump 只读、未施加布局、未运行 DRC/EDA。"
    )
    return "\n".join(lines) + "\n"


def write_markdown(result: Dict[str, Any], *, mode: Optional[str] = None, path: object = DEFAULT_MD_PATH) -> pathlib.Path:
    """Write the markdown report atomically and return its path."""
    target = pathlib.Path(path)
    _write_text_atomic(target, render_markdown(result, mode=mode))
    return target


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mp_place.realboard_benchmark",
        description=(
            "Freeze / check the realboard suite regression baseline "
            "(4 EasyCirq boards; truth/completion/board-count tolerances)."
        ),
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--update-baseline",
        action="store_true",
        help="run the suite and freeze docs/REALBOARD_BASELINE.json",
    )
    action.add_argument(
        "--check",
        action="store_true",
        help="run the suite and compare it with the frozen baseline (default action)",
    )
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), metavar="PATH", help="baseline JSON path")
    parser.add_argument("--md", default=str(DEFAULT_MD_PATH), metavar="PATH", help="markdown report path")
    parser.add_argument("--cases-root", default=None, help="EasyCirq cases root (default: resolved path)")
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        metavar="NAME=PATH",
        help="explicit dump NAME=PATH (repeatable; bypasses discovery, for CI/tests)",
    )
    parser.add_argument("--steps", type=int, default=None, help=f"solver move budget (default: {DEFAULT_STEPS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="solver/truth seed (default: 0)")
    parser.add_argument("--max-routes", type=int, default=DEFAULT_MAX_ROUTES, help=f"route_opt budget (default: {DEFAULT_MAX_ROUTES})")
    parser.add_argument("--json", action="store_true", help="print the compact JSON result on stdout")
    return parser


def _parse_sources(raw: Optional[Sequence[str]]) -> Optional[List[Tuple[str, pathlib.Path]]]:
    if not raw:
        return None
    sources: List[Tuple[str, pathlib.Path]] = []
    for spec in raw:
        if "=" not in spec:
            raise ValueError(f"--source expects NAME=PATH, got {spec!r}")
        name, path = spec.split("=", 1)
        if not name.strip() or not path.strip():
            raise ValueError(f"--source expects non-empty NAME and PATH, got {spec!r}")
        sources.append((name.strip(), pathlib.Path(path.strip())))
    return sources


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    steps = args.steps if args.steps is not None else DEFAULT_STEPS
    if steps < 0:
        parser.error("--steps must be >= 0")
    if args.max_routes < 1:
        parser.error("--max-routes must be >= 1")
    if args.seed < 0:
        parser.error("--seed must be >= 0")
    try:
        sources = _parse_sources(args.source)
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    common = dict(
        sources=sources,
        cases_root=pathlib.Path(args.cases_root) if args.cases_root else None,
        steps=steps,
        seed=args.seed,
        max_routes=args.max_routes,
    )
    try:
        if args.update_baseline:
            result = update_baseline(
                baseline_path=pathlib.Path(args.baseline),
                md_path=pathlib.Path(args.md),
                **common,
            )
            exit_code = 0
        else:
            result = check_baseline(
                baseline_path=pathlib.Path(args.baseline),
                md_path=pathlib.Path(args.md),
                **common,
            )
            exit_code = 0 if result.get("status") in ("PASS", "NO BASELINE", "SKIP", "UPDATED") else 1
    except (BenchmarkError, OSError, ValueError, KeyError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(_json_safe(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(f"realboard-benchmark: {result.get('status')} (mode={result.get('mode')})")
        if result.get("summary"):
            print(f"  {result.get('summary')}")
        if result.get("baseline_path"):
            print(f"  baseline: {result.get('baseline_path')}")
        print(f"  md: {result.get('md_path')}")
        comparison = result.get("comparison") or {}
        for drift in comparison.get("drifts") or []:
            print(
                f"  drift[{drift.get('severity')}] {drift.get('name')}: "
                f"{_fmt(drift.get('baseline'))} -> {_fmt(drift.get('current'))} ({drift.get('note')})"
            )
    print(f"[realboard-benchmark] wrote {result.get('md_path')}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASELINE_SCHEMA",
    "COMPARISON_SCHEMA",
    "DEFAULT_BASELINE_PATH",
    "DEFAULT_MD_PATH",
    "DEFAULT_STEPS",
    "TOLERANCES",
    "BenchmarkError",
    "collect_baseline",
    "validate_baseline",
    "load_baseline",
    "save_baseline",
    "read_baseline_status",
    "strip_volatile_baseline",
    "compare_to_baseline",
    "run_suite",
    "evaluate_current",
    "update_baseline",
    "check_baseline",
    "render_markdown",
    "write_markdown",
    "main",
]
