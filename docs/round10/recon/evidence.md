# evidence

## summary

两案例的必需产物大多存在：dump before/after、DRC/check、key net-path、SCH-PCB 对账、顶/底 PNG、actual SVG、BOM、.epro2+SHA 都有。两板都缺 layout-lint 与 manifest.json；现有 design-state.json 只是 design-engine-state/v1 的恢复状态，不含版本/命令/失败项，且最终 .epro2 未注册进 evidence[]。板 B 的 DRC/check/netpath 早于最终 save→reload，不能支持 README 的“最终 reload 后 DRC 0”；板 B 与 edit 的 .epro2 分别比最终 dump 多 7/9 条 0.01–0.07 mil 退化 LINE。板 A 的图/BOM/netpath/SCH-PCB 早于最终 dump，但 pcb-diff 证明 identity/geometry/copper 未变，风险主要是 PNG 无源哈希。所有已注册 evidence 的 sha256/bytes 都匹配。仓库和历史中没有 pcb_case.py 或 pcb-command-map.json。本次仅只读检查。

## gaps

- layout-lint 证据两板都缺失；只有 scratch 的 photo-led-layout-lint.json（80/moderate）和 boardB-lint2.json（68/moderate），case 内没有 pcb-layout-lint*.json/log。
- 两 case 都没有 manifest.json；design-state.json 是 design-engine-state/v1 的恢复状态，不含 versions、commands、failures、artifact 时间戳/source_dump_sha256，且不符合 gate_check 的 design-state/v1 结构。
- 最终 .epro2 未注册进 design-state.evidence[]（只有 recovery 里的文件名+sha），没有 bytes、没有 project export 回执（zipIntegrityVerified/restoreVerified），也没有恢复演练。
- case 内没有任何命令 argv、cwd、exit code、stdout/stderr 哈希；命令只散落在 README 复现段、references 模板和 C:/Users/jlc/work/pcb-round9-scratch 的临时脚本/回执里。
- 板 B 的 DRC（13:39:01Z）、check（13:38:57Z）、netpath（13:39:54Z）早于 dump-final（13:40:12Z）、save→reload（13:40:44Z）和 epro2（21:41:53 local）；没有 post-reload DRC/check/netpath，README 的“最终 save→reload 后 DRC 0”没有对应证据。
- 板 B/edit 的 .epro2 与最终 dump 对象数不一致：B 多 7 条 LINE（240 vs 233），edit 多 9 条（261 vs 252）；都是 0.01–0.073 mil 的退化短线，dump/DRC/check/netpath 均未覆盖。
- edit-add-decap 链缺 after-reload dump（只在 scratch boardB-edit-final-b.json）、edit check 未注册、scope JSON 未保留；edit DRC 早于 edit reload。
- 板 A 的 PNG（12:49:05/12:49:48Z）、BOM（12:50:38Z）、netpath（12:48:37Z）、sch-compare（12:50:25Z）早于最终 dump（12:51:18Z）和 epro2（12:51:38Z）；pcb-diff 虽 match，但 PNG 没有任何源哈希/回执，严格说无法证明与最终归档一致。
- 板 B 的 PNG（21:40:55/21:40:58 local）早于 archive 内 PCB updateTime（13:41:01Z），且 PNG 无源哈希。
- PNG 是 pcb snapshot 视口图，不是对象级 actual 导出；README 也承认最终制造图仍需 GUI/官方导出。
- BOM 导出回执记录的 sha/size 是 enrich 之前的，与最终 BOM.csv 不一致；回执不在 case。A 0/15 行命中 enrich，B 1 行未命中（SHT40-CD1B-R3）。
- DRC 与 save-reload-diff 的 JSON 在不同板/不同 edit 间字节完全相同（DRC bcecab...；save-reload 6abb4c...），文件内没有 board/project 标识，哈希本身不能证明属于哪块板。
- placement-apply-report.json 顶层 status=mismatch 是修复前 pcb_apply_plan.py 的旧口径；当前脚本会判 verified，报告没有记录工具版本。
- 板 B README 的 pcb-fabrication 复现命令没有对应 fabrication-check 输出入 case；板 A README 引用的 photo-led-source-20261026.epro2、photo-led-placed-checkpoint.epro2、photo-led-pcb-drc0.epro2 也不在 case。
- gate_check.py 的角色命名/状态 schema 与现有文件名不兼容：netpath-key-connections.json、save-reload-diff.json 不会被发现；lint/project-export/pours/vias 角色缺失。
- design-state.json 的 updated=null，路径混用正/反斜杠，最终 epro2 只有文件名，不适合作为跨机器可复算清单。
- 两板制造包（Gerber/drill/CPL）均 BLOCKED；BOM 的库存/价格/SMT 未查，DRC 0 不等于可制造/可工作。

