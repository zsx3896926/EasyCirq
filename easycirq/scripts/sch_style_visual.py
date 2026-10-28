#!/usr/bin/env python3
"""Rough visual comparison: exported schematic vs the style reference image.

Stage 5 helper. NOT an aesthetic judge: it only catches gross mismatches
(page shape, missing palette colors, blank/overexposed output) and writes a
side-by-side PNG for a human to look at.

Input: a PNG export of the candidate page and the reference image
(default: assets/style-reference/esp32-schematic.png).
Output: easycirq-sch-style-visual/v1 report; `--side-by-side` writes the pair.

Exit codes: 0 PASS, 1 REVIEW, 2 BLOCKED/invalid.
Requires Pillow (PIL). Does not access EDA or the network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REFERENCE = SCRIPT_DIR.parent / "assets" / "style-reference" / "esp32-schematic.png"
DEFAULT_TOKENS = SCRIPT_DIR.parent / "assets" / "style-reference" / "style-tokens.json"
SCHEMA = "easycirq-sch-style-visual/v1"

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except Exception:  # pragma: no cover - environment without Pillow
    HAVE_PIL = False


def _rgb(path):
    img = Image.open(path).convert("RGB")
    return img


def _grid(img, n=48):
    return list(img.convert("L").resize((n, n)).getdata())


def _pearson(a, b):
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / (va ** 0.5 * vb ** 0.5)


def _hist(img, bins=8):
    small = img.resize((96, 96))
    counts = [0] * (bins * 3)
    for r, g, b in small.getdata():
        counts[(r * bins) // 256] += 1
        counts[bins + (g * bins) // 256] += 1
        counts[2 * bins + (b * bins) // 256] += 1
    total = sum(counts) or 1
    return [c / total for c in counts]


def _cosine(a, b):
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na <= 0 or nb <= 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _palette_hits(img, tokens):
    colors = []
    for c in tokens["palette"]["zone_border"]:
        c = c.lstrip("#")
        colors.append(tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)))
    small = img.resize((120, 120))
    data = list(small.getdata())
    hits = 0
    for cr, cg, cb in colors:
        if any(abs(r - cr) + abs(g - cg) + abs(b - cb) <= 90 for r, g, b in data):
            hits += 1
    return hits, len(colors)


def _side_by_side(candidate, reference, out, height=520):
    def fit(img):
        w, h = img.size
        nh = height
        nw = max(1, int(w * nh / h))
        return img.resize((nw, nh))
    a = fit(candidate)
    b = fit(reference)
    gap = 20
    canvas = Image.new("RGB", (a.width + gap + b.width, height + 28), "white")
    canvas.paste(a, (0, 28))
    canvas.paste(b, (a.width + gap, 28))
    draw = ImageDraw.Draw(canvas)
    draw.text((6, 6), "candidate", fill="black")
    draw.text((a.width + gap + 6, 6), "reference", fill="black")
    canvas.save(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rough schematic-vs-reference visual comparison")
    ap.add_argument("--candidate", required=True, help="exported schematic PNG")
    ap.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    ap.add_argument("--tokens", default=str(DEFAULT_TOKENS))
    ap.add_argument("--side-by-side", help="write candidate|reference PNG here")
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    problems, metrics = [], {}
    try:
        if not HAVE_PIL:
            raise ValueError("Pillow (PIL) is required for visual comparison")
        cand = _rgb(args.candidate)
        ref = _rgb(args.reference)
        tokens = json.loads(Path(args.tokens).read_text(encoding="utf-8"))

        metrics["candidate_size"] = list(cand.size)
        metrics["reference_size"] = list(ref.size)
        ca = cand.width / cand.height
        ra = ref.width / ref.height
        metrics["aspect_ratio"] = round(ca, 3)
        metrics["reference_aspect_ratio"] = round(ra, 3)
        metrics["aspect_closeness"] = round(min(ca, ra) / max(ca, ra), 3)

        corr = _pearson(_grid(cand), _grid(ref))
        hist = _cosine(_hist(cand), _hist(ref))
        hits, total = _palette_hits(cand, tokens)
        gray = _grid(cand)
        mean = sum(gray) / len(gray)
        white = sum(1 for v in gray if v > 240) / len(gray)

        metrics.update({"gray_correlation": round(corr, 3),
                        "histogram_cosine": round(hist, 3),
                        "palette_colors_present": hits,
                        "palette_colors_total": total,
                        "mean_brightness": round(mean, 1),
                        "white_ratio": round(white, 3)})
        metrics["similarity"] = round(
            0.4 * max(0.0, corr) + 0.3 * max(0.0, hist) + 0.3 * (hits / total), 3)

        if metrics["aspect_closeness"] < 0.85:
            problems.append({"severity": "review", "message": "page aspect ratio differs a lot from the reference"})
        if hits == 0:
            problems.append({"severity": "review", "message": "no palette zone-border color found in the export"})
        if mean < 40:
            problems.append({"severity": "review", "message": "export is almost black (mean brightness %s)" % round(mean, 1)})
        if white > 0.98:
            problems.append({"severity": "review", "message": "export looks almost blank (white ratio %s)" % round(white, 3)})
        if white < 0.15:
            problems.append({"severity": "review", "message": "little white background (may be a screenshot, not a page export)"})

        if args.side_by_side:
            _side_by_side(cand, ref, args.side_by_side)
            metrics["side_by_side"] = str(args.side_by_side)
    except Exception as exc:  # noqa: BLE001 - report, do not crash the stage
        problems.append({"severity": "blocked", "message": str(exc)})

    blocked = any(p["severity"] == "blocked" for p in problems)
    review = any(p["severity"] == "review" for p in problems)
    verdict = "blocked" if blocked else ("review" if review else "pass")
    report = {
        "schema": SCHEMA,
        "verdict": verdict,
        "metrics": metrics,
        "problems": problems,
        "note": "rough visual signal for a human; not an aesthetic or electrical acceptance",
    }
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    return {"pass": 0, "review": 1, "blocked": 2}[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
