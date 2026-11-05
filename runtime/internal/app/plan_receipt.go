package app

// plan_receipt.go — 「离线先行」的**机械闸门**（把一句文档变成一道门）。
//
// 背景（板1/板2 实测，见 friction #40）：产品文档写着
// 「S2 离线布局…**未过 style_plan_check 不得进器件**」「S4 …**apply_allowed 才允许上机**」，
// 但那只是**一句话**。我按自己的目标文档做事，跳过了 S1–S4 直接落块，
// 于是后面几十轮一直在补几何：引脚没连、标号撞图签、组框重叠、块装不下。
//
// 文档管不住人，**闸门才管得住**。所以把"必须先有离线规划"变成落块前的硬检查：
//
//   • 没有规划回执 → `block-apply` **拒绝**（不是警告）
//   • 明确要用 `--unplanned` 跳过 → 允许，但**在回执里记一笔 `unplanned: true`**，
//     而 `card` 会因此拒绝说"可以打样"
//
// 为什么用回执文件而不是每次重算：S2/S4 的产物是**离线**的（style-plan.json、
// kpi-report.json），落块时不该再去解析它们；回执只记"这些证据存在过、在哪、什么时候"。
// 这也让"绕过流程"变成一件**留痕**的事 —— 想跳过可以，但会被记下来。

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// planReceipt 是一份"离线规划已完成"的回执。
type planReceipt struct {
	Project     string `json:"project"`
	Page        string `json:"page,omitempty"`
	StylePlan   string `json:"stylePlan,omitempty"`   // S2 产物路径
	StylePlanOK bool   `json:"stylePlanChecked"`      // sch_style_plan_check 是否通过
	KPIReport   string `json:"kpiReport,omitempty"`   // S4 产物路径
	ApplyAllowed bool  `json:"applyAllowed"`          // KPI 的 apply_allowed
	PlannedAt   string `json:"plannedAt"`
	// Unplanned 为真表示这块板是**绕过流程**落图的。它不会阻止落图，
	// 但会跟着板子一路走到交付卡 —— 让"还没走完流程"这件事没法被悄悄忘掉。
	Unplanned bool   `json:"unplanned,omitempty"`
	Note      string `json:"note,omitempty"`
}

func planReceiptPath(project string) string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	name := sanitizeKey(project)
	if name == "" {
		name = "_active"
	}
	return filepath.Join(home, ".easycirq", "plan-receipt-"+name+".json")
}

func sanitizeKey(s string) string {
	out := make([]rune, 0, len(s))
	for _, r := range s {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-', r == '_':
			out = append(out, r)
		}
	}
	if len(out) > 64 {
		out = out[:64]
	}
	return string(out)
}

// loadPlanReceipt 读回执；不存在就返回 false（"没走过流程"）。
func loadPlanReceipt(project string) (planReceipt, bool) {
	p := planReceiptPath(project)
	if p == "" {
		return planReceipt{}, false
	}
	body, err := os.ReadFile(p)
	if err != nil {
		return planReceipt{}, false
	}
	var r planReceipt
	if err := json.Unmarshal(body, &r); err != nil {
		return planReceipt{}, false
	}
	return r, true
}

// savePlanReceipt 写回执。写不进去**不是**致命错误：闸门会因此认为"没规划"，
// 那是安全方向（拒绝落块），不是放行。
func savePlanReceipt(r planReceipt) error {
	p := planReceiptPath(r.Project)
	if p == "" {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	if r.PlannedAt == "" {
		r.PlannedAt = time.Now().UTC().Format(time.RFC3339)
	}
	body, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(p, body, 0o644)
}

// planGate 决定"现在允许落块吗"，并给出**可执行的下一步**。
//
// 三种结论：
//   ok        —— 有回执且 stylePlanChecked && applyAllowed
//   unplanned —— 调用方显式 --unplanned；放行，但要求把这事记进回执
//   refuse    —— 没回执或回执不完整；拒绝，并列出凑齐证据的确切命令
type planGateResult struct {
	Allow   bool
	Reason  string
	HowTo   []string
	Receipt planReceipt
}

func planGate(project, page string, allowUnplanned bool) planGateResult {
	r, ok := loadPlanReceipt(project)
	if allowUnplanned {
		r.Project = project
		r.Page = page
		r.Unplanned = true
		r.Note = "--unplanned：绕过离线规划落图；交付卡会因此拒绝说可以打样"
		return planGateResult{Allow: true, Reason: r.Note, Receipt: r}
	}
	if !ok {
		return planGateResult{
			Allow:  false,
			Reason: "这块板还没有离线规划回执 —— 「未过 S2 不得进器件」是硬规则，不是建议",
			HowTo: []string{
				"1) S1 写 spec.json（功能模块、电源树、跨页网、NC 声明）",
				"2) S2 出 style-plan.json，然后跑：python easycirq/scripts/sch_style_plan_check.py style-plan.json",
				"3) S3/S4 跑离线度量与 15 项 KPI，拿到 apply_allowed=true（连续 2 轮 PASS）",
				"4) 回执：easycirq sch plan-ack --style-plan <file> --kpi-report <file>",
				"   确实要先落图看效果：加 --unplanned（会留痕，交付卡会拒绝放行）",
			},
		}
	}
	if !r.StylePlanOK || !r.ApplyAllowed {
		return planGateResult{
			Allow:   false,
			Reason:  "离线规划回执存在，但证据不完整（stylePlanChecked/applyAllowed 至少一项为假）",
			HowTo:   []string{"补齐 S2 的风格门与 S4 的 KPI 门，然后重跑 `easycirq sch plan-ack`"},
			Receipt: r,
		}
	}
	return planGateResult{Allow: true, Reason: "离线规划证据齐全", Receipt: r}
}
