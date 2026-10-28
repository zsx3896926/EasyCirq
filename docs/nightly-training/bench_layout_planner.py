#!/usr/bin/env python3
"""Offline benchmark for sch_layout_plan.py across block combinations.

Run from the repo root:
    python docs/nightly-training/bench_layout_planner.py

It enumerates combinations of the measured envelopes in ENVELOPES and reports
plan verdicts / fit rate / area usage. No EDA access.
"""
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_plan as planner  # noqa: E402

# measured on EasyEDA Pro 4.1.78 (easyeda.com), raw units 0.01 inch
ENVELOPES = {
    "es8311": ("音频编解码 ES8311", 560, 340),
    "aw8737": ("D 类功放 AW8737", 560, 340),
    "mems": ("模拟 MEMS 麦克风", 460, 220),
    "ams1117": ("3V3 线性稳压", 340, 220),
    "wroom": ("主控 ESP32-S3-WROOM", 460, 100),
    "bmi270": ("六轴 IMU BMI270", 460, 220),
    "ina226": ("电流监测 INA226", 540, 260),
    "microsd": ("microSD 存储", 460, 220),
    "bq24074": ("锂电充电与电源路径", 590, 550),
    "sy7088": ("同步升压 5V", 460, 340),
    "pmos": ("高侧负载开关", 340, 220),
}

BASE = {
    "schema": "easycirq-sch-layout-plan/v1",
    "page": {"width": 1170, "height": 825, "margin": 12},
    "titleBlock": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
    "options": {"gap": 24, "zonePad": 16, "titleGap": 36},
}


def run(combo):
    spec = dict(BASE)
    spec["blocks"] = [{"id": k, "title": ENVELOPES[k][0],
                       "envelope": {"w": ENVELOPES[k][1], "h": ENVELOPES[k][2]}} for k in combo]
    rep = planner.plan(spec)
    m = rep["metrics"]
    return rep["verdict"], m.get("fits", 0), m.get("overlaps", 0), m.get("area_usage", 0)


def main():
    keys = list(ENVELOPES)
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    fits = {1: 0, 2: 0, 3: 0, 4: 0}
    blocked = {}
    for n in (1, 2, 3, 4):
        for combo in itertools.combinations(keys, n):
            verdict, f, ov, usage = run(combo)
            counts[n] += 1
            if verdict == "pass":
                fits[n] += 1
            if verdict == "blocked":
                blocked.setdefault(n, []).append(combo)
        print("n=%d: %d combos, %d pass" % (n, counts[n], fits[n]))
    for n in blocked:
        print("blocked n=%d examples: %s" % (n, blocked[n][:3]))


if __name__ == "__main__":
    main()
