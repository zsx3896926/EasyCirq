# tests

## summary

审计对象：C:/Users/jlc/work/hds-pcb-round9。`python -m unittest discover -s tests` 共发现 982 个 unittest；三次运行中两次各出现 1 个失败/错误，均在 tests/test_skill_update.py 的 Windows 临时目录 os.replace 场景，第三次 OK；PCB 定向测试单独运行 25/25（test_pcb_workflow）与 73/73（test_eda_exec_pcb）全部通过。任务给出的 `| tail -5` 看不到 unittest 汇总，只看到 tests/test_thermal_calc_legacy.py:188 打印的 29/29 输出。现有 fake easyeda 是对象级 FakePcbPro（FIFO 重放 snapshot、记录 calls），没有可执行文件/PATH harness；pcb_apply_plan 的 apply 分支直接 subprocess 调用真实 easyeda，只有 dry-run/拒绝路径有测试，save/reload/dump 失败未判失败。新工具应按 unittest + temp dirs + fixtures + CLI subprocess 的现有约定测试，并给 pcb_apply_plan 增加 --easyeda/runner 注入，用脚本化 fake 重放 apply→save→reload→dump。审计中一次 PATH shadow 探针误命中真实 easyeda 并执行了 `pcb save`（返回 saved:false/SAVE_UNCONFIRMED），未确认写入，但需复核项目状态。

## gaps

- 全量测试不可重复：3 次运行 2 次各 1 个 test_skill_update 的 Windows 临时目录失败，另一次 OK；因此 handoff 中“982 tests OK”不能作为稳定验收结论。
- 任务给定的 `| tail -5` 看不到 `Ran/OK/FAILED` 汇总，只看到 tests/test_thermal_calc_legacy.py:188 的 29/29 输出，判断通过与否会误判。
- 没有可执行的 fake easyeda 测试装置；现有 FakePcbPro 只替换 eda.LcedaPro，无法覆盖 pcb_apply_plan 直接 subprocess 调用 `easyeda` 的 apply 分支。
- pcb_apply_plan 的 apply 路径没有成功/失败测试：save 返回 saved:false、reload 失败、dump 非零退出、dump 缺失、after dump 不匹配、超时均未被现有测试覆盖，其中 save/reload 失败当前甚至不会改变 status。
- 没有 batch playbook 测试；apply→save→reload→dump 的顺序、单次批量调用、首次失败停止、失败后不重放都未验证。
- pcb_preflight.py、pcb_gate.py、pcb_case.py 尚不存在，自然没有测试；新增工具也没有既有 fixture/case 契约可复用。
- skill_selftest 只 py_compile 脚本，不验证行为；新脚本不会自动加入 REQUIRED_FILES，gate-naming 检查也只覆盖 G0..G6 和 gate_check.py。
- tests/test_pcb_workflow.py:371-376 的注释称 constraints 文件缺失时会“generated below”，但测试中没有任何生成代码；该注释已过期，容易误导新增测试。
- 审计中误触真实 easyeda 的 `pcb save`（saved:false/SAVE_UNCONFIRMED）；photo-led-5v-20261026 是否完全未变尚未独立核验，后续测试必须禁止 PATH 回退到真实 CLI。
- pcb_apply_plan 没有 --easyeda、runner 注入或 subprocess timeout；测试无法安全地指向 fake，也无法覆盖超时/部分未知状态。

## recommendations

