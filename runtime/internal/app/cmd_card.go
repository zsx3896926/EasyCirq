package app

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

// cardAdvice is the one-line fix a customer can act on. It is deliberately
// separate from the KPI id: the customer reads the sentence, not the metric.
var cardAdvice = map[string]string{
	"unconnected":  "把它连到该连的地方，或显式标成不接（NC）",
	"cross_zone":   "在两端改用网络标签，不要拉长线跨区",
	"overlaps":     "挪开叠在一起的器件或文字",
	"net_text":     "给这行字找回归属，或删掉它",
	"bus":          "补齐总线/差分对缺的那一根",
	"wire_length":  "拆成短线 + 标签",
	"readability":  "局部电路尽量用导线直接连",
	"zone_balance": "把器件在各分区之间挪匀",
	"erc":          "按 DRC 提示逐条改（输出冲突/多驱动等）",
	"pin_mux":      "换一个引脚，或声明该复用是有意的",
	"decoupling":   "给电源脚补一颗去耦电容",
	"naming":       "改成有意义的名字",
	"bom_map":      "补上封装/型号/立创编号",
	"netlist_diff": "确认这次改动是不是真的等价",
	"readback":     "保存、重开、回读，确认对象都还在",
}

type cardEntry struct {
	KPI    string `json:"kpi"`
	Plain  string `json:"plain"`
	Advice string `json:"advice,omitempty"`
	Reason string `json:"reason,omitempty"`
}

type cardResult struct {
	Schema   string         `json:"schema"`
	State    string         `json:"state"`
	Headline string         `json:"headline"`
	Next     string         `json:"next"`
	Counts   map[string]int `json:"counts"`
	Blockers []cardEntry    `json:"blockers"`
	Missing  []cardEntry    `json:"missing"`
	Project  string         `json:"project,omitempty"`
	Page     string         `json:"page,omitempty"`
}

// analyzeCard answers the customer's actual question -- can this be ordered? --
// and never claims "ready" without a live write permission.
func analyzeCard(report *statusReport, gatePath, gateOverride string) cardResult {
	result := cardResult{
		Schema: "easycirq-sch-delivery-card/v1",
		Counts: map[string]int{"pass": 0, "fail": 0, "missing": 0, "na": 0, "advisory": 0},
		Blockers: []cardEntry{}, Missing: []cardEntry{},
	}
	if report == nil {
		result.State, result.Headline = "not_measured", "⏳ 这块板还没检查过"
		result.Next = "先跑一轮离线检查，再回来看这张卡"
		return result
	}
	result.Project, result.Page = report.Project, report.Page
	statusOf := map[string]string{}
	for _, kpi := range report.KPIs {
		statusOf[kpi.ID] = kpi.Status
		if kpi.Advisory {
			result.Counts["advisory"]++
			continue
		}
		switch kpi.Status {
		case "pass":
			result.Counts["pass"]++
		case "fail":
			result.Counts["fail"]++
		case "missing", "unknown":
			result.Counts["missing"]++
		case "na":
			result.Counts["na"]++
		}
	}
	for _, blocker := range report.Blockers {
		entry := cardEntry{KPI: blocker.KPI, Plain: plainFor(blocker.KPI),
			Advice: cardAdvice[blocker.KPI], Reason: blocker.Reason}
		if entry.Advice == "" {
			entry.Advice = "按检查结果修正"
		}
		if s := statusOf[blocker.KPI]; s == "missing" || s == "unknown" {
			entry.Advice = ""
			result.Missing = append(result.Missing, entry)
		} else {
			result.Blockers = append(result.Blockers, entry)
		}
	}

	live, detail := true, ""
	if gateOverride != "" {
		live, detail = gateLive(gatePath)
	}
	unmeasured := 0
	for _, kpi := range report.KPIs {
		if !kpi.Advisory && (kpi.Status == "missing" || kpi.Status == "unknown") {
			unmeasured++
		}
	}
	switch {
	case strings.EqualFold(report.Verdict, "PASS") && unmeasured > 0:
		result.State, result.Headline = "incomplete", "⏳ 还不能判断：有些检查还没做"
		result.Next = "补齐下面这些检查需要的资料，再跑一轮"
	case strings.EqualFold(report.Verdict, "PASS") && live:
		result.State, result.Headline = "ready", "✅ 可以打样"
		result.Next = "导出制造文件；打样回来后做验收"
	case strings.EqualFold(report.Verdict, "PASS"):
		result.State, result.Headline = "gate_stale", "⚠️ 检查通过，但需要重新确认"
		result.Next = detail + "；重新跑一次检查即可"
	case strings.EqualFold(report.Verdict, "REVIEW"):
		result.State, result.Headline = "review", "⚠️ 可以打样，但有需要留意的项"
		result.Next = "确认下面这些提醒可接受，再导出制造文件"
	case len(result.Blockers) > 0:
		result.State, result.Headline = "blocked", "❌ 还不能打样"
		result.Next = "按下面的建议逐条修，修完重新测量"
	default:
		result.State, result.Headline = "incomplete", "⏳ 还不能判断：有些检查还没做"
		result.Next = "补齐下面这些检查需要的资料，再跑一轮"
	}
	return result
}

