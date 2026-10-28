【给 A：annotation-layout capability record 回传请求】

K 的离线标注规划与 probe 接入链路已合入 main（当前 main=697d511）。工作区里目前没有找到你实际回传的 capability record，只有格式示例。请在“一次性页面副本”上完成 probe 并回传 record 和证据。

一、执行步骤（不要在生产页面直接探测）
1. 复制页面/工程，确认无其他写入者，先导出 .epro2 备份。
2. 记录 host 名称/版本、project、page_id、page snapshot sha256、probe 时间。
3. 按这个 quickstart 执行 P0–P7：
   docs/parallel-annotation-layout/integration-probe-quickstart.md
   - P0 读回稳定性（读两次 + save/reopen 无编辑）
   - P1 attribute 平移（位号、值分别 +5 raw x，各有证据）
   - P2 free text 平移（+5 raw y，重点验证 save+reopen 后是否持久）
   - P3 net-label 文字与 anchor 分离（anchor/net/connectivity 必须不变）
   - P5 ID/数量稳定、P6 host bbox 与官方 SVG bbox 一致性、P7 回滚
   - P4 旋转/对齐可选；当前 K 只做平移，不要改 rotation/font
   每个 probe 保留：对象 ID/内容/bbox、操作 dx/dy、即时读回、save+reopen 读回、官方 SVG/PNG、checker 与 connectivity 前后对比、容差。
   若 free-text 不持久或 net-label 不能分离，直接记 unsupported，不要改内容/net 或手工修连接。

二、生成 record 并自检
1. 复制 docs/parallel-annotation-layout/integration-capability-record.example.json，填入真实证据。
   - execution 必须为 not_executed
   - capability_source 用 onsite_probe_<date>_<page_id>
2. 自检命令（在 easycirq/scripts 下）：
   python -m annotation_layout probe-check <你的 capability-record.json 路径> --out <host-block.json>
   exit 0 且 stdout 的 status=valid 才继续；把 stdout JSON（尤其 warnings）一并回传。
   若 exit 2，按 errors 修 record，不要绕开。

三、回传内容（请给绝对路径或直接附文件）
probe-<page_id>-<date>/
  capability-record.json
  host-block.json
  probe-before/   # sch list / sheet-geometry / check / connectivity / 官方 SVG
  probe-after/    # save+reopen 后的同样证据
  probe-log.md    # 每个 probe 一行：对象、操作、结果、失败原因、容差
并在消息中写明：
  - page_id、snapshot_sha256、host/version、probe 时间
  - 哪些 capability 是 supported / unverified / unsupported
  - 哪些对象必须保持 fixed
  - NOT RUN 项（如有）

四、K 收到后
- 运行 probe-check，并用 probe-bind 将 record 绑定到 page/snapshot 匹配的 annotation-layout/v1 输入；
- 运行 annotation_layout plan，返回计划与独立验证结果；
- A 再按 docs/parallel-annotation-layout/integration-apply-checklist.md 在副本执行 apply → save/reopen → 官方导图 → checker/连通性回读，并回传 acceptance 证据。
- K 不调用 EDA，也不把离线计划当写入授权。

任何一步失败请直接回传失败点、原始证据和最小缺口（需要更准 bbox / 更大分区 / host 能力限制），不要用缩字号、隐藏文字、改内容或改网名换通过。
