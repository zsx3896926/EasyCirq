package app

// cmd_sch_kpi.go — 把离线 KPI 管线接成 `easycirq sch kpi`。
//
// 为什么需要这个子命令：交付卡（`easycirq card`）读 `.easycirq/kpi-report.json`，
// 而产出它的 `sch_offline_pipeline.py` 原本**没有暴露成 easycirq 子命令**。
// 于是 harness 里的模型无论如何都满足不了 CARD —— 这是真板子干跑时才暴露的
// 卡点：相位机把板子推到 S6，门也过了，但交付卡永远是 not_measured。
//
// 接上来之后，S5 的白名单里就有 `sch kpi`，模型能自己补齐交付卡的证据。

import (
	"io"

	"github.com/spf13/cobra"
)

func newSchKpiCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "kpi",
		Short: "离线 KPI 报告：产出交付卡要读的 kpi-report.json",
		Long: "把冻结快照跑成离线检查 + 15 项 KPI 判词，写出 `kpi-report.json`。\n\n" +
			"**为什么它是交付链的一环**：`easycirq card` 读这份报告；没有它，\n" +
			"交付卡永远是 `not_measured`，而 `not_measured` 不等于通过——\n" +
			"相位机不会放行 DELIVER。原先它只是脚本、没有子命令，于是\n" +
			"harness 里的模型无法补齐这份证据。\n\n" +
			"  easycirq sch kpi --snapshot-dir reports/<页>-snapshot \\\n" +
			"      --project <名称> --page <页uuid> --out-dir .easycirq",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			return runEnterpriseScript(enterpriseScript{
				name: "sch_offline_pipeline.py",
			}, args, stdout, stderr)
		},
	}
}
