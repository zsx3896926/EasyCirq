package app

// cmd_sch_plan_ack.go — 记录「离线先行」证据（S2 风格门 + S4 KPI 门）。

import (
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/spf13/cobra"
)

func newSchPlanAckCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var (
		stylePlan string
		kpiReport string
		page      string
		asJSON    bool
	)
	c := &cobra.Command{
		Use:   "plan-ack",
		Short: "Record offline-plan evidence (S2 style plan + S4 KPI) so block-apply will run",
		Long: `记录「离线先行」的证据回执。

产品文档写着「未过 S2 不得进器件」「apply_allowed 才允许上机」——那是**一句话**。
这条命令把那句话变成**回执**：` + "`block-apply`" + ` 落块前会检查它，没有就拒绝。

回执要的是**证据存在且通过**，不是"我觉得规划过了"：

  --style-plan  S2 的 style-plan.json；脚本里 verdict=pass 才算 stylePlanChecked
  --kpi-report  S4 的 kpi-report.json；apply_allowed 必须为 true

两个都给齐，回执才成立。缺一个，闸门继续拦。

确实要先落图看效果，用 ` + "`block-apply --unplanned`" + `：它会放行，但回执里记
` + "`unplanned: true`" + `，而 ` + "`card`" + ` 会因此拒绝说"可以打样"。`,
		Example: `  easycirq sch plan-ack --style-plan reports/style-plan.json --kpi-report reports/kpi-report.json
  easycirq sch plan-ack --style-plan reports/style-plan.json --kpi-report reports/kpi-report.json --json`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if stylePlan == "" || kpiReport == "" {
				return fmt.Errorf("--style-plan 与 --kpi-report 都要给：回执要的是证据，不是承诺")
			}
			project := cfg.project
			r := planReceipt{Project: project, Page: page}

			// --- S2：读 style-plan 报告，看它自己说什么 ---
			//
			// **只有真读到了才登记路径。** 否则回执里会留下一条指向不存在文件的
			// 记录，而 plan-status 会据此显示 ✓ —— 那等于把"给了个路径"当成
			// "有证据"。（实测踩过：kpi-report.json 根本不存在，S3 却显示已完成。）
			okStyle, styleDetail := planReadVerdict(stylePlan)
			r.StylePlanOK = okStyle
			if _, err := os.Stat(stylePlan); err == nil {
				r.StylePlan = stylePlan
			}

			// --- S4：读 kpi-report，看 apply_allowed ---
			okKPI, kpiDetail := planReadApplyAllowed(kpiReport)
			r.ApplyAllowed = okKPI
			if _, err := os.Stat(kpiReport); err == nil {
				r.KPIReport = kpiReport
			}

			if err := savePlanReceipt(r); err != nil {
				return fmt.Errorf("写回执失败（%w）—— 闸门仍会拦，所以这不是放行", err)
			}
			out := map[string]any{
				"project":         project,
				"page":            page,
				"stylePlan":       stylePlan,
				"stylePlanOK":     okStyle,
				"stylePlanDetail": styleDetail,
				"kpiReport":       kpiReport,
				"applyAllowed":    okKPI,
				"kpiDetail":       kpiDetail,
				"gate":            map[bool]string{true: "open", false: "closed"}[okStyle && okKPI],
			}
			if asJSON {
				enc := json.NewEncoder(stdout)
				enc.SetIndent("", "  ")
				enc.SetEscapeHTML(false)
				return enc.Encode(out)
			}
			fmt.Fprintf(stdout, "回执已记录：%s\n", planReceiptPath(project))
			fmt.Fprintf(stdout, "  S2 style-plan : %v  %s\n", okStyle, styleDetail)
			fmt.Fprintf(stdout, "  S4 kpi-report : %v  %s\n", okKPI, kpiDetail)
			if okStyle && okKPI {
				fmt.Fprintln(stdout, "  闸门：open —— 可以落块")
			} else {
				fmt.Fprintln(stdout, "  闸门：closed —— 证据不齐，block-apply 仍会拒绝")
			}
			return nil
		},
	}
	c.Flags().StringVar(&stylePlan, "style-plan", "", "S2 的 style-plan.json 报告")
	c.Flags().StringVar(&kpiReport, "kpi-report", "", "S4 的 kpi-report.json")
	c.Flags().StringVar(&page, "page", "", "限定到某一页（可选）")
	c.Flags().BoolVar(&asJSON, "json", false, "以 JSON 输出")
	return c
}

// planReadVerdict 从风格门报告里取 verdict。
//
// 只认 `verdict == "pass"`；`review` / `blocked` / 缺字段都不算通过 ——
// "没有明确通过"和"没通过"在这里是同一件事。
func planReadVerdict(path string) (bool, string) {
	body, err := os.ReadFile(path)
	if err != nil {
		return false, "读不到：" + err.Error()
	}
	var v struct {
		Verdict string   `json:"verdict"`
		Summary string   `json:"summary"`
		Errors  []string `json:"errors"`
	}
	if err := json.Unmarshal(body, &v); err != nil {
		return false, "不是 JSON：" + err.Error()
	}
	if v.Verdict == "" {
		return false, "报告里没有 verdict 字段"
	}
	return v.Verdict == "pass", "verdict=" + v.Verdict
}

// planReadApplyAllowed 从 KPI 报告里取 apply_allowed。
func planReadApplyAllowed(path string) (bool, string) {
	body, err := os.ReadFile(path)
	if err != nil {
		return false, "读不到：" + err.Error()
	}
	var v struct {
		ApplyAllowed *bool  `json:"apply_allowed"`
		Verdict      string `json:"verdict"`
	}
	if err := json.Unmarshal(body, &v); err != nil {
		return false, "不是 JSON：" + err.Error()
	}
	if v.ApplyAllowed == nil {
		return false, fmt.Sprintf("报告里没有 apply_allowed（verdict=%s）", v.Verdict)
	}
	return *v.ApplyAllowed, fmt.Sprintf("apply_allowed=%v verdict=%s", *v.ApplyAllowed, v.Verdict)
}