## recommendations

- 实现 pcb_case.py 时定义稳定 schema（建议 design-engine-pcb-case/v1），在 case 根写 manifest.json；每个产物记录 role/stage/path/sha256/bytes/produced_at/source_dump_sha256/run_after_final_reload。
- 命令记录复用 sch_layout_pipeline.py 的 _run 形状：argv 数组、cwd、开始/结束时间、exit code、stdout_sha256、stderr_sha256、stdout/stderr 落盘路径；不要只写人类可读命令串。
- 版本用实际命令/文件取证：easyeda version、easyeda health（Connector）、.epro2 project2.json editorVersion、design_engine.ENGINE_VERSION、skill .version、Python/OS、repo HEAD；不要只抄 README。
- 强制记录每次检查使用的源 dump 哈希：DRC/check/netpath/SCH-PCB 都要绑定 dump-final 或 dump-after-reload 的 sha256；如果检查早于最终 reload，manifest 标 pre_reload 且不能宣称 final。
- 把 DRC/check/netpath 安排在最终 save→reload→fresh dump 之后重跑，或至少补一次 post-reload 版本；README 的 final 声明以该次为准。
- 保留 dump 的 .capture.json sidecar（含 persisted sha256、per-request resultSha256、identityVerified），或把 capture 块完整写入 manifest；当前 case 缺 sidecar。
- 输出文件名对齐 gate_check.py 角色，或在 manifest 里写显式 role→path 映射：pcb-layout-lint.json、net-path-<net>.json（或 net-path.json）、doc-reload-readback.json、project-export.json、pcb-pour-list.json、pcb-vias.json。
- project export 后保留回执并做恢复演练：记录 zipIntegrityVerified、restoreVerified、epro2 sha256/bytes、archive updateTime；在副本上重开核对工程/页 UUID、器件、网表与关键网。
- 增加 archive-vs-dump 对象对账：COMPONENT/PAD_NET/LINE/VIA/POUR/FILL 计数；B/edit 的 7/9 条退化 LINE 应显式列为差异并判断是否为 dump 过滤还是真实铜。
- BOM 记录 raw export 回执 + enrich 后最终文件哈希 + enrich 命中/未命中清单；不要用回执里的 pre-enrich sha/size 代表最终 BOM。
- 图像改为可追溯：保存 pcb snapshot 的 artifact 回执（path/sha256）或改用 layout render --actual --side top/bottom 输出两个 SVG，并把 sourceSha256 写入 manifest；至少不要让 PNG 无源哈希。
- failures/waivers 显式建模：apply report 的旧版 mismatch、check 的 13/6 WARN 及处置、BOM 未命中、制造包 BLOCKED、lint 缺失、pre-reload DRC、archive/dump 行数差都要进 manifest，而不是只写在 README 文字里。
- 与 pcb_gate 对齐：manifest 或伴生文件补 schematic/layout/stackup/routing/manufacturing/sourcing 节，或提供 gate 读取映射；否则 gate_check 会把现有 design-state 大量判 BLOCKED。
- 路径统一为相对 case 根目录的 POSIX 路径，写 updated 时间戳；最终 archive 进入 evidence[] 并记录 bytes；不要把恢复状态和案例清单混在一个文件里。
- 为 pcb_case.py 加 fake easyeda 回放端到端测试 + A/B 真实 dump 回归；用 design_engine.state.verify_evidence 验证 manifest 里的所有哈希，并断言 DRC/check/netpath 的 source_dump_sha256 等于 final dump。
- 在实现前先冻结本轮 A/B 最终归档与 dump，记录 SHA/版本/时间；后续任何 pcb_case 重跑都先校验冻结哈希，避免用旧进程/旧截图/旧归档冒充最终状态。

## facts

