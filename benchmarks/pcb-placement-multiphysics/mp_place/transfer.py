"""P2.14: cross-domain surrogate transfer — synthetic templates -> real boards.

Question: a surrogate trained on the 8 synthetic product-family templates is
cheap to build (the template generator is the only data source we fully control),
but does it predict the offline physics-v2 truth on *real* PCB read-back boards?

Protocol
--------
1. Sample random hard-feasible placements on the synthetic templates
   (``templates.instantiate`` + ``solver.random_feasible_placement``), compute
   the 10-dim baseline features and the 40-dim feature set, and the physics-v2
   truth.
2. Train a ridge surrogate on the template data (10-dim and 40-dim variants).
3. Sample random hard-feasible placements on each real board (``realboard``
   conversion of the three EasyCirq read-back dumps) and score them with the
   same physics-v2 model; report transfer R2 / Spearman against the in-domain
   ridge trained on part of that board's own samples.
4. Report a per-board table and a ranking-quality view (best-10 selection
   regret) to show whether transfer ranking is usable for candidate selection.

All offline, deterministic, standard library only.  The physics is the analytic
pseudo-physics surrogate, NOT SPICE/FEA; the result says something about
surrogate transfer, not about real board quality.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import time
from typing import Dict, List, Optional, Sequence, Tuple

from .features import FEATURE_NAMES, extract_features, feature_vector
from .features_v2 import FEATURE_NAMES_V2, extract_features_v2, feature_vector_v2
from .objective import PhysicsSimulator, RidgeModel, correlation, r_squared, spearman
from .physics_v2 import PhysicsSimulatorV2
from .realboard import DEFAULT_SOURCES, load_and_convert
from .solver import random_feasible_placement
from .templates import instantiate

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_NAMES: Tuple[str, ...] = ("mcu-min", "buck", "rs485", "motor", "wireless")
SAMPLES_PER_TEMPLATE = 120
SAMPLES_PER_BOARD = 120
BOARD_TRAIN_FRACTION = 2.0 / 3.0
CALIBRATION_FRACTION = 0.2


def _sample_templates(n: int = SAMPLES_PER_TEMPLATE, seed: int = 0) -> Tuple[List[List[float]], List[List[float]], List[float]]:
    X10: List[List[float]] = []
    X40: List[List[float]] = []
    y: List[float] = []
    for index, name in enumerate(TEMPLATE_NAMES):
        sc = instantiate(name, seed=seed)
        sim = PhysicsSimulatorV2(sc, seed=seed)
        rng = random.Random(seed * 1000 + index)
        for _ in range(n):
            pl = random_feasible_placement(sc, rng)
            f10 = extract_features(sc, pl)
            f40 = extract_features_v2(sc, pl)
            X10.append(feature_vector(f10))
            X40.append(feature_vector_v2(f40))
            y.append(sim.score_features(f40))
    return X10, X40, y


def _sample_board(converted, n: int = SAMPLES_PER_BOARD, seed: int = 0) -> Tuple[list, list, list]:
    sc = converted.scenario
    sim = PhysicsSimulatorV2(sc, seed=seed)
    rng = random.Random(seed + 77)
    X10, X40, y = [], [], []
    for _ in range(n):
        pl = random_feasible_placement(sc, rng)
        f10 = extract_features(sc, pl)
        f40 = extract_features_v2(sc, pl)
        X10.append(feature_vector(f10))
        X40.append(feature_vector_v2(f40))
        y.append(sim.score_features(f40))
    return X10, X40, y


def _fit_affine(pred: Sequence[float], true: Sequence[float]) -> Tuple[float, float]:
    """Least-squares y ≈ a·pred + b used for few-shot transfer calibration."""
    n = len(pred)
    if n == 0:
        return 1.0, 0.0
    mp = sum(pred) / n
    mt = sum(true) / n
    var = sum((p - mp) ** 2 for p in pred)
    if var <= 1e-12:
        return 1.0, mt - mp
    a = sum((p - mp) * (v - mt) for p, v in zip(pred, true)) / var
    return a, mt - a * mp


def _regret(y_true: Sequence[float], y_pred: Sequence[float], top: int = 10) -> Optional[float]:
    """Mean truth of the predicted top-k minus the mean truth of the true top-k."""
    n = len(y_true)
    if n <= top:
        return None
    true_top = sorted(range(n), key=lambda i: y_true[i])[:top]
    pred_top = sorted(range(n), key=lambda i: y_pred[i])[:top]
    mean_true = sum(y_true[i] for i in true_top) / top
    mean_pred = sum(y_true[i] for i in pred_top) / top
    return round(mean_pred - mean_true, 6)


def run(n_templates: int = SAMPLES_PER_TEMPLATE, n_boards: int = SAMPLES_PER_BOARD, seed: int = 0) -> Dict:
    started = time.time()
    X10_t, X40_t, y_t = _sample_templates(n_templates, seed=seed)
    model10 = RidgeModel(lam=1e-2).fit(X10_t, y_t)
    model40 = RidgeModel(lam=1e-2).fit(X40_t, y_t)
    rows = []
    for name, path in DEFAULT_SOURCES:
        converted = load_and_convert(path, name=name)
        X10_b, X40_b, y_b = _sample_board(converted, n_boards, seed=seed)
        n_calib = max(4, int(len(y_b) * CALIBRATION_FRACTION))
        n_test = max(4, int(len(y_b) * 0.4))
        calib_end = n_calib
        test_start = len(y_b) - n_test
        X40_tr, y_tr = X40_b[calib_end:test_start], y_b[calib_end:test_start]
        X10_tr = X10_b[calib_end:test_start]
        in10 = RidgeModel(lam=1e-2).fit(X10_tr, y_tr)
        in40 = RidgeModel(lam=1e-2).fit(X40_tr, y_tr)
        X40_te, y_te = X40_b[test_start:], y_b[test_start:]
        transfer40 = [model40.predict(x) for x in X40_te]
        transfer10 = [model10.predict(x) for x in X10_b[test_start:]]
        domain40 = [in40.predict(x) for x in X40_te]
        # few-shot affine calibration of the transferred predictions
        calib_pred = [model40.predict(x) for x in X40_b[:calib_end]]
        calib_true = y_b[:calib_end]
        a, b = _fit_affine(calib_pred, calib_true)
        calibrated40 = [a * p + b for p in transfer40]
        rows.append(
            {
                "board": name,
                "board_mm": [round(converted.scenario.board_w, 2), round(converted.scenario.board_h, 2)],
                "components": len(converted.scenario.components),
                "nets": len(converted.scenario.nets),
                "samples": len(y_b),
                "test_samples": len(y_te),
                "transfer": {
                    "r2_10": round(r_squared(y_te, transfer10), 4),
                    "r2_40": round(r_squared(y_te, transfer40), 4),
                    "spearman_10": round(spearman(y_te, transfer10), 4),
                    "spearman_40": round(spearman(y_te, transfer40), 4),
                    "regret10_40": _regret(y_te, transfer40),
                    "calibrated_r2_40": round(r_squared(y_te, calibrated40), 4),
                    "calibrated_spearman_40": round(spearman(y_te, calibrated40), 4),
                    "calibrated_regret10_40": _regret(y_te, calibrated40),
                    "calibration_samples": calib_end,
                },
                "in_domain": {
                    "r2_10": round(r_squared(y_te, [in10.predict(x) for x in X10_b[test_start:]]), 4),
                    "r2_40": round(r_squared(y_te, domain40), 4),
                    "spearman_10": round(spearman(y_te, [in10.predict(x) for x in X10_b[test_start:]]), 4),
                    "spearman_40": round(spearman(y_te, domain40), 4),
                    "regret10_40": _regret(y_te, domain40),
                },
                "truth_mean": round(sum(y_te) / len(y_te), 4),
                "truth_std": round(_std(y_te), 4),
            }
        )
        print(
            f"[transfer] {name}: transfer40 R2={rows[-1]['transfer']['r2_40']:.3f} "
            f"rho={rows[-1]['transfer']['spearman_40']:.3f} | "
            f"in-domain40 R2={rows[-1]['in_domain']['r2_40']:.3f} rho={rows[-1]['in_domain']['spearman_40']:.3f}"
        )
    agg_transfer = _mean_metric(rows, "transfer", "r2_40")
    agg_domain = _mean_metric(rows, "in_domain", "r2_40")
    return {
        "config": {
            "templates": list(TEMPLATE_NAMES),
            "samples_per_template": n_templates,
            "samples_per_board": n_boards,
            "board_train_fraction": BOARD_TRAIN_FRACTION,
            "feature_dims": {"baseline": len(FEATURE_NAMES), "rich": len(FEATURE_NAMES_V2)},
            "seed": seed,
        },
        "rows": rows,
        "aggregate": {
            "transfer_r2_mean": agg_transfer,
            "in_domain_r2_mean": agg_domain,
            "transfer_gap_r2": round(agg_domain - agg_transfer, 4),
            "transfer_spearman_mean": _mean_metric(rows, "transfer", "spearman_40"),
        },
        "runtime_s": round(time.time() - started, 2),
    }


def _mean_metric(rows: Sequence[Dict], block: str, key: str) -> float:
    vals = [r[block][key] for r in rows if r[block].get(key) is not None]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def _std(xs: Sequence[float]) -> float:
    import math

    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_transfer.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    agg = data["aggregate"]
    lines = ["# P2.14: 代理模型跨域迁移（合成模板 → 真实板）\n"]
    lines.append(f"- 运行：{data['runtime_s']} s；模板 {len(TEMPLATE_NAMES)} 个，每模板 {data['config']['samples_per_template']} 布局；")
    lines.append(f"- 真实板每板 {data['config']['samples_per_board']} 布局，板内 2/3 训练 1/3 测试；")
    lines.append(f"- 特征：10 维基线 vs 40 维 rich；真值 = PhysicsSimulatorV2。\n")
    lines.append("## 汇总\n")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 跨域迁移 R² 均值（40 维） | {agg['transfer_r2_mean']} |")
    lines.append(f"| 板内 in-domain R² 均值（40 维） | {agg['in_domain_r2_mean']} |")
    lines.append(f"| 跨域差距（in-domain − transfer） | {agg['transfer_gap_r2']} |")
    lines.append(f"| 跨域 Spearman 均值（40 维） | {agg['transfer_spearman_mean']} |")
    lines.append("\n## 逐板\n")
    lines.append("| 板 | 器件 | nets | 跨域 R²(10/40) | 跨域 ρ(10/40) | 跨域+校准 R²/ρ | 域内 R²(10/40) | 域内 ρ(10/40) | 真值 mean±sd |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in data["rows"]:
        t, i = row["transfer"], row["in_domain"]
        lines.append(
            f"| {row['board']} | {row['components']} | {row['nets']} | "
            f"{t['r2_10']} / {t['r2_40']} | {t['spearman_10']} / {t['spearman_40']} | "
            f"{t['calibrated_r2_40']} / {t['calibrated_spearman_40']} | "
            f"{i['r2_10']} / {i['r2_40']} | {i['spearman_10']} / {i['spearman_40']} | "
            f"{row['truth_mean']} ± {row['truth_std']} |"
        )
    lines.append("\n## 结论\n")
    cal_r2 = _mean_metric(data["rows"], "transfer", "calibrated_r2_40")
    cal_rho = _mean_metric(data["rows"], "transfer", "calibrated_spearman_40")
    lines.append(f"- 跨域秩相关均值：raw {agg['transfer_spearman_mean']}，校准后 {cal_rho}；校准后 R² 均值 {cal_r2}。")
    if agg["transfer_spearman_mean"] >= 0.8 and cal_r2 >= 0.8:
        lines.append("- 合成模板训练的 40 维代理对真实板**有较好迁移**（秩相关高、少量校准后 R² 高），可作为真实板候选筛选的默认代理 + 少量样本校准。")
    elif agg["transfer_spearman_mean"] >= 0.5:
        lines.append("- 迁移**部分可用**：秩相关中等，适合粗筛/排序；必须用少量真实板样本做仿射校准，不能直接当验收分。")
    elif agg["transfer_spearman_mean"] >= 0.6:
        lines.append("- 迁移**部分可用**：秩相关中等，适合粗筛/排序，但不宜单独作为验收分；真实板应补少量样本做校准。")
    else:
        lines.append("- 迁移**不可靠**：合成模板与真实板的分布差距过大，真实板需域内样本训练或特征再校准。")
    lines.append("- 边界：真值是离线伪物理模型，不是 SPICE/FEA；真实 DRC/布线/SI/PI/热仍 `NOT RUN`。")
    (out_dir / "report_transfer.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[transfer] wrote {out_dir / 'report_transfer.md'} / report_transfer.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-domain surrogate transfer experiment")
    parser.add_argument("--template-samples", type=int, default=SAMPLES_PER_TEMPLATE)
    parser.add_argument("--board-samples", type=int, default=SAMPLES_PER_BOARD)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    write_report(run(args.template_samples, args.board_samples, args.seed), pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