- 给 pcb_apply_plan 增加 `--easyeda`（默认 `easyeda`）和可注入的 runner/`_run` seam，并增加 `--timeout`；所有命令（modify/save/reload/dump）都使用该路径。测试传 fake 的绝对路径或 patch `_run`，不要依赖 PATH。
- 新增 tests/test_pcb_apply_plan.py：定义进程内 FakeEasyEda，按 FIFO 或 argv match 返回 (exit, stdout JSON)，记录每次 argv；覆盖 dry-run 零调用、apply→save→reload→dump 顺序、首件 verified=false 停止、save saved=false、reload 失败、dump 缺失、scoped diff mismatch、超时。
- 新增可执行级 replay fixture：tests/fixtures/fake-easyeda/ 放 scenario JSON、fake_easyeda.py、Windows easyeda.cmd 和 POSIX shim。fake 记录 calls、按步骤返回 JSON、按 `write_file` 生成 after dump；Windows 必须传 .cmd 绝对路径（PATH 中同名 .bat/.cmd 不会 shadow easyeda.exe）。
- batch playbook replay：fake 读取 before dump 和 `--playbook`，按 playbook 修改内部 state，再在 `pcb dump --out` 时写出 after dump；断言工具只发一次 apply，然后 save→reload→dump，且 after 与预期逐字段一致。失败注入覆盖 unverified、save:false、reload error、dump 非零、after 含 unrelated/identity/copper 变化。
- pcb_preflight 测试：建 tests/test_pcb_preflight.py，setUpClass 加载 tests/fixtures 的 board/plan/intent/constraints；正例断言 pass/measured；用 subTest 对 outline 缺失、bbox 缺失、pad 坐标缺失、stale hash、stale primitiveId、netless pour、silk-over-pad、via/pad net mismatch、power unmeasured 逐项断言具体 finding code 与 CLI exit 1/2。
- pcb_gate 测试：仿 tests/test_gate_check.py:26-43 的 argparse Namespace 助手和 :158-167 的 CLI subprocess 测试；缺失/畸形证据必须 fail/blocked 而非 pass，waiver 只在允许处生效。若复用 G0..G6，更新 skill_selftest 的 GATE_NAME_FILES/STATUS_NAME_FILES；若使用新状态词，增加专用 selftest check。
- pcb_case 测试：建 tests/test_pcb_case.py，用 TemporaryDirectory 构造 case（design-state.json、evidence/、expected.json），断言缺失证据为 NOT RUN/blocked、expected 不匹配 exit 1、重复运行 hash/status 稳定、不会写出 case 目录；可对照 skill_selftest.py:355-384 的 _case_files 和 :491-511 的 gate pair 比对逻辑。
- skill_selftest 注册：把新脚本加入 REQUIRED_FILES（design-hardware/scripts/skill_selftest.py:56-72）；check_python_compile 只证明能编译（:524-549），功能测试仍放 unittest；新增 check 函数后追加到 run_checks（:559-566），返回值用 _check 的 PASS/FAIL/NOT RUN schema（:92-98）。
- 处理 Windows flake：隔离或重试 test_skill_update 的临时目录 os.replace 失败，或在 PCB 验收时只跑 test_pcb_workflow.py + test_eda_exec_pcb.py；用 `grep -E '^(Ran|OK|FAILED|ERROR)'` 或完整日志判断，不要用 `| tail -5`。
- 复核审计中误触的真实 easyeda `pcb save`：确认 photo-led-5v-20261026 未变化；后续测试显式断言 fake 路径不是真实 CLI（例如 `shutil.which('easyeda')` 检查或 mock 拦截），禁止 PATH fake 回退。
- 为 pcb_apply_plan 增加 CLI 契约测试：固定 --dump/--plan/--constraints/--project/--doc/--out-dump/--report/--apply 与 status/exit code；若改名，同时更新 tests/test_pcb_workflow.py:329-359 和 design-hardware/references/pcb-execution.md:209-214。

## facts

### 全量 discover 共 982 个测试，但结果不稳定：三次运行两次各 1 个失败/错误，一次 OK。

evidence: 命令 `python -m unittest discover -s tests`：run1 `Ran 982 tests in 35.721s` + `FAILED (failures=1)`；run2 `Ran 982 tests in 34.602s` + `FAILED (errors=1)`；run3 `Ran 982 tests in 35.101s` + `OK`。

### 任务给出的 `| tail -5` 不是 unittest 汇总，而是 test_thermal_calc_legacy 的 stdout；因此不能据此判断通过。

evidence: tests/test_thermal_calc_legacy.py:188 打印 `{len(checks)-len(failed)}/{len(checks)} checks passed`，即 29/29；unittest 汇总写 stderr，受 stdout 缓冲影响会出现在日志更早位置。

### 第一次失败是 test_skill_update.UpdaterTests.test_cli_real_subprocess_install_and_status：install 子进程返回 2，断言期望 0。

evidence: tests/test_skill_update.py:306-315，断言在 :311 `self.assertEqual(p.returncode, 0, p.stderr)`；实际 `AssertionError: 2 != 0`。

### 第二次失败是 test_skill_update.UpdaterTests.test_invalid_archive_never_alters_customer_project：Windows 下 os.replace(stage, target) 抛 PermissionError WinError 5。

evidence: tests/test_skill_update.py:174-179 调用 u.install；design-hardware/scripts/skill_update.py:269 执行 os.replace；traceback 为 `PermissionError: [WinError 5] 拒绝访问: ...\.design-hardware-stage-... -> ...\skills\design-hardware`。

### PCB 定向测试本身全部通过：test_pcb_workflow 25/25，test_eda_exec_pcb 73/73；两次全量失败都只来自 test_skill_update，不是 PCB 代码。

evidence: 隔离运行 `python -m unittest discover -s tests -p test_pcb_workflow.py` → `Ran 25 tests ... OK`；`-p test_eda_exec_pcb.py` → `Ran 73 tests ... OK`；全量日志中 run1 仅 `FAIL: test_cli_real_subprocess...`，run2 仅 `ERROR: test_invalid_archive...`。

### 测试风格是纯 unittest，无 pytest fixture；按行为层拆 TestCase，部分模块用一个类集中覆盖。

