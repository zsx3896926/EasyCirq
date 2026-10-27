# PCB 模块批量执行提速 — 2026-10-27

## 实际修改

在现有 pcb_apply_plan.py 增加可重复 --module-plan，不另造执行器。多个独立放置模块先按同一基础快照合并，再运行原有整体几何/约束检查及 apply/journal/save/reload/dump/diff。保持 --plan 行为，保留完整计划本已具备的一次批量能力。

报告含输入原始字节哈希、模块成员、基础哈希及 assembled_plan。冲突归属、旧快照、不支持字段、扩大作用域和显式全板要求都拒绝；只接受 partial:true 的局部放置模块。公共 hard constraints 继续通过 --constraints 输入，不把模块 keepout 静默丢掉。

## 对照与验证范围

benchmark-result.json 为本机实际运行三轮的离线编译统计。双按键 LED 冻结 12 器件，统一平移 1mil 生成编译负载：逐器件与合批的有序修改指令一致；dump 文件读取/标准化 12→1；生成的 save/reload/dump 各 12→1。耗时仅为 Python 准备、文件读写及报告生成，不是 EDA 或整板速度。逐器件对照是每份以同一源独立编译，真实连续执行仍须每批更新快照。

不修改真实板。冻结源含已有铜，移动器件但不重布不能视为电气改板完成。本次没有完成从空工程绘制 LED 板的真实 A/B，不宣称整体提速百分比。

## 独立复核

只读子 Agent 审查新入口，复现 partial:false 被覆盖及模块 keepout 未参与放置检查。已修为显式 partial:true，拒绝模块 board/keepout/constraints 等未支持字段，追加负例。进一步拒绝未知 scope 字段，避免隐藏要求被解析器忽略。

## 真机阻断

本机 easyeda 1.15.0 health 无法访问 127.0.0.1:60832–60841，系统返回 socket access forbidden。不能据此断言 daemon 未运行；未启动或重启服务，未抢占共享窗口。真实批量写入、原生检查、保存重开、总耗时 A/B 均 BLOCKED。

## 下一次真机接续

在有连接权限且窗口归属明确的执行环境，先从同一初态建立两个隔离工程。对照原逐对象工作流与 --module-plan 工作流，使用相同最终位置、布线任务和完整验收，记录总耗时、等待、读取/写入、失败及返工。每批后按当前现场重算，不能顺序执行本离线基准的旧计划。

入口和格式见 design-hardware/references/execution-efficiency.md。未替换已安装 Skill，未合并、未发布。

## 本轮实际检查

- 新入口定向：最终18 tests OK（含新增 scope 负例）。
- 原执行器回归：49 tests OK。
- 全仓：1272 tests OK / skipped=1；此运行包含当时15个新测试，随后增加 scope 与 nested base 负例并通过最终18项定向，不将其冒记为更新后的全仓测试数。
- skill_selftest.py：5 PASS / 0 FAIL。
- git diff --check：通过。
- benchmark_module_batch.py --runs 3 与 pcb_apply_plan.py --help 均从真实入口运行。
- FakeRunner 的一次 apply、journal/save/reload/dump/diff 成功及失败路径是模拟验证，未证明真机通过。

第二次独立复核发现 nested base 别名冲突仍可被优先字段掩盖，已逐字段核验并拒绝未知字段，补充2个负例。