### 逐板矩阵（PRESENT/MISSING/PARTIAL）：dump before=PRESENT/PRESENT；dump after reload=PRESENT/PRESENT；DRC=PRESENT(passed=true,total=0)/PRESENT(但早于最终 reload)；check=PRESENT(6 WARN,0 ERROR)/PRESENT(13 WARN+1 INFO,0 ERROR)；lint=MISSING(scratch 80/moderate)/MISSING(scratch 68/moderate)；key net-path=PRESENT(14/14)/PRESENT(15/15)；SCH-PCB=PRESENT(19 器件/47 脚 match)/PRESENT(23/104 match)；top/bottom image=PRESENT(PNG snapshot,早于最终 dump)/PRESENT(PNG snapshot,早于 archive updateTime)；actual SVG=PRESENT(sourceSha256 绑定最终 dump)/PRESENT(同左)；BOM=PRESENT(15 行/19 件)/PRESENT(15 行/23 件)；.epro2+SHA=PRESENT(d9ef...)/PRESENT(312f...，另有 edit f656...)；manifest.json=MISSING/MISSING。

evidence: A=`C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/`；B=`C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/`；A README.md:69-83；B README.md:66-83；A design-state.json:31-133；B design-state.json:34-148；lint 见 C:/Users/jlc/work/pcb-round9-scratch/photo-led-layout-lint.json 与 boardB-lint2.json；两 case 目录均无 manifest.json。

### 仓库与分支历史中不存在 pcb_case.py，也没有 references/pcb-command-map.json；两案例目录没有 manifest.json，可机读索引只有 design-state.json。

evidence: `find C:/Users/jlc/work/hds-pcb-round9/design-hardware -name pcb_case.py -o -name pcb-command-map.json` 无结果；`git log --all --name-only | grep pcb_case` 无结果；cases 目录清单只有 README.md、design-state.json、evidence/；design-hardware/references/ 无 command-map 文件。

### design-state.json 的 schema 是 design-engine-state/v1（恢复状态），不是案例 manifest，也不符合 gate_check.py 读取的 design-state/v1 结构。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/state.py:11-31（SCHEMA='design-engine-state/v1'）；A design-state.json:1-2；B design-state.json:1-2；design-gates.md §13.3 要求 design-state/v1；gate_check.py:1339-1969 读取 schematic/layout/stackup/routing/manufacturing/sourcing，两 case 均无这些键。

### design-state.json 只有 project/stage/best_candidate/open_items/next_action/budget/recovery/evidence[]/updated；缺少 versions、commands、failures、每个产物的时间戳、源 dump 哈希绑定；updated 为 null，路径混用反斜杠。

evidence: B design-state.json:1-151（updated 在 :150）；A design-state.json:1-136（updated 在 :135）；evidence 条目仅 role/path/sha256/bytes（state.py:50-59）；B design-state.json:37 形如 'design-hardware/cases/mcu-i2c-s3-2026-10-26\\evidence/...'。

### 两 case 的 design-state 注册项哈希全部匹配实际文件（A 17/17，B 19/19），但有未注册文件：B 3 个（boardB-final.epro2、edit-add-decap-dump.json、edit-add-decap-check.json），A 17 个（含最终 photo-led-pcb-final.epro2 与全部中间产物）。

evidence: 重算 sha256 与 bytes 对比 design-state evidence[]；A 未注册清单：candidates.json, constraints.json, escapes.json, fabrication-check.json, module-U1-C2-R4.json, module-binding.json, pcb-dump-placed.json, pcb-intent.json, pcb-placed-actual.svg, photo-led-pcb-final.epro2, placement-check.json, placement-plan.json, poured-list-plus5-empty.json, power-check.json, power-pour.log, sch-read.json, silk-align.log；B 未注册：boardB-final.epro2, edit-add-decap-dump.json, edit-add-decap-check.json。

### 两板原生 DRC 都是 passed=true、total=0、violations=[]；两份文件字节完全相同（sha256 bcecab466975deec1fec102618a846f3efc015aad81f67c0a99374eb016ad6ad），文件内没有 board/project 标识或源 dump 哈希。

evidence: A/B evidence/pcb-drc-final.json 内容与哈希；A design-state.json:54-56；B design-state.json:55-57；与 temp-alarm 的 evidence/project-export.json 不同，DRC JSON 无 capture/identity。

