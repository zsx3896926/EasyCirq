#!/usr/bin/env python3
"""Offline layout benchmark for the v2 layout engine (corpus + scoring).

Self-contained: no EDA, no network, no imports from other wave-0 layout
modules.  It reads the measured block footprints from
``easycirq/assets/block-envelopes.json``, enumerates deterministic module
combinations of a given size, estimates the minimum number of A4 pages from
the usable page area, checks feasibility with a simple internal first-fit
packer, and reports per-combination metrics plus aggregates.

Geometry (from ``docs/method/layout-engine-v2-contract.md`` and the envelope
asset): page 1170x825, margin 12, title-block keep-out
``[610..1170] x [12..380]``.  The usable region is the L-shape left of and
below the title block.

Usage::

    python tools/layout2/benchmark.py --sizes 2,3 --top 10 --out bench.json

The run is deterministic: corpus selection is seeded by SHA-256 of the sorted
block ids, module ids are stable, and the JSON payload contains no timestamps.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENVELOPES = ROOT / "easycirq" / "assets" / "block-envelopes.json"

SCHEMA = "easycirq-layout2-benchmark/v1"

#: Page geometry fallbacks, per the v2 contract.  The envelope asset normally
#: carries the same values, which take precedence when present.
DEFAULT_PAGE = {"width": 1170, "height": 825, "margin": 12}
DEFAULT_TITLE_BLOCK = {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380}

DEFAULT_SIZES = (1, 2, 3, 4)
#: The v2 benchmark contract only defines combination sizes 1..4.
MAX_CORPUS_SIZE = 4
#: Per-size corpus cap so a full run stays fast (0 = no cap).
DEFAULT_MAX_COMBOS = 40
#: How many extra pages the packer may try beyond the area lower bound before
#: a combination is scored ``fail``.
MAX_EXTRA_PAGES = 2

VERDICT_FIT = "fit"      # packed inside the area lower bound
VERDICT_OVER = "over"    # packed, but needed more pages than the lower bound
VERDICT_FAIL = "fail"    # packer could not fit the set within the page budget

_PACKER_PAGE_EXTRA = MAX_EXTRA_PAGES


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in schematic units (0.01 inch)."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.max_x < self.min_x or self.max_y < self.min_y:
            raise ValueError(f"inverted rect: {self!r}")

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_json(self) -> dict:
        return {
            "minX": self.min_x,
            "minY": self.min_y,
            "maxX": self.max_x,
            "maxY": self.max_y,
        }


def intersect(a: Rect, b: Rect) -> Rect | None:
    """Overlap of two rectangles, or ``None`` when they are disjoint."""
    min_x = max(a.min_x, b.min_x)
    min_y = max(a.min_y, b.min_y)
    max_x = min(a.max_x, b.max_x)
    max_y = min(a.max_y, b.max_y)
    if max_x <= min_x or max_y <= min_y:
        return None
    return Rect(min_x, min_y, max_x, max_y)


def subtract(outer: Rect, cutter: Rect) -> list[Rect]:
    """``outer`` minus ``cutter`` as a list of non-overlapping rectangles."""
    overlap = intersect(outer, cutter)
    if overlap is None:
        return [outer]
    # Left / right slabs use the full height; bottom / top slabs only span the
    # cutter's x-range.  That keeps the pieces disjoint with no duplication.
    left = Rect(outer.min_x, outer.min_y, overlap.min_x, outer.max_y)
    right = Rect(overlap.max_x, outer.min_y, outer.max_x, outer.max_y)
    bottom = Rect(overlap.min_x, outer.min_y, overlap.max_x, overlap.min_y)
    top = Rect(overlap.min_x, overlap.max_y, overlap.max_x, outer.max_y)
    return [r for r in (left, right, bottom, top) if r.width > 0 and r.height > 0]


def _contains(outer: Rect, inner: Rect) -> bool:
    return (
        outer.min_x <= inner.min_x
        and outer.min_y <= inner.min_y
        and outer.max_x >= inner.max_x
        and outer.max_y >= inner.max_y
    )


def sort_rects(rects: list[Rect]) -> list[Rect]:
    """Deterministic order: largest first, then by position."""
    return sorted(rects, key=lambda r: (-r.area, r.min_y, r.min_x))


# ---------------------------------------------------------------------------
# Page template -> usable region
# ---------------------------------------------------------------------------
def page_geometry(envelopes: dict) -> dict:
    """Return the page/title-block geometry and the usable L-shaped region.

    Usable area = inner page rectangle (margin removed) minus the clipped
    title-block keep-out.
    """
    page = envelopes.get("page") or {}
    width = int(page.get("width", DEFAULT_PAGE["width"]))
    height = int(page.get("height", DEFAULT_PAGE["height"]))
    margin = int(page.get("margin", DEFAULT_PAGE["margin"]))
    if width <= 2 * margin or height <= 2 * margin:
        raise ValueError(f"page {width}x{height} with margin {margin} has no interior")

    raw_tb = page.get("title_block") or {}
    title_block = Rect(
        int(raw_tb.get("minX", DEFAULT_TITLE_BLOCK["minX"])),
        int(raw_tb.get("minY", DEFAULT_TITLE_BLOCK["minY"])),
        int(raw_tb.get("maxX", DEFAULT_TITLE_BLOCK["maxX"])),
        int(raw_tb.get("maxY", DEFAULT_TITLE_BLOCK["maxY"])),
    )

    inner = Rect(margin, margin, width - margin, height - margin)
    usable = sort_rects(subtract(inner, title_block))
    if not usable:
        raise ValueError(f"title block leaves no usable area on {width}x{height}")

    return {
        "width": width,
        "height": height,
        "margin": margin,
        "title_block": title_block,
        "inner": inner,
        "usable_rects": usable,
        "usable_area": sum(r.area for r in usable),
    }


def estimate_page_lower_bound(total_area: float, usable_area: float) -> int:
    """Area-only lower bound on the number of pages (>= 1)."""
    if usable_area <= 0:
        raise ValueError("usable_area must be positive")
    if total_area <= 0:
        return 1
    return max(1, int(math.ceil(total_area / usable_area)))


# ---------------------------------------------------------------------------
# Simple internal first-fit packer (no rotation, deterministic)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Module:
    name: str
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


def _first_fit(free: list[Rect], width: float, height: float) -> int | None:
    for index, rect in enumerate(free):
        if width <= rect.width and height <= rect.height:
            return index
    return None


def _prune_free(free: list[Rect]) -> None:
    """Drop free rects fully contained in another (keeps the list monotone)."""
    if len(free) < 2:
        return
    drop: set[int] = set()
    for i, inner in enumerate(free):
        if i in drop:
            continue
        for j, outer in enumerate(free):
            if i == j:
                continue
            if inner == outer:
                if j < i:
                    drop.add(i)
                continue
            if _contains(outer, inner):
                drop.add(i)
                break
    if drop:
        free[:] = [r for k, r in enumerate(free) if k not in drop]


def _split_free(free: list[Rect], index: int, width: float, height: float) -> None:
    rect = free.pop(index)
    if rect.width - width > 0:
        free.append(Rect(rect.min_x + width, rect.min_y, rect.max_x, rect.max_y))
    if rect.height - height > 0:
        free.append(Rect(rect.min_x, rect.min_y + height, rect.max_x, rect.max_y))
    _prune_free(free)


def pack_pages(
    modules: list[Module],
    base_free: list[Rect],
    page_limit: int,
) -> tuple[list[list[dict]], list[Module]]:
    """First-fit pack ``modules`` into at most ``page_limit`` fresh pages.

    Modules keep their given order (callers pass largest-area-first).  Each
    module goes to the first free rectangle that can hold it; a new page is
    opened only after every page-local slot has been tried.  Returns the
    placements per page and the modules that did not fit.
    """
    if page_limit < 1:
        raise ValueError("page_limit must be >= 1")
    pending = list(modules)
    pages: list[list[dict]] = []
    while pending and len(pages) < page_limit:
        free = list(base_free)
        placed: list[dict] = []
        leftover: list[Module] = []
        for module in pending:
            index = _first_fit(free, module.width, module.height)
            if index is None:
                leftover.append(module)
                continue
            rect = free[index]
            placed.append(
                {
                    "id": module.name,
                    "x": rect.min_x,
                    "y": rect.min_y,
                    "w": module.width,
                    "h": module.height,
                }
            )
            _split_free(free, index, module.width, module.height)
        if not placed:
            # Nothing fits on a fresh page: more pages cannot help.
            break
        pages.append(placed)
        pending = leftover
    return pages, pending


def _modules_for(envelopes: dict, names: tuple[str, ...]) -> list[Module]:
    blocks = envelopes["blocks"]
    modules = [
        Module(name=name, width=float(blocks[name]["w"]), height=float(blocks[name]["h"]))
        for name in names
    ]
    return sorted(modules, key=lambda m: (-m.area, m.name))


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
def normalize_sizes(sizes) -> tuple[int, ...]:
    """Validate and canonicalise a size selection (1..4, ascending, unique)."""
    if sizes is None:
        return DEFAULT_SIZES
    try:
        parsed = {int(size) for size in sizes}
    except (TypeError, ValueError) as exc:
        raise ValueError(f"sizes must be integers, got {sizes!r}") from exc
    if not parsed:
        raise ValueError("sizes must not be empty")
    bad = sorted(size for size in parsed if size < 1 or size > MAX_CORPUS_SIZE)
    if bad:
        raise ValueError(
            f"sizes out of range 1..{MAX_CORPUS_SIZE}: {bad}"
        )
    return tuple(sorted(parsed))


def parse_sizes(text: str) -> tuple[int, ...]:
    """Parse ``--sizes`` (``"2,3"``) into a canonical tuple."""
    parts = [part.strip() for part in str(text).split(",")]
    if any(not part for part in parts):
        raise ValueError(f"invalid --sizes value: {text!r}")
    return normalize_sizes(parts)


def _combo_digest(names: tuple[str, ...]) -> str:
    return hashlib.sha256("\x1f".join(names).encode("utf-8")).hexdigest()


def build_corpus(
    envelopes: dict,
    sizes=DEFAULT_SIZES,
    max_combos: int = DEFAULT_MAX_COMBOS,
) -> list[dict]:
    """Deterministic combination corpus.

    Combinations of each requested size are ranked by SHA-256 of their sorted
    block ids and truncated to ``max_combos`` per size (0 = no cap).  The hash
    ranking avoids the order bias of plain ``itertools.combinations`` while
    staying reproducible across runs and machines.
    """
    selected = normalize_sizes(sizes)
    if max_combos < 0:
        raise ValueError("max_combos must be >= 0")
    names = sorted(envelopes["blocks"])
    if len(names) < max(selected):
        raise ValueError(
            f"need at least {max(selected)} blocks, asset has {len(names)}"
        )

    corpus: list[dict] = []
    for size in selected:
        combos = sorted(
            itertools.combinations(names, size),
            key=lambda combo: (_combo_digest(combo), combo),
        )
        if max_combos:
            combos = combos[:max_combos]
        for index, combo in enumerate(combos):
            corpus.append(
                {"id": f"s{size}-{index:04d}", "size": size, "modules": list(combo)}
            )
    return corpus


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def score_combo(
    combo: dict,
    envelopes: dict,
    geometry: dict,
    max_extra: int = _PACKER_PAGE_EXTRA,
) -> dict:
    """Score one combination: lower bound, packed pages, utilization, verdict."""
    modules = _modules_for(envelopes, tuple(combo["modules"]))
    total_area = sum(module.area for module in modules)
    usable_area = geometry["usable_area"]
    lower_bound = estimate_page_lower_bound(total_area, usable_area)

    pages: list[list[dict]] | None = None
    pages_used: int | None = None
    for extra in range(0, max_extra + 1):
        limit = lower_bound + extra
        attempt, leftover = pack_pages(modules, geometry["usable_rects"], limit)
        if not leftover and attempt:
            pages, pages_used = attempt, limit
            break

    if pages is None:
        verdict = VERDICT_FAIL
        utilization = None
    elif pages_used == lower_bound:
        verdict = VERDICT_FIT
        utilization = total_area / (pages_used * usable_area)
    else:
        verdict = VERDICT_OVER
        utilization = total_area / (pages_used * usable_area)

    page_modules = (
        [[placed["id"] for placed in page] for page in pages] if pages else None
    )
    return {
        "id": combo["id"],
        "size": combo["size"],
        "modules": list(combo["modules"]),
        "module_count": len(modules),
        "module_area": round(total_area, 4),
        "page_usable_area": round(usable_area, 4),
        "page_count_lower_bound": lower_bound,
        "pages_used": pages_used,
        "page_modules": page_modules,
        "estimated_utilization": (
            round(utilization, 4) if utilization is not None else None
        ),
        "fit_verdict": verdict,
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _aggregate_rows(results: list[dict], key: int | None) -> dict:
    subset = results if key is None else [r for r in results if r["size"] == key]
    utils = [r["estimated_utilization"] for r in subset if r["estimated_utilization"] is not None]
    used_pages = [r["pages_used"] for r in subset if r["pages_used"] is not None]
    bounds = [r["page_count_lower_bound"] for r in subset]
    counts = Counter(r["fit_verdict"] for r in subset)
    total = len(subset)
    return {
        "combinations": total,
        "fit": counts.get(VERDICT_FIT, 0),
        "over": counts.get(VERDICT_OVER, 0),
        "fail": counts.get(VERDICT_FAIL, 0),
        "pass_rate": round(counts.get(VERDICT_FIT, 0) / total, 4) if total else 0.0,
        "mean_estimated_utilization": _mean(utils),
        "mean_pages_used": _mean([float(p) for p in used_pages]),
        "mean_page_count_lower_bound": _mean([float(b) for b in bounds]),
    }


def aggregate(results: list[dict], sizes: tuple[int, ...]) -> dict:
    by_size = []
    for size in sizes:
        row = _aggregate_rows(results, size)
        by_size.append(
            {
                "size": size,
                "combinations": row["combinations"],
                "fit": row["fit"],
                "over": row["over"],
                "fail": row["fail"],
                "pass_rate": row["pass_rate"],
                "mean_estimated_utilization": row["mean_estimated_utilization"],
                "mean_pages_used": row["mean_pages_used"],
                "mean_page_count_lower_bound": row["mean_page_count_lower_bound"],
            }
        )
    overall = {
        "combinations": len(results),
        "fit": sum(row["fit"] for row in by_size),
        "over": sum(row["over"] for row in by_size),
        "fail": sum(row["fail"] for row in by_size),
        "pass_rate": (
            round(sum(row["fit"] for row in by_size) / len(results), 4)
            if results
            else 0.0
        ),
        "mean_estimated_utilization": _mean(
            [r["estimated_utilization"] for r in results if r["estimated_utilization"] is not None]
        ),
    }
    overall["sizes"] = [row["size"] for row in by_size]
    overall["by_size"] = by_size
    return overall


def _example(result: dict) -> dict:
    return {
        "id": result["id"],
        "size": result["size"],
        "modules": list(result["modules"]),
        "page_count_lower_bound": result["page_count_lower_bound"],
        "pages_used": result["pages_used"],
        "estimated_utilization": result["estimated_utilization"],
        "fit_verdict": result["fit_verdict"],
    }


def examples(results: list[dict], top: int) -> dict:
    """Best/worst combinations by estimated utilization."""
    if top < 0:
        raise ValueError("top must be >= 0")
    ranked = sorted(
        results,
        key=lambda r: (
            -(r["estimated_utilization"] if r["estimated_utilization"] is not None else -1.0),
            r["id"],
        ),
    )
    worst = sorted(
        results,
        key=lambda r: (
            (r["estimated_utilization"] if r["estimated_utilization"] is not None else -1.0),
            r["id"],
        ),
    )
    return {
        "top": [_example(r) for r in ranked[:top]],
        "bottom": [_example(r) for r in worst[:top]],
    }


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def load_envelopes(path=None) -> tuple[dict, str, Path]:
    """Load the block envelope asset; returns ``(data, sha256, path)``."""
    asset = Path(path) if path is not None else DEFAULT_ENVELOPES
    asset = asset.resolve()
    raw = asset.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema") != "easycirq-block-envelopes/v1":
        raise ValueError(f"unexpected envelope schema: {data.get('schema')!r}")
    if not isinstance(data.get("blocks"), dict) or not data["blocks"]:
        raise ValueError(f"no blocks in envelope asset: {asset}")
    for name, block in data["blocks"].items():
        if not isinstance(block, dict) or "w" not in block or "h" not in block:
            raise ValueError(f"block {name!r} missing w/h")
        if float(block["w"]) <= 0 or float(block["h"]) <= 0:
            raise ValueError(f"block {name!r} has non-positive size")
    return data, digest, asset


def run_benchmark(
    *,
    sizes=DEFAULT_SIZES,
    max_combos: int = DEFAULT_MAX_COMBOS,
    top: int = 10,
    envelopes_path=None,
) -> dict:
    """Build the corpus, score every combination and return the report."""
    selected = normalize_sizes(sizes)
    if top < 0:
        raise ValueError("top must be >= 0")
    envelopes, digest, asset = load_envelopes(envelopes_path)
    geometry = page_geometry(envelopes)

    corpus = build_corpus(envelopes, selected, max_combos)
    results = [score_combo(combo, envelopes, geometry) for combo in corpus]
    results.sort(key=lambda r: (r["size"], r["id"]))

    source = asset.relative_to(ROOT).as_posix() if asset.is_relative_to(ROOT) else asset.as_posix()
    return {
        "schema": SCHEMA,
        "offline": True,
        "tool": "tools/layout2/benchmark.py",
        "page": {
            "width": geometry["width"],
            "height": geometry["height"],
            "margin": geometry["margin"],
            "title_block": geometry["title_block"].to_json(),
            "inner": geometry["inner"].to_json(),
            "usable_rects": [r.to_json() for r in geometry["usable_rects"]],
            "usable_area": geometry["usable_area"],
        },
        "corpus": {
            "source": source,
            "sha256": digest,
            "block_count": len(envelopes["blocks"]),
            "blocks": sorted(envelopes["blocks"]),
            "sizes": list(selected),
            "max_combos_per_size": max_combos,
            "combinations": len(corpus),
        },
        "aggregates": aggregate(results, selected),
        "examples": examples(results, top),
        "results": results,
    }


def write_report(path, report: dict) -> Path:
    """Write the report as stable, newline-terminated UTF-8 JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target.write_text(payload, encoding="utf-8", newline="\n")
    return target


