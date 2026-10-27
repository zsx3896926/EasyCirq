# round11 真机小范围回归（2026-10-27）

使用已安装 **0.9.3**（Claude 客户端）与真实 EasyEDA 4.1.78 / easyeda-agent 1.15.0。

1. 从 `dual-button-led-night-20261027/case/evidence/case.epro2` 导入为新工程
   `dual-button-led-r11-20261027`（UUID `1ce3c95f9714476b999a920c2e65b3c9`）；
   `project import` 返回 `created:true`、`verified:true`、`contentVerified:false`，
   打开后 12 个器件、PCB `49c8e7a5dc2e8f59`，fresh dump semantic hash
   `240dee0a...` 与源工程一致。
2. 局部移动 D4：`pcb_apply_plan --apply` 一次 apply → save → reload → dump；
   `status=verified`、journal pass、save/reload/dump ok、diff `changed`，
   仅 D4 pose `808.74 → 810.0`，unrelated 0。
3. 恢复 D4：同一流程回到 `808.74`；最终 dump semantic hash 恢复为
   `240dee0a...`，与导入前一致，证明保存重开持久化。
4. 已安装 0.9.3 的 `pcb_gate --profile full --key-nets ...` 在交付 case 上
   **8/8 pass**（PG1–PG8）。
5. 未重跑原生 DRC/check；其证据沿用交付 case。导入/移动/恢复不证明该板
   电气重新验收，制造/实物仍 NOT RUN。

证据：`before.json`、`after-move.json`、`after-restore.json`、
`move-report.json`、`restore-report.json`、`gate-report.json`。