### check 证据两板都存在但 passed=false：A 为 6 条 WARN、0 ERROR；B 为 13 条 WARN + 1 条 INFO、0 ERROR；与 README 的 6/13 WARN 描述一致，但 pcb_case 若把 passed=false 直接当失败会误判。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/*/evidence/pcb-check-final.json 的 findings 计数；A README.md:72；B README.md:69。

### layout-lint 在两案例目录中缺失，只在 scratch 保留：A score 80/moderate、5 crossings；B score 68/moderate、8 crossings；README 分别引用这两个数字。

evidence: C:/Users/jlc/work/pcb-round9-scratch/photo-led-layout-lint.json（report.score=80, verdict=moderate, 5 crossings）；C:/Users/jlc/work/pcb-round9-scratch/boardB-lint2.json（report.score=68, verdict=moderate, 8 crossings）；A README.md:28；B README.md:31；evidence/ 无 *layout*lint* 文件。

### net-path 两板都通过（A 14/14、B 15/15 connected），但产物只有聚合 rows，没有 project/UUID/源 dump hash；生成方式是仓库外的 scratch 脚本逐对调用 easyeda pcb net-path。

evidence: netpath-key-connections.json 的 rows（字段 from/to/net/status/length_mil/vias/layers/path_kind，B 无 widths）；C:/Users/jlc/work/pcb-round9-scratch/netpath_check.py:4-36（photo-led-pcb-20261026/PCB1，命令在 :22-25）；C:/Users/jlc/work/pcb-round9-scratch/boardB_netpath_final.py:4-42（mcu-i2c-s3-20261026/PCB2，命令在 :23-26）；references/design-gates.md:194。

### SCH-PCB 对账两板都 match（A 19 器件/47 脚，B 23/104），但产物由仓库外的临时 Python 脚本生成，不是 repo CLI；输出没有输入哈希或工程标识，B 的 sch-connectivity.json 与 scratch boardB-connectivity-final.json 字节一致。

evidence: A/B evidence/sch-pcb-compare.json 内容；C:/Users/jlc/work/pcb-round9-scratch/sch_pcb_compare.py:1-32（boardA-sch-read.json + boardA-final-a.json）；C:/Users/jlc/work/pcb-round9-scratch/boardB_sch_pcb_compare.py:1-33（boardB-connectivity-final.json + boardB-final-a.json）；B sch-connectivity.json 47095 B sha 435459... 与 scratch boardB-connectivity-final.json 相同。

### 顶/底 PNG 与 actual SVG 都存在；PNG 实际是 pcb snapshot 视口图（哈希分别等于 .easyeda/artifacts 下的 pcb_snapshot 文件），不是对象级 actual 导出；SVG 是 layout render --actual --side both，metadata.sourceSha256 分别等于两板最终 dump 的 sha256。

evidence: C:/Users/jlc/work/hds-pcb-round9/.easyeda/artifacts/20261026-204905-pcb_snapshot-28c18b80.png sha 34e69a...=A bottom；20261026-204948-pcb_snapshot-f292263a.png sha d942aae...=A top；20261026-214055-pcb_snapshot-b7720104.png sha 7c880e...=B top；20261026-214058-pcb_snapshot-a0bb8de3.png sha e50e4b...=B bottom；SVG metadata sourceSha256 A=3a07ade...、B=42acfe...；A README.md:105；B README.md:38；assets/docs/silk-assembly.md:64；references/pcb-execution.md:245。

### BOM 两板都是 15 行（A 19 件、B 23 件），全部有 Supplier Part；BOM.csv 与 .easyeda/artifacts 的最终 CSV 字节一致，但 scratch 导出回执记录的 sha/size 是 enrich 之前的（A 74131f/2656 vs 最终 c88181/1471；B 1aa6aa/2546 vs 最终 f2628a/1401），回执不在 case 中。

evidence: A/B evidence/BOM.csv 行数与 Quantity 合计；bom-audit.json（status pass, rows 15, parts 19/23）；scratch bom-export.json 与 boardB-bom-export.json 的 artifacts[0].sha256/size；.easyeda/artifacts 最终文件哈希；A README.md:78；B README.md:74。

