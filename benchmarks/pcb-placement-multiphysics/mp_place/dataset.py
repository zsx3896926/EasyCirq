"""P2-E: streaming sampling + deterministic JSON cache for placement datasets.

The dataset is the reproducible bridge between the offline simulator (truth
model) and the learned surrogate::

    placement --extract_features--> f --feature_vector--> X row
                                     \\--simulator.score_features(f)--> y row

Design contracts
----------------
* **Determinism** — for a fixed ``(scenario, simulator, n, seed)`` the generated
  dataset and the exported file bytes are identical across runs and processes:
  the random stream is derived from ``scenario.name`` + ``seed`` only, JSON is
  written key-sorted/compact, and gzip headers use ``mtime=0`` so no timestamp
  leaks into the cache.  No wall-clock data is stored in ``meta``.
* **Streaming / bounded memory** — :func:`build_dataset` pulls placements one at
  a time from :func:`iter_layouts`; it never keeps the list of ``Placement``
  dicts, only the 10-float feature rows, the truth values and an incremental
  SHA-256.  Memory therefore grows as ``O(n * 10)`` floats (~3 MB at n=10k),
  not as ``O(n * components)``.
* **Cache** — :func:`save_dataset` / :func:`load_dataset` round-trip a dataset
  as JSON (``.gz`` suffix selects gzip); :func:`load_or_build_dataset` reuses a
  cache file only when its meta fingerprints still match the current scenario
  and simulator.

The module is pure standard library and does not import or modify the stable
modules beyond ``model`` / ``features`` / ``solver`` (see INTERFACES.md).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import os
import random
import zlib
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .features import FEATURE_NAMES, extract_features, feature_vector
from .model import Placement, Scenario, hard_violations
from .solver import random_feasible_placement

#: Version tag stored in ``dataset["meta"]["schema"]`` and checked on load.
DATASET_SCHEMA = "mp_place.dataset/v1"

#: Top-level keys of a dataset dict (extra keys are tolerated on load, not on
#: save — the writer always emits exactly these four).
TOP_LEVEL_KEYS: Tuple[str, ...] = ("meta", "X", "y", "placements_hash")

#: How many whole-placement retries are attempted when a random feasible
#: placement cannot be constructed for a sample (should never trigger for the
#: bundled scenarios; guards tiny/over-full custom boards).
MAX_PLACEMENT_ATTEMPTS = 25

_HEX_DIGITS = set("0123456789abcdef")


# --------------------------------------------------------------------------- #
# deterministic random stream
# --------------------------------------------------------------------------- #
def _mix_seed(name: str, seed: int) -> int:
    """Derive a stable RNG seed from a scenario name and an integer seed.

    Mirrors the derivation used by ``objective.PhysicsSimulator`` so the whole
    project has one reproducible seeding convention.
    """
    return (zlib.crc32(name.encode("utf-8")) ^ ((int(seed) * 2654435761) & 0xFFFFFFFF)) & 0xFFFFFFFF


def iter_layouts(scenario: Scenario, n: int = 100, seed: int = 0) -> Iterator[Placement]:
    """Yield ``n`` random hard-feasible layouts, lazily and deterministically.

    Sampling is uniform-feasible via ``solver.random_feasible_placement``; a
    placement that would violate a hard constraint (defensive check) or cannot
    be constructed is retried within the same deterministic random stream.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be >= 0")
    rng = random.Random(_mix_seed(scenario.name, seed))
    for index in range(n):
        placement: Optional[Placement] = None
        for _attempt in range(MAX_PLACEMENT_ATTEMPTS):
            try:
                candidate = random_feasible_placement(scenario, rng)
            except RuntimeError:
                continue
            if not hard_violations(scenario, candidate):
                placement = candidate
                break
        if placement is None:
            raise RuntimeError(
                "could not sample a feasible layout "
                f"(scenario={scenario.name}, sample={index}, attempts={MAX_PLACEMENT_ATTEMPTS})"
            )
        yield placement


def sample_layouts(
    scenario: Scenario,
    simulator: Optional[Any] = None,
    n: int = 100,
    seed: int = 0,
) -> List[Placement]:
    """Return ``n`` random hard-feasible layouts (``list[Placement]``).

    ``simulator`` is accepted for pipeline symmetry with :func:`build_dataset`
    (integration code may pass ``None``, which is a no-op here); sampling itself
    never scores layouts, so the same scenario/seed yields the same placements
    for every simulator — a fair comparison across truth models.
    """
    return list(iter_layouts(scenario, n=n, seed=seed))


