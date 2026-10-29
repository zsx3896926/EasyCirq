"""Measure an EasyEDA schematic page into ``easycirq-page-template/v1`` JSON.

Documented offline/one-shot wrapper around ``easycirq sch sheet-geometry``.
It reads the measured page + title-block geometry (live project readback or a
saved official SVG vector export), derives the usable regions with
:mod:`tools.layout2.page_template`, and writes a validated template document.

Usage
-----
Read a saved ``sheet-geometry --json`` payload (no EDA needed)::

    python tools/layout2/measure_page_template.py \
        --sheet-json sheet-geometry.json --out easycirq/assets/page-template.json

Run the live measurement for a loaded project/page::

    python tools/layout2/measure_page_template.py \
        --project <project> --doc <page-uuid> --out easycirq/assets/page-template.json

Run the exact vector measurement from an exported SVG::

    python tools/layout2/measure_page_template.py \
        --from-svg page.svg --out easycirq/assets/page-template.json

Options
-------
``--margin N``      Override the measured margin (the inner border is then
                    recomputed from the page; the measured value is recorded
                    in ``notes``).
``--out PATH``      Write the template JSON there (default: print to stdout).
``--easycirq PATH`` Executable used for the live/SVG readback (default:
                    ``$EASYCIRQ_BIN``, then ``easycirq`` on ``PATH``).

Exit codes: ``0`` success, ``2`` unreadable payload / invalid geometry, ``3``
the ``easycirq`` CLI failed or returned malformed JSON.

This wrapper is intentionally not unit-tested: it is a thin one-shot bridge
around the measured data source.  The loader/builder it calls are tested
offline in ``tests/test_layout2_page_template.py``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # normal package import: python -m tools.layout2.measure_page_template
    from . import page_template
except ImportError:  # direct script execution: python tools/layout2/...
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.layout2 import page_template  # type: ignore[no-redef]

_RECT_KEYS = ("minX", "minY", "maxX", "maxY")


class MeasurementError(RuntimeError):
    """The sheet geometry payload cannot be turned into a page template."""


def _rect_from_any(value: Any, field: str) -> page_template.Rect:
    """Accept a ``{minX,minY,maxX,maxY}`` object or ``[x, y, x2, y2]``."""
    if isinstance(value, Mapping):
        missing = [key for key in _RECT_KEYS if key not in value]
        if missing:
            raise MeasurementError("%s: missing %s" % (field, ", ".join(missing)))
        try:
            return page_template.Rect(
                *(float(value[key]) for key in _RECT_KEYS)
            )
        except (TypeError, ValueError) as exc:
            raise MeasurementError("%s: non-numeric rect: %s" % (field, exc)) from exc
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return page_template.Rect(*(float(item) for item in value))
        except (TypeError, ValueError) as exc:
            raise MeasurementError("%s: non-numeric rect: %s" % (field, exc)) from exc
    raise MeasurementError("%s: expected a rect object or 4 numbers, got %r" % (field, value))


def _shift(rect: page_template.Rect, dx: float, dy: float) -> page_template.Rect:
    return page_template.Rect(
        rect.minX - dx, rect.minY - dy, rect.maxX - dx, rect.maxY - dy
    )


def _unwrap(payload: Any) -> Mapping:
    if not isinstance(payload, Mapping):
        raise MeasurementError("sheet-geometry payload: expected a JSON object")
    result = payload.get("result")
    if isinstance(result, Mapping):
        return result
    if payload.get("ok") is False:
        raise MeasurementError(
            "sheet-geometry reported failure: %s"
            % json.dumps(payload.get("error", payload), ensure_ascii=False)
        )
    return payload


def geometry_from_payload(payload: Any) -> Dict[str, Any]:
    """Normalize a ``sch sheet-geometry --json`` payload to origin-based geometry."""
    data = _unwrap(payload)
    sheet = data.get("sheet")
    if not isinstance(sheet, Mapping):
        raise MeasurementError("sheet-geometry payload: missing 'sheet' object")
    page = _rect_from_any(sheet.get("bbox"), "sheet.bbox")
    origin_x, origin_y = page.minX, page.minY
    width, height = page.width, page.height
    if width <= 0 or height <= 0:
        raise MeasurementError("sheet.bbox: page has non-positive size %r" % (page.to_dict(),))

    inner_value = sheet.get("innerBBox")
    if inner_value is None:
        # Fall back to the page itself when the exporter did not report a border.
        inner = page_template.Rect(0.0, 0.0, width, height)
        margins = [0.0, 0.0, 0.0, 0.0]
    else:
        inner = _shift(_rect_from_any(inner_value, "sheet.innerBBox"), origin_x, origin_y)
        margins = [
            inner.minX,
            inner.minY,
            width - inner.maxX,
            height - inner.maxY,
        ]
    spread = max(margins) - min(margins)
    if spread > 1.0:
        raise MeasurementError(
            "sheet.innerBBox insets are not uniform (left/bottom/right/top = %s); "
            "the page template schema stores a single margin value"
            % ", ".join("%.3f" % value for value in margins)
        )
    margin = sum(margins) / 4.0

    title_data = data.get("titleBlock")
    title_block: Optional[page_template.Rect] = None
    visible: Optional[bool] = None
    if isinstance(title_data, Mapping):
        visible = title_data.get("visible") if isinstance(title_data.get("visible"), bool) else None
        if title_data.get("bbox") is not None:
            title_block = _shift(
                _rect_from_any(title_data["bbox"], "titleBlock.bbox"), origin_x, origin_y
            )
    if title_block is None:
        keepouts = data.get("keepouts")
        if isinstance(keepouts, Sequence):
            for keepout in keepouts:
                if not isinstance(keepout, Mapping):
                    continue
                if keepout.get("name") == "titleBlock" and keepout.get("bbox") is not None:
                    title_block = _shift(
                        _rect_from_any(keepout["bbox"], "keepouts.titleBlock.bbox"),
                        origin_x,
                        origin_y,
                    )
                    break
    if title_block is None:
        raise MeasurementError(
            "sheet-geometry payload: no titleBlock bbox (titleBlock.bbox or "
            "keepouts[name=titleBlock].bbox required)"
        )

    warnings = data.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    return {
        "width": width,
        "height": height,
        "margin": margin,
        "inner_border": inner,
        "title_block": title_block,
        "title_block_visible": visible,
        "warnings": [str(item) for item in warnings],
    }


def _run_sheet_geometry(easycirq: str, args: Sequence[str]) -> Any:
    command = [easycirq, "sch", "sheet-geometry", *args, "--json"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except OSError as exc:
        raise MeasurementError("cannot run %r: %s" % (command[0], exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise MeasurementError("easycirq sch sheet-geometry timed out") from exc
    stdout = completed.stdout or ""
    start = stdout.find("{")
    if completed.returncode != 0 or start < 0:
        detail = (completed.stderr or stdout or "").strip()
        raise MeasurementError(
            "easycirq sch sheet-geometry failed (exit %s): %s"
            % (completed.returncode, detail[:2000] or "<no output>")
        )
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError as exc:
        raise MeasurementError(
            "easycirq sch sheet-geometry returned non-JSON output: %s"
            % (stdout[:2000],)
        ) from exc


def _resolve_easycirq(explicit: Optional[str]) -> str:
    candidate = explicit or os.environ.get("EASYCIRQ_BIN") or ""
    if candidate:
        return candidate
    found = shutil.which("easycirq")
    if found:
        return found
    raise MeasurementError(
        "easycirq executable not found; pass --easycirq or set EASYCIRQ_BIN, "
        "or use --sheet-json with a saved payload"
    )


def _read_sheet_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MeasurementError("cannot read %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise MeasurementError(
            "%s: invalid JSON at line %s column %s: %s"
            % (path, exc.lineno, exc.colno, exc.msg)
        ) from exc


def _rect_close(left: page_template.Rect, right: page_template.Rect, tolerance: float = 1e-6) -> bool:
    return (
        abs(left.minX - right.minX) <= tolerance
        and abs(left.minY - right.minY) <= tolerance
        and abs(left.maxX - right.maxX) <= tolerance
        and abs(left.maxY - right.maxY) <= tolerance
    )


def _format_number(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else ("%.3f" % number).rstrip("0").rstrip(".")


def _build_document(
    geometry: Mapping[str, Any],
    *,
    margin_override: Optional[float],
    provenance: Mapping[str, Any],
    extra_notes: Sequence[str],
) -> Dict[str, Any]:
    measured_margin = float(geometry["margin"])
    if margin_override is None:
        margin = measured_margin
    else:
        margin = float(margin_override)
    expected_inner = page_template.Rect(
        margin, margin, float(geometry["width"]) - margin, float(geometry["height"]) - margin
    )
    measured_inner: page_template.Rect = geometry["inner_border"]
    margin_note: Optional[str] = None
    if margin_override is None and _rect_close(measured_inner, expected_inner):
        inner_border: Optional[Dict[str, float]] = measured_inner.to_dict()
    else:
        # A single scalar margin cannot represent a non-uniform measured border;
        # recompute the inner border from the page + margin and record the delta.
        inner_border = None
        if margin_override is not None:
            margin_note = (
                "margin overridden to %s by measure_page_template.py "
                "(measured inner-border inset was %s)"
                % (_format_number(margin), _format_number(measured_margin))
            )
        elif not _rect_close(measured_inner, expected_inner, tolerance=1e-3):
            margin_note = (
                "measured inner border %s was normalized to a uniform margin of %s"
                % (measured_inner.to_dict(), _format_number(margin))
            )
    notes: List[str] = list(extra_notes)
    notes.extend(str(item) for item in geometry.get("warnings", []))
    if margin_note:
        notes.append(margin_note)
    title_block: Dict[str, Any] = {
        "rect": geometry["title_block"].to_dict(),
    }
    if geometry.get("title_block_visible") is not None:
        title_block["visible"] = bool(geometry["title_block_visible"])
    return page_template.build_template_document(
        {
            "width": geometry["width"],
            "height": geometry["height"],
            "margin": margin,
        },
        title_block,
        margin=margin,
        inner_border=inner_border,
        provenance=dict(provenance),
        notes=notes,
        measured_at=datetime.date.today().isoformat(),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="measure_page_template.py",
        description=(
            "Measure EasyEDA sheet geometry into a validated "
            "easycirq-page-template/v1 JSON (offline-friendly wrapper around "
            "easycirq sch sheet-geometry)."
        ),
        epilog=(
            "examples:\n"
            "  measure_page_template.py --sheet-json sheet.json --out page-template.json\n"
            "  measure_page_template.py --project P --doc PAGE --out page-template.json\n"
            "  measure_page_template.py --from-svg page.svg --out page-template.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sheet-json", metavar="PATH",
                        help="read a saved 'sch sheet-geometry --json' payload")
    source.add_argument("--from-svg", metavar="PATH",
                        help="run the exact vector measurement on an exported page SVG")
    source.add_argument("--project", metavar="PROJECT",
                        help="live project measurement (requires --doc)")
    parser.add_argument("--doc", metavar="PAGE_UUID",
                        help="page UUID for --project")
    parser.add_argument("--margin", type=float, metavar="N",
                        help="override the measured margin (inner border is recomputed)")
    parser.add_argument("--out", metavar="PATH",
                        help="write the template JSON to PATH (default: stdout)")
    parser.add_argument("--easycirq", metavar="PATH",
                        help="easycirq executable (default: $EASYCIRQ_BIN or PATH)")
    parser.add_argument("--note", action="append", default=[], metavar="TEXT",
                        help="extra note to record in the template (repeatable)")
    args = parser.parse_args(argv)

    if args.project and not args.doc:
        parser.error("--project requires --doc")
    if args.doc and not args.project:
        parser.error("--doc requires --project")
    if args.margin is not None and args.margin < 0:
        parser.error("--margin must be >= 0")

    try:
        if args.sheet_json:
            payload = _read_sheet_json(Path(args.sheet_json))
            provenance: Dict[str, Any] = {
                "command": "easycirq sch sheet-geometry --json",
                "mode": "saved-payload",
                "payload": str(args.sheet_json),
            }
        elif args.from_svg:
            easycirq = _resolve_easycirq(args.easycirq)
            payload = _run_sheet_geometry(easycirq, ["--from-svg", args.from_svg])
            provenance = {
                "command": "easycirq sch sheet-geometry --from-svg <page.svg> --json",
                "mode": "official-svg-vectors",
                "svg": str(args.from_svg),
            }
        else:
            easycirq = _resolve_easycirq(args.easycirq)
            payload = _run_sheet_geometry(
                easycirq, ["--project", args.project, "--doc", args.doc]
            )
            provenance = {
                "command": "easycirq sch sheet-geometry --project <project> --doc <page> --json",
                "mode": "live-project",
                "project": args.project,
                "doc": args.doc,
            }
        geometry = geometry_from_payload(payload)
        document = _build_document(
            geometry,
            margin_override=args.margin,
            provenance=provenance,
            extra_notes=args.note,
        )
    except (MeasurementError, page_template.TemplateError) as exc:
        print("measure_page_template: %s" % exc, file=sys.stderr)
        return 2

    text = json.dumps(document, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        corner = document["title_block"]["corner"]
        print(
            "wrote %s (page %sx%s margin %s, title block %s %s, regions %s)"
            % (
                out_path,
                document["page"]["width"],
                document["page"]["height"],
                document["page"]["margin"],
                corner,
                document["title_block"]["rect"],
                ", ".join(region["name"] for region in document["regions"]),
            )
        )
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