### .epro2 两板都存在且 SHA-256 与 README/recovery 一致：A d9ef9201e574c7ba944c7c77c77aa3364802464790e4e7daca1969884a826491（230203 B），B 312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1（132270 B），edit f65654cb7144c184137002c2efe5a8af7ed8ff7f5c79997d554f71251776e025（135173 B）；但最终归档都未注册进 design-state.evidence[]，也没有 project export 回执（zipIntegrityVerified/restoreVerified）。

evidence: 实测 sha256/bytes；A README.md:16；B README.md:13 与 :95；A design-state.json:24-26；B design-state.json:25-26；case 内无 project-export*.json；gate_check.py:125 期望 project-export*.json；temp-alarm case 的 evidence/project-export.json 是现成格式先例。

### 归档内容与最终 dump 的对象集合：A 完全一致（19 组件/47 pad/67 line/0 via/2 pour/2 poured/4 fill）；B 的归档多 7 条 LINE（240 vs 233）；edit 多 9 条（261 vs 252）。多出的都是 0.01–0.073 mil 退化短线，位于 U1.4、J1、D1 等 pad 附近。

evidence: 解压 .epru 统计 PCB 段 type=COMPONENT/PAD_NET/LINE/VIA/POUR/POURED/FILL/REGION；B 额外 id 6adb35783251bfc8、78c8553ba8c22c12、cd9788f8d45ddf1b、286fa5e58bdb792d、45fa0b076a9c5a50、9a47692f21c0469c、b7a040a48a0f1e9b；edit 另多 524a42c9f728cbe1、ee38aa59dc028b90；A 无差异。

### 命令来源：dump/DRC/check/lint 有文档模板；net-path 与 SCH-PCB 只有 scratch 脚本；BOM 只有 scratch 回执；case 本身不能复现任何一条命令的 argv。

evidence: dump：references/pcb-execution.md:23；after-reload：design-gates.md:196 与 scratch board-a-next-steps.md:58；DRC/check/lint：board-a-next-steps.md:43-45；net-path：netpath_check.py:22-25、boardB_netpath_final.py:23-26；SCH-PCB：两个 scratch compare 脚本；PNG：assets/docs/silk-assembly.md:64；SVG：references/pcb-execution.md:245；epro2：design-gates.md:221；离线命令：A README.md:88-95、B README.md:82-84。

### 推荐记录的命令 argv（带 documented/inferred 标记）：dump `easyeda pcb dump --project <P> --doc <PCB> --include-copper --out <file>`；after-reload `easyeda pcb save` + `easyeda doc reload <PCB> --project <P>` + 同 dump；DRC `easyeda pcb drc --json --timeout 120`；check `easyeda pcb check --json`；lint `easyeda pcb layout-lint --json`；net-path 逐对 `easyeda pcb net-path --project <P> --doc <PCB> --from <D.PAD> --to <D.PAD> --net <NET> --json`；PNG `easyeda pcb view-side --side top|bottom` + `easyeda pcb snapshot --fit-mode board`；SVG `easyeda pcb layout render --actual --board <dump> --side both --out <svg>`；BOM `easyeda bom export --type csv`（默认 enrich）；epro2 `easyeda project export --window <id> --project-uuid <uuid> --out <file>`；save/reload diff `python -m design_engine pcb-diff --before <dump> --after <dump-after-reload> --json`；A 的 pcb-check-plan/pcb-power/pcb-fabrication 见 README 复现段；edit scoped diff 为 `pcb-diff --scope <scope.json>`（inferred，cli.py:667-671）。

evidence: references/pcb-execution.md:23,245；design-gates.md:194,196,221；scratch board-a-next-steps.md:43-45,58-60；scratch netpath_check.py:22-25 与 boardB_netpath_final.py:23-26；assets/docs/silk-assembly.md:64；A README.md:88-95；B README.md:82-84；design_engine/cli.py:667-671,682-707；pcb_apply_plan.py:65-72。

### 板 B 的 DRC/check/netpath 都早于最终 save→reload 和最终 .epro2：DRC 13:39:01Z、check 13:38:57Z、netpath 13:39:54Z；dump-final 13:40:12.948Z、after-reload 13:40:44.976Z、epro2 本地 21:41:53；README 却写 DRC 在“最终 save→reload 后”，case 中没有 post-reload DRC。

evidence: 文件 mtime 与 pcb-dump-final.json capture.capturedAt=2026-10-26T13:40:12.9486363Z、after-reload capture=13:40:44.9769342Z；B README.md:31；scratch boardB-drc-final.json 与 case 同哈希，boardB-check-silk3.json 与 case 同哈希。