func renderCard(result cardResult) string {
	var b strings.Builder
	b.WriteString(result.Headline + "\n\n")
	if len(result.Blockers) > 0 {
		b.WriteString("必须修的问题：\n")
		for _, entry := range result.Blockers {
			fmt.Fprintf(&b, "  · %s\n    → %s\n", entry.Plain, entry.Advice)
		}
		b.WriteString("\n")
	}
	if len(result.Missing) > 0 {
		b.WriteString("还没检查的项目（补上资料即可）：\n")
		for _, entry := range result.Missing {
			fmt.Fprintf(&b, "  · %s\n", entry.Plain)
		}
		b.WriteString("\n")
	}
	c := result.Counts
	total := c["pass"] + c["fail"] + c["missing"]
	fmt.Fprintf(&b, "检查结果：必查 %d/%d 通过 · 缺证据 %d · 不适用 %d · 提醒 %d\n",
		c["pass"], total, c["missing"], c["na"], c["advisory"])
	fmt.Fprintf(&b, "下一步：%s", result.Next)
	return b.String()
}

// ── card ──────────────────────────────────────────────────────────────────

func newCardCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var kpiReport, gate string
	var asJSON bool
	c := &cobra.Command{
		Use:   "card",
		Short: "One card: can this board be ordered, and what is left",
		Long: `The customer-facing answer to "can I order this board?". It reads the last
offline KPI report and the write permission; it never re-measures and never
claims "ready" without a live permission. Missing evidence is shown apart from
real defects: an untested item is not a broken one.

Exit codes: 0 ready, 1 not ready, 2 not measured or invalid.`,
		Args:    cobra.NoArgs,
		Example: `  easycirq card\n  easycirq card --kpi-report reports/p1/kpi-report.json`,
		RunE: func(cmd *cobra.Command, args []string) error {
			reportPath := kpiReport
			if reportPath == "" {
				if cwd, err := os.Getwd(); err == nil {
					reportPath = filepath.Join(cwd, ".easycirq", "kpi-report.json")
				}
			}
			var report *statusReport
			if _, err := os.Stat(reportPath); err == nil {
				var loaded statusReport
				if err := readStatusJSON(reportPath, &loaded); err != nil {
					return exitCodeError{code: 2}
				}
				report = &loaded
			}
			gatePath := gate
			if gatePath == "" {
				if cwd, err := os.Getwd(); err == nil {
					gatePath = filepath.Join(cwd, ".easycirq", "gate.json")
				}
			}
			result := analyzeCard(report, gatePath, gate)
			if asJSON {
				raw, _ := json.MarshalIndent(result, "", "  ")
				fmt.Fprintln(stdout, string(raw))
			} else {
				fmt.Fprintln(stdout, renderCard(result))
			}
			switch result.State {
			case "ready":
				return nil
			case "blocked", "review", "gate_stale":
				return exitCodeError{code: 1}
			default:
				return exitCodeError{code: 2}
			}
		},
	}
	c.Flags().StringVar(&kpiReport, "kpi-report", "",
		"offline KPI report (default .easycirq/kpi-report.json)")
	c.Flags().StringVar(&gate, "gate", "",
		"write permission file (default .easycirq/gate.json); pass it explicitly to require one")
	c.Flags().BoolVar(&asJSON, "json", false, "print JSON")
	return c
}
