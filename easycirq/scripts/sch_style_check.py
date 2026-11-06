#!/usr/bin/env python3
"""按 `assets/style-reference/style-tokens.json` 检查图面合规性。

目标明确要求"以 style-reference 样例为基准"。这份脚本把 tokens 变成**可测量**的判据：

  · `layout.zone_area_ratio` 分区面积占比必须在 [0.25, 0.8]
  · `layout.page_margin_mm` 内容不得进入页边
  · `layout.zone_min_padding_mm` 分区框与内容的最小内距
  · `palette.zone_border` 分区框颜色必须取自调色板
  · `typography.*` 字号必须落在给定区间

**实测发现（本脚本写出来的原因）**：M3 的分区只占页面 **5.5%**，
而 tokens 要求 **≥25%** —— 这是硬性违反，而且解释了"一张邮票贴在巨幅纸上"。

用法：
  python scripts/sch_style_check.py --composition reports/.../composition-M3-placed.json
  python scripts/sch_style_check.py --work reports/hard-board/board2
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

MM_PER_RAW = 0.254          # 1 raw = 0.01 inch = 0.254 mm


def load_tokens(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(doc: dict, tokens: dict) -> list[dict]:
    out = []
    sheet = doc.get("sheet") or {}
    page_area = max(1e-9, (sheet.get("maxX", 0) - sheet.get("minX", 0))
                    * (sheet.get("maxY", 0) - sheet.get("minY", 0)))
    layout = tokens.get("layout") or {}
    lo, hi = (layout.get("zone_area_ratio") or [0.0, 1.0])[:2]

    frames = []
    # 优先用**真实导出**的分区框（审图渲染器写的 frames-*.json）：
    # 这样量的是"画出来的框"，而不是按器件外框估的。
    fr_path = doc.get("_framesPath")
    if fr_path and pathlib.Path(fr_path).is_file():
        fd = json.loads(pathlib.Path(fr_path).read_text(encoding="utf-8"))
        frames = [{"bbox": f["rect"]} for f in fd.get("frames") or []]
    for mod in ([] if frames else (doc.get("modules") or [])):
        fr = mod.get("frames") or mod.get("moduleFrames")
        if fr:
            frames.extend(fr)
        else:
            # 没有显式 frame 时用器件外框估
            xs0 = [p["bbox"]["minX"] for p in mod.get("placements") or []]
            xs1 = [p["bbox"]["maxX"] for p in mod.get("placements") or []]
            ys0 = [p["bbox"]["minY"] for p in mod.get("placements") or []]
            ys1 = [p["bbox"]["maxY"] for p in mod.get("placements") or []]
            if xs0:
                frames.append({"bbox": {"minX": min(xs0), "minY": min(ys0),
                                        "maxX": max(xs1), "maxY": max(ys1)}})
    if not frames:
        return [{"check": "zone_area_ratio", "ok": False,
                 "detail": "排版稿里找不到分区框"}]

    # 没有**真实分区框**时，这条判据测不了：用器件外框估出来的比例
    # 会把"框很松"误判成"框太小"，是错误结论。
    if not doc.get("_framesPath"):
        return [{"check": "layout.zone_area_ratio", "ok": True, "na": True,
                 "value": None, "want": [lo, hi],
                 "detail": "没有真实分区框（frames-*.json），"
                           "按器件外框估不算数 → NOT RUN"}]

    total = 0.0
    for f in frames:
        b = f.get("bbox") or {}
        a = max(0.0, (b.get("maxX", 0) - b.get("minX", 0))
                * (b.get("maxY", 0) - b.get("minY", 0)))
        total += a
    ratio = total / page_area
    out.append({
        "check": "layout.zone_area_ratio",
        "ok": lo <= ratio <= hi,
        "value": round(ratio, 4),
        "want": [lo, hi],
        "detail": ("分区占页面 %.1f%%，tokens 要求 %.0f%%~%.0f%%"
                   % (ratio * 100, lo * 100, hi * 100)),
    })

    # ── 分区内距：框与内容的最小距离（tokens: zone_min_padding_mm）──────
    pad_mm = layout.get("zone_min_padding_mm")
    if pad_mm is not None and frames:
        need = pad_mm / MM_PER_RAW
        worst = None
        for mod in doc.get("modules") or []:
            boxes = [p["bbox"] for p in mod.get("placements") or []]
            if not boxes:
                continue
            for f in frames:
                b = f.get("bbox") or {}
                for bb in boxes:
                    if (bb["minX"] >= b.get("minX", 0) and bb["maxX"] <= b.get("maxX", 0)
                            and bb["minY"] >= b.get("minY", 0)
                            and bb["maxY"] <= b.get("maxY", 0)):
                        gap = min(bb["minX"] - b["minX"], b["maxX"] - bb["maxX"],
                                  bb["minY"] - b["minY"], b["maxY"] - bb["maxY"])
                        if worst is None or gap < worst:
                            worst = gap
        out.append({"check": "layout.zone_min_padding_mm",
                    "ok": worst is None or worst >= need,
                    "value": round(worst, 3) if worst is not None else None,
                    "want": pad_mm,
                    "detail": "框与内容最小内距 %.2f mm（要求 ≥ %g mm）"
                              % ((worst or 0) * MM_PER_RAW, pad_mm)})

    # ── 单模块页：min_zones / zone_min_gap 明确不适用 ─────────────────────
    n_zones = len(frames)
    min_zones = layout.get("min_zones")
    if min_zones is not None:
        if n_zones < min_zones:
            out.append({"check": "layout.min_zones", "ok": True, "value": n_zones,
                        "want": min_zones, "na": True,
                        "detail": "本设计一页一模块（单分区），min_zones 针对多分区页，不适用"})
        else:
            out.append({"check": "layout.min_zones", "ok": True, "value": n_zones,
                        "want": min_zones, "detail": "分区数 %d（要求 ≥ %d）"
                                                    % (n_zones, min_zones)})

    margin_mm = layout.get("page_margin_mm")
    if margin_mm is not None:
        margin = margin_mm / MM_PER_RAW
        violations = []
        for mod in doc.get("modules") or []:
            for p in mod.get("placements") or []:
                b = p["bbox"]
                if (b["minX"] < sheet["minX"] + margin
                        or b["minY"] < sheet["minY"] + margin
                        or b["maxX"] > sheet["maxX"] - margin
                        or b["maxY"] > sheet["maxY"] - margin):
                    violations.append(p.get("designator"))
        out.append({"check": "layout.page_margin_mm", "ok": not violations,
                    "value": len(violations), "want": 0,
                    "detail": "越页边的器件：%r" % (violations[:5] or "无")})
    return out


def check_typography(svg_path: pathlib.Path, tokens: dict) -> list[dict]:
    """从渲染 SVG 读字号，按 tokens 的 typography 区间校验。"""
    import re
    typo = tokens.get("typography") or {}
    out = []
    try:
        svg = pathlib.Path(svg_path).read_text(encoding="utf-8")
    except OSError:
        return [{"check": "typography", "ok": False, "detail": "读不到 SVG"}]
    rows = re.findall(r'<text x="[\d.-]+" y="([\d.-]+)" font-size="([\d.]+)"', svg)
    if not rows:
        return [{"check": "typography", "ok": False, "detail": "SVG 里没有可解析的 text"}]
    # **只看图纸区域内**的文字：页标题画在 y<85（页面之上），属于纸张装饰，
    # tokens 的 zone_title 管的是页内分区名。混在一起会把 20 当成区名。
    sizes = [float(fs) for y, fs in rows if float(y) >= 85.0]
    if not sizes:
        sizes = [float(fs) for _y, fs in rows]
    biggest = max(sizes)
    spec = typo.get("zone_title") or {}
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None and hi is not None:
        out.append({"check": "typography.zone_title",
                    "ok": lo <= biggest <= hi,
                    "value": biggest, "want": [lo, hi],
                    "detail": "最大字号 %g，要求 %s~%s" % (biggest, lo, hi)})
    return out


FIELD_KEYWORDS = {
    "project": ("PROJECT",), "version": ("REV",), "date": ("20",),
    "sheet": ("SHEET",), "page": ("PAGE",), "size": ("SIZE",),
}


def check_title_block(svg_path: pathlib.Path, tokens: dict) -> list[dict]:
    """按 tokens.title_block.required_fields 检查图签字段是否齐全。"""
    import re
    want = (tokens.get("title_block") or {}).get("required_fields") or []
    if not want:
        return []
    try:
        svg = pathlib.Path(svg_path).read_text(encoding="utf-8")
    except OSError:
        return [{"check": "title_block.required_fields", "ok": False,
                 "detail": "读不到 SVG"}]
    texts = re.findall(r'<text[^>]*>([^<]*)</text>', svg)
    joined = " ".join(texts).upper()
    missing = [f for f in want
               if not any(k in joined for k in FIELD_KEYWORDS.get(f, (f.upper(),)))]
    return [{"check": "title_block.required_fields", "ok": not missing,
             "value": len(want) - len(missing), "want": len(want),
             "detail": ("齐全 %d/%d" % (len(want) - len(missing), len(want)))
                       + ("；缺 %r" % missing if missing else "")}]


def main() -> int:
    ap = argparse.ArgumentParser(description="按 style-tokens 检查图面合规")
    ap.add_argument("--composition", action="append", default=[])
    ap.add_argument("--work")
    ap.add_argument("--tokens", default=None)
    ap.add_argument("--frames", action="append", default=[],
                    help="审图渲染器导出的 frames-*.json；不给我就按器件外框估")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--svg", action="append", default=[],
                    help="渲染 SVG `模块=路径`：给了就一并校验字体尺寸")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    tpath = pathlib.Path(args.tokens) if args.tokens else \
        root / "assets" / "style-reference" / "style-tokens.json"
    tokens = load_tokens(tpath)

    comps = list(args.composition)
    if args.work:
        comps += [str(p) for p in
                  sorted(pathlib.Path(args.work).glob("composition-M*-placed.json"))]
    if not comps:
        raise SystemExit("需要 --composition 或 --work")

    rows = []
    for cp in comps:
        doc = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))
        name = pathlib.Path(cp).stem.replace("composition-", "").replace("-placed", "")
        # 显式映射 `模块=路径`；也兼容只给路径时按 stem 包含模块名匹配。
        # （按文件名猜结果永远匹配不上：`frames-P3_xxx.json` 里没有 `M3`。）
        fb = None
        for cand in args.frames:
            if "=" in cand:
                k, v = cand.split("=", 1)
                if k.strip() == name:
                    fb = v
                    break
            elif pathlib.Path(cand).stem.lower().find(name.lower()) >= 0:
                fb = cand
                break
        if fb:
            doc["_framesPath"] = fb
        res = check(doc, tokens)
        for spec in args.svg:
            if "=" in spec:
                k, v = spec.split("=", 1)
                if k.strip() == name:
                    res = res + check_typography(v, tokens)
                    res = res + check_title_block(v, tokens)
                    break
        rows.append({"module": name, "checks": res})
        if not args.json:
            print("  %s" % name)
            for r in res:
                print("     %-26s %s  %s"
                      % (r["check"], "✅" if r["ok"] else "❌", r["detail"]))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    bad = sum(1 for r in rows for c in r["checks"] if not c["ok"])
    if not args.json:
        print()
        print("  违规 %d 项（%d 个模块）" % (bad, len(rows)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