evidence: tests/test_pcb_workflow.py:36-44 用 `PcbWorkflowTests(unittest.TestCase)` + `setUpClass`；tests/test_pcb_workflow.py:387-388 unittest.main；tests/test_eda_exec_pcb.py 按 PcbPlanValidation/PcbReconciliation/PcbVerification/PcbSnapshotComparison/PcbIntegrityCoverage/PcbCommandFlow/PcbBuildFlow 拆类（:125,178,231,319,345,414,448,514,781）。

### 脚本导入有两种约定：pcb_workflow 测试把 scripts 目录插入 sys.path 后直接 import；eda_exec 测试用 importlib.util.spec_from_file_location 加载脚本。

evidence: tests/test_pcb_workflow.py:12-14 `sys.path.insert(0, str(SCRIPTS))`，:16-24 直接 import；tests/test_eda_exec_pcb.py:9-14 importlib spec/exec_module。

### PCB fixture 固定在 tests/fixtures，使用真实测量 dump/plan/intent/constraints；fixture 是保留证据，不是验收结论。

evidence: tests/test_pcb_workflow.py:26-29 定义 `FIXTURES = ROOT/'tests'/'fixtures'` 及 BOARD_PATH/PLAN_PATH/INTENT_PATH；:334/:352/:369 传 `photo-led-pcb-constraints.json`；tests/fixtures/README.md:1-5 明确这些是实际 EasyEDA 页面的只读证据、不得当作项目通过。

### 临时目录/临时文件约定：坏 plan 用 NamedTemporaryFile，CLI 工作目录用 TemporaryDirectory，stdout JSON 用 io.StringIO + contextlib.redirect_stdout 捕获。

evidence: tests/test_pcb_workflow.py:329-359（StringIO 330/348，NamedTemporaryFile 343-346，unlink 359）；tests/test_eda_exec_pcb.py:523-526 write_plan，:544-546/:555-557/:587-593 使用 TemporaryDirectory。

### PCB snapshot fixture 由 pcb_snapshot() 工厂生成，sync_counts() 在突变后同步 total/truncated/counts；负例普遍用 copy.deepcopy 修改。

evidence: tests/test_eda_exec_pcb.py:26-68 pcb_snapshot，:71-81 sync_counts；tests/test_pcb_workflow.py:77-95、tests/test_eda_exec_pcb.py:196-202 等用 deepcopy/直接改 snapshot。

### FakePcbPro 是对象级 fake，不是可执行文件：snapshots 是 FIFO 队列，invoke 按固定 JS 模板常量分派并记录 (code,args)，队列耗尽或未知操作抛 AssertionError。

evidence: tests/test_eda_exec_pcb.py:476-512；:479-483 保存 snapshots/execution/save_result/build/calls；:487-490 `if code == eda.PCB_SNAPSHOT_JS: return self.snapshots.pop(0)`，:502 未知操作 `raise AssertionError`。对应常量：design-hardware/scripts/eda_exec.py:932 PCB_SNAPSHOT_JS、:1081 PCB_APPLY_JS、:1144 PCB_SAVE_JS、:1162 PCB_DRC_JS、:1177 PCB_EXPORT_JS。

### 测试通过替换 eda.LcedaPro 注入 FakePcbPro，并在 finally 恢复；这是当前唯一的 easyeda fake 机制。

evidence: tests/test_eda_exec_pcb.py:514-521 `original = eda.LcedaPro; eda.LcedaPro = lambda *a, **k: fake; ... finally: eda.LcedaPro = original`；PcbBuildFlow 同样在 :781-788；tests/test_eda_exec.py:264-295 的 FakePro 是同一模式。

### 仓库没有 fake easyeda 可执行文件或 PATH shim；pcb_apply_plan 直接 subprocess.run(['easyeda', ...])，没有 --easyeda 或 runner 注入口。

evidence: design-hardware/scripts/pcb_apply_plan.py:28-36 `_run` 直接 subprocess.run，:104-106/:125/:127/:130-131 命令首项硬编码 `easyeda`；全仓 find/git log 未发现 fake easyeda 脚本；tests/test_eda_exec.py:407-410 仅创建一个空的 lceda-pro.exe 路径用于 find_cli，不执行。

### skill_selftest 不用 unittest 注册：run_checks 硬编码 5 个 check，_check 统一返回 PASS/FAIL/NOT RUN 字典，任一 FAIL 或 NOT RUN 导致退出 1。

evidence: design-hardware/scripts/skill_selftest.py:92-98 `_check` schema；:559-566 `checks = [check_required_files, check_markdown_links, check_gate_naming, check_case_regression, check_python_compile]`；:567-570 统计并 `exit_code = 0 if FAIL==0 and NOT RUN==0 else 1`。