### 板 A 的 PNG（bottom 12:49:05Z、top 12:49:48Z）、BOM（12:50:38Z）、netpath（12:48:37Z）、sch-compare（12:50:25Z）都早于最终 dump（12:51:18Z）和 epro2（12:51:38Z）；但 pcb-diff 对 boardA-final-a（12:48:06Z）与 final-c（12:51:18Z）返回 match（identity/geometry/copper/unrelated 全 0），归档也包含 final dump 的全部对象，所以没有内容变化的证据，风险在 PNG 没有源哈希。

evidence: 文件 mtime；`python -m design_engine pcb-diff --before C:/Users/jlc/work/pcb-round9-scratch/boardA-final-a.json --after boardA-final-c.json` 输出 status=match、counts 全 0；SVG metadata sourceSha256=3a07ade...；A README.md:16,31；archive 对象计数见上一条。

### edit-add-decap 链不完整：DRC 13:47:53Z 早于 edit dump 13:48:05Z 和 reload/epro2 13:48:31/32Z；after-reload dump 只在 scratch（boardB-edit-final-b.json），未复制进 case；edit check 在 case 中但未注册；scoped diff 使用的 scope JSON（{'designators':['C99'],'nets':['+3V3','GND']}）也未保留。

evidence: 文件 mtime；B design-state.json:137-148 只注册 edit scoped-diff/save-reload-diff/drc/archive；C:/Users/jlc/work/pcb-round9-scratch/boardB-edit-final-b.json；boardB-edit-scope.json；design_engine/cli.py:667-671。

### board B 的 placement-apply-report.json 顶层 status=mismatch，但 records 23/23 applied+verified、diff counts identity=0/geometry=23/copper=0/unrelated=0；按当前 pcb_apply_plan.py 的 expected_placement_diff 会判 verified，说明该报告由修复前版本生成，是版本/失败记录问题。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/placement-apply-report.json；design-hardware/scripts/pcb_apply_plan.py:54-58、145；commit da77226 'fix apply verification' 修改了该逻辑；B README.md:58 声称 23/23 verified。

### 现有文件名与 gate_check.py 的角色模式不兼容：netpath-key-connections.json 不匹配 net-path*.json；save-reload-diff.json 不匹配 *reload*readback*；lint、project-export、pcb-pours、pcb-vias 角色没有对应文件；design-state 也缺 gate 读取的 schematic/layout/stackup/routing/manufacturing/sourcing 键。

evidence: gate_check.py:115（pcb_layout_lint）、:119-120（pcb_pours/pcb_vias）、:123（net_path）、:124（reopen_check）、:125（project_export）；Path.glob 模式实测 netpath-key-connections.json 与 save-reload-diff.json 均不匹配；gate_check.py:1339-1969；两 design-state 顶层键见上。

### 案例中可机器读取的版本只有：EasyEDA Pro 4.1.78（.epro2 内 project2.json editorVersion 与 PCB DOCHEAD editVersion）、easyeda-agent 1.15.0（easyeda version）、design_engine 1.0.0、skill 0.9.1；Connector 1.15.0 只在 README 文字里，Python/OS/repo commit 未记录。

evidence: epro2 zip member project2.json；easyeda version 输出；design-hardware/scripts/design_engine/__init__.py:13；design-hardware/.version；A README.md:17；B README.md:14；repo HEAD 60f2f2c（git log -1）。

### 按 rev4 任务书，case manifest 至少要包含 versions、commands、hashes、failures；仓库现有可参考形状是 sch_layout_pipeline 的 run-manifest（status/inputs sha/steps[argv,exit,stdout_sha256,stderr_sha256]/evidence NOT RUN）和 docs/evidence 的 files[{file,bytes,sha256}]。

evidence: workflow 脚本 C:/Users/jlc/.claude/projects/C--Users-jlc/24a71959-9bf3-45b7-87f5-2bd189caed32/workflows/scripts/pcb-skill-recon-wf_5f0f3b9b-0b3.js:151-166；design-hardware/scripts/sch_layout_pipeline.py:29-46,175-190；docs/evidence/round7-baseline-2026-10-24/manifest.json；docs/evidence/round7-apply/manifest.json。