# --------------------------------------------------------------------------- #
# determinism fingerprints / canonical encodings
# --------------------------------------------------------------------------- #
def _num(value: float) -> str:
    """Canonical decimal spelling for hashing fingerprints (12 significant digits)."""
    return format(float(value), ".12g")


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Best-effort JSON-safe projection used by the simulator fingerprint."""
    if depth > 4:
        return None
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _num(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(value[key], depth + 1)
            for key in sorted(value.keys(), key=lambda item: str(item))
        }
    return None


def scenario_fingerprint(scenario: Scenario) -> str:
    """SHA-256 of the canonical electrical/mechanical description of a scenario.

    Used as a cache key so a dataset built for a different board/netlist is
    never silently reused.
    """
    components = []
    for ref in sorted(scenario.components):
        comp = scenario.components[ref]
        components.append(
            {
                "ref": ref,
                "kind": comp.kind,
                "w": _num(comp.w),
                "h": _num(comp.h),
                "fixed": bool(comp.fixed),
                "rotations": [int(rot) for rot in comp.rotations],
                "power_w": _num(comp.power_w),
                "edge": comp.edge,
                "pins": {
                    name: [_num(dx), _num(dy)]
                    for name, (dx, dy) in sorted(comp.pins.items())
                },
            }
        )
    nets = [
        {"name": net.name, "cls": net.cls, "pins": [[ref, pin] for ref, pin in net.pins]}
        for net in scenario.nets
    ]
    payload = {
        "name": scenario.name,
        "board": [_num(scenario.board_w), _num(scenario.board_h)],
        "edge_tol": _num(scenario.edge_tol),
        "components": components,
        "nets": nets,
        "keepouts": [[_num(value) for value in rect] for rect in scenario.keepouts],
        "base_placement": {
            ref: [_num(x), _num(y), int(rot)]
            for ref, (x, y, rot) in sorted(scenario.base_placement.items())
        },
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _canonical_simulator(simulator: Any) -> Dict[str, Any]:
    """Describe a simulator by class name plus its public coefficient attributes."""
    data: Dict[str, Any] = {"class": type(simulator).__name__}
    attributes = getattr(simulator, "__dict__", None)
    if isinstance(attributes, Mapping):
        for key in sorted(attributes):
            if key == "scenario":  # already captured by scenario_fingerprint
                continue
            safe = _json_safe(attributes[key])
            if safe is not None or attributes[key] is None:
                data[key] = safe
    return data


def simulator_fingerprint(simulator: Any) -> str:
    """SHA-256 over the simulator class + its coefficient attributes.

    This makes the cache sensitive to a changed truth model (e.g. v1 vs v2
    physics, or the same class constructed with a different seed) while still
    working for duck-typed simulators that only expose ``score_features``.
    """
    blob = json.dumps(
        _canonical_simulator(simulator), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _layout_record(placement: Placement) -> bytes:
    """Canonical byte record of one placement, used by the incremental hash."""
    parts = [
        [ref, repr(float(placement[ref][0])), repr(float(placement[ref][1])), int(placement[ref][2])]
        for ref in sorted(placement)
    ]
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
# dataset construction (streaming)
# --------------------------------------------------------------------------- #
def _require_scorer(simulator: Any):
    scorer = getattr(simulator, "score_features", None)
    if not callable(scorer):
        raise TypeError("simulator must provide score_features(f: dict) -> float")
    return scorer


def _finite_vector(values: Sequence[Any], index: int) -> List[float]:
    row: List[float] = []
    for column, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {column} of sample {index} is not a real number: {value!r}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"feature {column} of sample {index} is not finite: {number!r}")
        row.append(number)
    return row


def iter_samples(
    scenario: Scenario, simulator: Any, n: int = 100, seed: int = 0
) -> Iterator[Tuple[List[float], float]]:
    """Yield ``(feature_vector, truth)`` pairs lazily, without keeping layouts.

    Useful for consumers that only need ``X``/``y`` (e.g. streaming a CSV or
    incrementally training a surrogate) and never want the whole dataset in
    memory.
    """
    scorer = _require_scorer(simulator)
    for index, placement in enumerate(iter_layouts(scenario, n=n, seed=seed)):
        features = extract_features(scenario, placement)
        row = _finite_vector(feature_vector(features), index)
        truth = float(scorer(features))
        if not math.isfinite(truth):
            raise ValueError(f"simulator returned a non-finite truth for sample {index}: {truth!r}")
        yield row, truth


def build_dataset(scenario: Scenario, simulator: Any, n: int = 100, seed: int = 0) -> Dict[str, Any]:
    """Build ``{"meta", "X", "y", "placements_hash"}`` with streaming sampling.

    * ``X[i]`` is ``feature_vector(extract_features(scenario, placements[i]))``
      (order fixed by ``FEATURE_NAMES``).
    * ``y[i]`` is ``simulator.score_features(features)`` ("truth").
    * ``placements_hash`` is a SHA-256 over the canonical placements in sample
      order, so two datasets can be compared without storing the layouts.

    For a fixed ``(scenario, simulator, n, seed)`` the returned dict (and the
    bytes written by :func:`save_dataset`) are fully deterministic.
    """
    scorer = _require_scorer(simulator)
    hasher = hashlib.sha256()
    features_rows: List[List[float]] = []
    truths: List[float] = []
    for index, placement in enumerate(iter_layouts(scenario, n=n, seed=seed)):
        features = extract_features(scenario, placement)
        row = _finite_vector(feature_vector(features), index)
        truth = float(scorer(features))
        if not math.isfinite(truth):
            raise ValueError(f"simulator returned a non-finite truth for sample {index}: {truth!r}")
        features_rows.append(row)
        truths.append(truth)
        hasher.update(_layout_record(placement))
        hasher.update(b"\n")
    meta = {
        "schema": DATASET_SCHEMA,
        "scenario": scenario.name,
        "scenario_fingerprint": scenario_fingerprint(scenario),
        "n": len(features_rows),
        "seed": int(seed),
        "feature_names": list(FEATURE_NAMES),
        "simulator": {
            "class": type(simulator).__name__,
            "fingerprint": simulator_fingerprint(simulator),
        },
        "board_mm": [float(scenario.board_w), float(scenario.board_h)],
        "n_components": len(scenario.components),
        "n_nets": len(scenario.nets),
    }
    return {
        "meta": meta,
        "X": features_rows,
        "y": truths,
        "placements_hash": hasher.hexdigest(),
    }


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _is_real(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_dataset(dataset: Any) -> None:
    """Raise ``ValueError`` when a dataset dict is structurally invalid."""
    if not isinstance(dataset, dict):
        raise ValueError("dataset must be a dict")
    missing = [key for key in TOP_LEVEL_KEYS if key not in dataset]
    if missing:
        raise ValueError(f"dataset is missing keys: {missing}")
    meta = dataset["meta"]
    if not isinstance(meta, dict):
        raise ValueError("dataset['meta'] must be a dict")
    for key in (
        "schema",
        "scenario",
        "scenario_fingerprint",
        "n",
        "seed",
        "feature_names",
        "simulator",
    ):
        if key not in meta:
            raise ValueError(f"dataset['meta'] is missing key: {key}")
    if meta["schema"] != DATASET_SCHEMA:
        raise ValueError(
            f"unsupported dataset schema: {meta['schema']!r} (expected {DATASET_SCHEMA!r})"
        )
    if not isinstance(meta["scenario"], str):
        raise ValueError("dataset['meta']['scenario'] must be a string")
    if not isinstance(meta["scenario_fingerprint"], str):
        raise ValueError("dataset['meta']['scenario_fingerprint'] must be a string")
    if not isinstance(meta["simulator"], dict):
        raise ValueError("dataset['meta']['simulator'] must be a dict")
    if isinstance(meta["n"], bool) or not isinstance(meta["n"], int) or meta["n"] < 0:
        raise ValueError("dataset['meta']['n'] must be a non-negative integer")
    if isinstance(meta["seed"], bool) or not isinstance(meta["seed"], int):
        raise ValueError("dataset['meta']['seed'] must be an integer")
    names = meta["feature_names"]
    if not isinstance(names, list) or list(names) != list(FEATURE_NAMES):
        raise ValueError("dataset['meta']['feature_names'] must equal features.FEATURE_NAMES")

    rows = dataset["X"]
    truths = dataset["y"]
    if not isinstance(rows, list) or not isinstance(truths, list):
        raise ValueError("dataset['X'] and dataset['y'] must be lists")
    n = meta["n"]
    if len(rows) != n or len(truths) != n:
        raise ValueError(
            f"length mismatch: meta.n={n}, len(X)={len(rows)}, len(y)={len(truths)}"
        )
    width = len(FEATURE_NAMES)
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != width:
            raise ValueError(f"X[{index}] must be a list of {width} numbers")
        for column, value in enumerate(row):
            if not _is_real(value) or not math.isfinite(float(value)):
                raise ValueError(f"X[{index}][{column}] is not a finite number: {value!r}")
    for index, value in enumerate(truths):
        if not _is_real(value) or not math.isfinite(float(value)):
            raise ValueError(f"y[{index}] is not a finite number: {value!r}")

    digest = dataset["placements_hash"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in _HEX_DIGITS for char in digest)
    ):
        raise ValueError("dataset['placements_hash'] must be a 64-char lowercase hex digest")


# --------------------------------------------------------------------------- #
# cache I/O
# --------------------------------------------------------------------------- #
def _dump_dataset(dataset: Mapping[str, Any], text_stream) -> None:
    """Stream a dataset as deterministic compact JSON (key-sorted, no NaN)."""
    json.dump(
        dataset,
        text_stream,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _is_gzip_path(path: str) -> bool:
    return path.lower().endswith(".gz")


def save_dataset(dataset: Dict[str, Any], path: os.PathLike | str) -> str:
    """Write a dataset to ``path`` as deterministic JSON (gzip when ``.gz``).

    The serialisation is key-sorted and compact, numbers must be finite, and a
    gzip header is written with ``mtime=0`` / no embedded filename, so saving the
    same dataset twice yields byte-identical files.  Returns the path as a str.
    """
    _validate_dataset(dataset)
    file_path = os.fspath(path)
    if _is_gzip_path(file_path):
        with open(file_path, "wb") as raw:
            # filename="" / mtime=0 keep the gzip header free of path- or
            # timestamp-dependent data, so identical datasets save identically.
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
                text = io.TextIOWrapper(gz, encoding="utf-8", newline="\n", write_through=True)
                try:
                    _dump_dataset(dataset, text)
                    text.write("\n")
                    text.flush()
                finally:
                    text.detach()  # let the gzip context manager close the stream
    else:
        # Binary mode + explicit UTF-8 bytes keeps output identical on every OS
        # (text mode could translate newlines to CRLF on Windows).
        with open(file_path, "w", encoding="utf-8", newline="\n") as text:
            _dump_dataset(dataset, text)
            text.write("\n")
    return file_path


def _reject_constant(token: str):
    raise ValueError(f"non-finite JSON constant is not allowed in a dataset: {token}")


def load_dataset(path: os.PathLike | str) -> Dict[str, Any]:
    """Load and validate a dataset written by :func:`save_dataset`."""
    file_path = os.fspath(path)
    if _is_gzip_path(file_path):
        with gzip.open(file_path, "rt", encoding="utf-8") as stream:
            text = stream.read()
    else:
        with open(file_path, "r", encoding="utf-8") as stream:
            text = stream.read()
    data = json.loads(text, parse_constant=_reject_constant)
    _validate_dataset(data)
    return data


def dataset_matches(
    dataset: Mapping[str, Any],
    scenario: Scenario,
    simulator: Any,
    n: int,
    seed: int,
) -> bool:
    """True when a loaded dataset is still a valid cache for these inputs."""
    try:
        _validate_dataset(dataset)
    except (TypeError, ValueError):
        return False
    meta = dataset["meta"]
    simulator_meta = meta["simulator"]
    return bool(
        meta["n"] == n
        and meta["seed"] == int(seed)
        and meta["scenario"] == scenario.name
        and meta["scenario_fingerprint"] == scenario_fingerprint(scenario)
        and simulator_meta.get("fingerprint") == simulator_fingerprint(simulator)
        and simulator_meta.get("class") == type(simulator).__name__
        and list(meta["feature_names"]) == list(FEATURE_NAMES)
    )


def load_or_build_dataset(
    path: os.PathLike | str,
    scenario: Scenario,
    simulator: Any,
    n: int = 100,
    seed: int = 0,
    rebuild: bool = False,
) -> Dict[str, Any]:
    """Return a cached dataset from ``path`` when valid, else build and save one.

    The cache is reused only when meta fingerprints match the current scenario,
    simulator, ``n`` and ``seed``; otherwise the file is rebuilt and overwritten.
    Pass ``rebuild=True`` to force a rebuild.
    """
    file_path = os.fspath(path)
    if not rebuild and os.path.exists(file_path):
        try:
            cached = load_dataset(file_path)
        except (OSError, ValueError):
            cached = None  # corrupt/stale cache -> rebuild
        if cached is not None and dataset_matches(cached, scenario, simulator, n, seed):
            return cached
    dataset = build_dataset(scenario, simulator, n=n, seed=seed)
    save_dataset(dataset, file_path)
    return dataset


__all__ = [
    "DATASET_SCHEMA",
    "build_dataset",
    "dataset_matches",
    "iter_layouts",
    "iter_samples",
    "load_dataset",
    "load_or_build_dataset",
    "sample_layouts",
    "save_dataset",
    "scenario_fingerprint",
    "simulator_fingerprint",
]
