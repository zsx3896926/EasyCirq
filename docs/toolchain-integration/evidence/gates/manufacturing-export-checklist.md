# 制造资料导出清单（G6 待办）

> 本版本 `easycirq capabilities` 中 `gerber.export`/`drill.export`/`cpl.export` 均为
> `gui_only`（typed action 目录不存在），因此只能在 EasyEDA Pro GUI 导出，人工落证据。
> 导出后放入 `docs/toolchain-integration/evidence/gates/manufacturing/` 并在
> `design-state.manufacturing.artifacts` 登记 role/path。

## 1. Gerber
1. EasyEDA Pro 打开 `easycirq-integrated-dual-button-led-20261027` → PCB1；
2. 「制造 → 导出 Gerber」：层选 TOP/BOTTOM/丝印/阻焊/板框（两层板标准集合）；
3. 命名 `easycirq-dual-button-led-{rev}-gerber.zip`，落到上面目录；
4. 校验：zip 可打开、层文件数与层数一致、板框层存在、文件非空。

## 2. 钻孔
1. 同一导出面 → 导出钻孔文件（Excellon）；
2. 命名 `...-drill.zip`/`.drl`；
3. 校验：孔径列表与 PCB 设计一致（本板 **0 过孔/0 钻孔**，导出的空孔表需如实说明）。

## 3. CPL / 贴装坐标
1. 「制造 → 导出坐标」(Pick and Place)；
2. 命名 `...-cpl.csv`；列需含 Designator、Mid X/Y、Rotation、Layer；
3. 校验：行数与 BOM 装配件数一致（本板 9 件，全 TOP）。

## 4. 归档与恢复（已完成）
- `.epro2` + sha256 已落证据；恢复演练见 `evidence/m4/restore/restore-summary.json`。

## 5. 登记
导出后更新 `design-state.json`：
```json
"artifacts": [
  {"role": "gerber", "path": "evidence/gates/manufacturing/....zip"},
  {"role": "drill",  "path": "evidence/gates/manufacturing/....drl"},
  {"role": "cpl",    "path": "evidence/gates/manufacturing/....csv"}
]
```
然后重跑 gate_check（G6 的 gerber_files/drill_files/cpl_files 才会 pass）。
