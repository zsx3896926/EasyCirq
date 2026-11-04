"""Refresh HANDOFF section 3 with the reproducible dump2 baseline and the btn sweep."""
from pathlib import Path

p = Path(r"hds-verifier/tools/layout/HANDOFF.md")
s = p.read_text(encoding="utf-8")
i = s.find("## 3.")
j = s.find("## 4.")
assert i > 0 and j > i, "section markers not found"

new = """## 3. 当前实测前沿（RetroCam-02，4 层，GND 按铺铜建模）

**基线可复现性（已纠正）**：旧文档的"未布通 5 / 未连通 8"来自磁盘上的
`ec-placed.json`，**该文件用任何已知参数都复现不出来**（历史纯 HPWL 代码 + dump2 得
42202，而文件对应 43301）。那份基线**作废**。以下为 `dump2 + 当前代码` 的可复现基线，
同参数重跑得同一组数字。

| 配置（权重 bus/face/btn） | HPWL | 走线间距 | 拥塞 | 未布通 | 未连通 | vias |
|---|---|---|---|---|---|---|
| **baseline 0/0/0（可复现基线）** | 42202 | **0** | **0** | **9** | 11 | 66 |
| btn400 (0/0/400) | 46626 | 2 | 0 | 10 | 11 | 54 |
| **btn (0/0/800)** | 50103 | 0 | 1 | **6** | 11 | 69 |
| btn1200 (0/0/1200) | 48747 | 2 | 2 | 8 | 12 | 65 |
| btn2000 (0/0/2000) | 46447 | 0 | 0 | 9 | 7 | 58 |
| both (0/1500/800) | 50103 | 0 | 1 | 6 | 11 | 69 |

**结论一：btn 权重不单调。** 未布通随权重 0→400→800→1200→2000 为
**9 → 10 → 6 → 8 → 9**，噪声型曲线，不是趋势。btn=800 的 6 条腿可能是局部幸运点，
不能当作"找到规律"。它同时把 HPWL 抬高 19%（42202 → 50103）并引入 1 个拥塞单元，
**不值得作为默认配置**。

**结论二：`face_w` 项目前无效。** `both (0/1500/800)` 与 `btn (0/0/800)` 的 HPWL、
未布通、死腿清单完全一致（50103 / 6 / 同样 6 条腿）。说明 `escape_face_penalty`
在 cost 里要么是常数、要么梯度为零 —— 需要单独验证后才有意义。

其它已测指标：

```
45° 占比 ≈ 0.40；总线等长误差 CAM 741–1011 / LCD 130–305 / SD 73–308 mil（未达标）
测试 11/11 通过
```

死腿（baseline 9 条）集中在 GND（5 条）、CAM_D4 / CAM_PWDN、CC1 ——
GND 在真实板上是铺铜，因此 GND 相关死腿应视为"建模缺口"，而不是布线失败。

"""
p.write_text(s[:i] + new + s[j:], encoding="utf-8")
print("section 3 replaced")
