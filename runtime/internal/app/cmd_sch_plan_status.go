package app

// cmd_sch_plan_status.go — 「离线先行」四阶段的**可见状态**（面板要渲染它）。
//
// 为什么需要它：闸门只管"放不放行"，但人需要看到**卡在哪一步**。
// 只有一句"没有回执"，用户不知道是 S1 没写、S2 没过、还是 S4 没跑。
//
// 面板照旧零判定：这份状态由 CLI 算，面板只渲染。

import (
	"encoding/json"
	"fmt"
	"io"

	"github.com/spf13/cobra"
)

type planStage struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Status string `json:"status"` // done | pending | missing
	Detail string `json:"detail,omitempty"`
}

type planStatusReport struct {
	Project string      `json:"project"`
	Stages  []planStage `json:"stages"`
	Gate    string      `json:"gate"` // open | closed
	Reason  string      `json:"reason,omitempty"`
	HowTo   []string    `json:"howTo,omitempty"`
}

func buildPlanStatus(project string) planStatusReport {
	rep := planStatusReport{Project: project, Stages: []planStage{}}
	r, ok := loadPlanReceipt(project)

	// S1：规格。回执里没有单独字段，所以用"有没有回执"来表达"走没走过流程"，
	// 但**如实标注**它是从回执推断的，不假装我们见过 spec.json。
	s1 := planStage{ID: "S1", Name: "离线规格化", Status: "missing"}
	switch {
	case !ok:
		s1.Detail = "没有规划回执：S1–S4 都没走"
	case r.StylePlan != "":
		s1.Status = "done"
		s1.Detail = "已登记规划证据（回执 " + r.PlannedAt + "）"
	default:
		s1.Detail = "回执存在但没有 planning 产物路径"
	}
	rep.Stages = append(rep.Stages, s1)

	s2 := planStage{ID: "S2", Name: "离线布局（style-plan）", Status: "pending"}
	if ok && r.StylePlan != "" {
		if r.StylePlanOK {
			s2.Status = "done"
			s2.Detail = "verdict=pass：" + r.StylePlan
		} else {
			s2.Status = "missing"
			s2.Detail = "未通过：" + r.StylePlan
		}
	} else {
		s2.Detail = "没有 style-plan 证据"
	}
	rep.Stages = append(rep.Stages, s2)

	s3 := planStage{ID: "S3", Name: "离线度量", Status: "pending"}
	if ok && r.KPIReport != "" {
		s3.Status = "done"
		s3.Detail = "检查报告：" + r.KPIReport
	} else {
		s3.Detail = "没有离线度量报告"
	}
	rep.Stages = append(rep.Stages, s3)

	s4 := planStage{ID: "S4", Name: "KPI 门禁（apply_allowed）", Status: "pending"}
	if ok && r.KPIReport != "" {
		if r.ApplyAllowed {
			s4.Status = "done"
			s4.Detail = "apply_allowed=true"
		} else {
			s4.Status = "missing"
			s4.Detail = "apply_allowed 不为 true"
		}
	} else {
		s4.Detail = "没有 KPI 报告"
	}
	rep.Stages = append(rep.Stages, s4)

	g := planGate(project, "", false)
	rep.Gate = map[bool]string{true: "open", false: "closed"}[g.Allow]
	rep.Reason = g.Reason
	rep.HowTo = g.HowTo
	if ok && r.Unplanned {
		rep.Gate = "closed"
		rep.Reason = "这块板是用 --unplanned 落图的：流程没走完"
	}
	return rep
}

func newSchPlanStatusCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var asJSON bool
	c := &cobra.Command{
		Use:   "plan-status",
		Short: "Show the offline-first stages (S1-S4) and whether the placement gate is open",
		Long: `显示「离线先行」四阶段的状态与闸门结论。

闸门只管放不放行；这条命令负责说清**卡在哪一步**：
是哪一阶段没做、哪一份证据没过。面板的「离线规划」卡渲染的就是它。`,
		Example: `  easycirq sch plan-status
  easycirq sch plan-status --json`,
		RunE: func(cmd *cobra.Command, args []string) error {
			rep := buildPlanStatus(cfg.project)
			if asJSON {
				enc := json.NewEncoder(stdout)
				enc.SetIndent("", "  ")
				enc.SetEscapeHTML(false)
				return enc.Encode(rep)
			}
			fmt.Fprintf(stdout, "离线规划：闸门 %s\n", rep.Gate)
			for _, st := range rep.Stages {
				mark := map[string]string{"done": "✓", "pending": "·", "missing": "✗"}[st.Status]
				fmt.Fprintf(stdout, "  %s %-4s %-22s %s\n", mark, st.ID, st.Name, st.Detail)
			}
			if rep.Reason != "" {
				fmt.Fprintf(stdout, "  %s\n", rep.Reason)
			}
			for _, h := range rep.HowTo {
				fmt.Fprintf(stdout, "    %s\n", h)
			}
			return nil
		},
	}
	c.Flags().BoolVar(&asJSON, "json", false, "以 JSON 输出")
	return c
}