def _summarize(report: dict, target: Path) -> str:
    lines = [
        f"schema: {report['schema']}",
        f"blocks: {report['corpus']['block_count']}  "
        f"combinations: {report['corpus']['combinations']}  "
        f"sizes: {','.join(str(s) for s in report['corpus']['sizes'])}",
    ]
    for row in report["aggregates"]["by_size"]:
        util = row["mean_estimated_utilization"]
        util_text = f"{util:.3f}" if util is not None else "n/a"
        lines.append(
            f"  size {row['size']}: n={row['combinations']} "
            f"pass={row['pass_rate']:.1%} "
            f"(fit={row['fit']} over={row['over']} fail={row['fail']}) "
            f"mean_util={util_text}"
        )
    overall = report["aggregates"]
    lines.append(
        f"overall: pass={overall['pass_rate']:.1%} "
        f"fit={overall['fit']} over={overall['over']} fail={overall['fail']}"
    )
    lines.append(f"wrote {target}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline layout v2 benchmark: deterministic block-combination corpus, "
            "area page lower bound, first-fit feasibility and utilization scores."
        )
    )
    parser.add_argument(
        "--sizes",
        default="1,2,3,4",
        help="comma-separated combination sizes (1..4), default: 1,2,3,4",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="number of best/worst examples to report (default: 10)",
    )
    parser.add_argument(
        "--max-combos",
        type=int,
        default=DEFAULT_MAX_COMBOS,
        dest="max_combos",
        help=(
            "cap combinations per size (default: 40; 0 = no cap; "
            "uncapped totals: 11/55/165/330)"
        ),
    )
    parser.add_argument(
        "--envelopes",
        default=None,
        help=f"block envelope asset (default: {DEFAULT_ENVELOPES})",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output JSON path; without it the report is printed to stdout",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        sizes = parse_sizes(args.sizes)
        if args.top < 0:
            raise ValueError("--top must be >= 0")
        if args.max_combos < 0:
            raise ValueError("--max-combos must be >= 0")
        report = run_benchmark(
            sizes=sizes,
            max_combos=args.max_combos,
            top=args.top,
            envelopes_path=args.envelopes,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.out is None:
        sys.stdout.write(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
    else:
        target = write_report(args.out, report)
        print(_summarize(report, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