### skill_selftest 的 required-files 是显式列表；python-compile 只 glob scripts/*.py 并 py_compile，不执行脚本；case-regression 通过子进程运行 gate_check.py 并比对 G0..G6。

evidence: design-hardware/scripts/skill_selftest.py:56-72 REQUIRED_FILES；:524-549 check_python_compile（doc :12 明确 no script is executed）；:400-521 check_case_regression（:434-460 构造 subprocess，:491-511 比对 gate pairs）；:42-53 GATE_KEYS/GATE_NAME_FILES。

### pcb_apply_plan 的 CLI 契约是 --dump/--plan/--constraints/--project/--doc/--out-dump/--report/--apply，默认 dry-run；dry-run 不调用 subprocess。

evidence: design-hardware/scripts/pcb_apply_plan.py:62-73 argparse；:83-120 validate_placement 后逐件生成 records；:107-110 dry-run 仅 append record，不调用 _run。

### apply 成功后执行 save→doc reload→pcb dump→scoped diff；但 save/reload 的 exit code 和 ok/saved 未强制，dump 只检查文件是否存在。

evidence: design-hardware/scripts/pcb_apply_plan.py:125 save、:127 reload、:130-131 dump、:134-137 仅 `if not os.path.isfile(args.out_dump)` → unverified；:140-147 diff 与 status。save/reload 的 code/payload 只写入 report，不参与失败判定。

### 会因 pcb_apply_plan CLI 变化而失败的现有测试是 test_pcb_workflow.py 的两个 apply adapter 测试：它们直接调用 main 并断言 flags、status 和 records 形状。

evidence: tests/test_pcb_workflow.py:329-359：:332-336 和 :350-354 传入 `--dump/--plan/--constraints/--project/--doc/--out-dump`；:337-340 断言 exit 0/status dry_run/所有 record status dry_run；:355-357 断言 exit 1/status refused。任何 flag 改名、增加必填项或 status 词表变化都会破坏。

### expected_placement_diff 也被直接单测；若升级移动/改名该函数或改变其语义，测试会失败。

evidence: tests/test_pcb_workflow.py:315-327 直接调用 pcb_apply_plan.expected_placement_diff；函数定义在 design-hardware/scripts/pcb_apply_plan.py:54-59。

### test_cli_surface 不调用 pcb_apply_plan，只调用 design_engine.cli 的 pcb-check-plan/pcb-constraints/pcb-candidates，因此不会因 pcb_apply_plan 的 CLI 改动直接失败（除非共享 pcb_workflow 行为变化）。

evidence: tests/test_pcb_workflow.py:361-384；对应子命令注册在 design-hardware/scripts/design_engine/cli.py:946-1046；该文件未 import pcb_apply_plan。

### pcb_apply_plan 的 dry-run 测试没有 patch _run；若升级后 dry-run 引入任何 live easyeda 读取，这两个测试会尝试真实 CLI，可能失败或产生副作用。

evidence: tests/test_pcb_workflow.py:329-359 只调用 pcb_apply_plan.main；design-hardware/scripts/pcb_apply_plan.py:83-110 的 dry-run 目前不调用 _run；_run 定义 :28-36 且无 timeout。

### 仓库当前没有 pcb_preflight.py/pcb_gate.py/pcb_case.py；只有 scripts/pcb_apply_plan.py 和 scripts/design_engine/pcb_workflow.py。

evidence: docs/handoff-pcb-round9.md:12 只列出 pcb_apply_plan；全仓 grep `pcb_preflight|pcb_gate|pcb_case` 无匹配文件（仅任务文本引用）。

### 审计中一次 PATH shadow 探针误命中真实 easyeda CLI，执行了 `pcb save`；返回 ok:false/saved:false/SAVE_UNCONFIRMED，上下文是隐藏的 photo-led-5v-20261026 原理图；未确认写入，项目状态未由本审计验证。

evidence: 本地临时目录探针输出：`"ok": false, "result": {"saved": false}`, `"error": {"code": "SAVE_UNCONFIRMED"}`, `documentType: schematic`, `projectName: photo-led-5v-20261026`；调用形式同 design-hardware/scripts/pcb_apply_plan.py:125 的 `easyeda pcb save`。

### Windows 上把 fake 命名为 easyeda.bat 放进 PATH 不会被 subprocess.run(['easyeda',...]) 命中，会回退到真实 easyeda.exe；传 .cmd 绝对路径则可以执行。

evidence: 本地探针：`subprocess.run(['easyeda','pcb','save'], env=PATH=temp_bin+...)` 仍命中真实 CLI；`subprocess.run([r'...\fake.cmd'])` 返回 fake 的 JSON。pcb_apply_plan.py:104 正是以裸名 `easyeda` 构造命令，因此测试必须用绝对路径或 runner 注入。
