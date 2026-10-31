package app

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// plainLabel turns a KPI id into a sentence a customer can act on. The whole
// point of `easycirq status` is that the customer never meets a KPI id.
var statusPlain = map[string]string{
	"unconnected":  "有引脚或网络没有接上",
	"cross_zone":   "有一根线跨过了不该跨的区域",
	"overlaps":     "图上有东西叠在一起",
	"net_text":     "图上有一行字没有归属",
	"bus":          "总线或差分对少了一根",
	"wire_length":  "有一根线太长，读图困难",
	"readability":  "整页几乎全靠标签连接（提醒项）",
	"zone_balance": "各分区里的器件数量不均",
	"erc":          "电气规则有冲突",
	"pin_mux":      "引脚复用冲突",
	"decoupling":   "电源脚没有配电容",
	"naming":       "网络名重复或还是默认名",
	"bom_map":      "元件缺封装、型号或立创编号",
	"netlist_diff": "改动前后连接对不上",
	"readback":     "保存重开后和保存前对不上",
}

type statusKPI struct {
	ID       string `json:"id"`
	Status   string `json:"status"`
	Advisory bool   `json:"advisory"`
}

type statusBlocker struct {
	KPI    string `json:"kpi"`
	Reason string `json:"reason"`
}

type statusReport struct {
	Project   string          `json:"project"`
	Page      string          `json:"page"`
	Verdict   string          `json:"verdict"`
	KPIs      []statusKPI     `json:"kpis"`
	Blockers  []statusBlocker `json:"blockers"`
	Stability struct {
		ApplyAllowed bool `json:"apply_allowed"`
	} `json:"stability"`
}

type statusGate struct {
	Verdict      string `json:"verdict"`
	ApplyAllowed bool   `json:"apply_allowed"`
	ExpiresAt    string `json:"expires_at"`
}

type statusEntry struct {
	KPI    string `json:"kpi"`
	Plain  string `json:"plain"`
	Reason string `json:"reason,omitempty"`
}

type statusResult struct {
	Schema   string        `json:"schema"`
	State    string        `json:"state"`
	Headline string        `json:"headline"`
	Next     string        `json:"next"`
	Verdict  string        `json:"verdict,omitempty"`
	Project  string        `json:"project,omitempty"`
	Page     string        `json:"page,omitempty"`
	Blockers []statusEntry `json:"blockers"`
	Missing  []statusEntry `json:"missing"`
}

func readStatusJSON(path string, into any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, into)
}

func plainFor(kpi string) string {
	if label, ok := statusPlain[kpi]; ok {
		return label
	}
	return kpi
}

// gateLive reports whether the offline checker's write permission is usable.
func gateLive(path string) (bool, string) {
	if path == "" {
		return false, "没有指定通行证路径"
	}
	var token statusGate
	if err := readStatusJSON(path, &token); err != nil {
		if os.IsNotExist(err) {
			return false, "还没确认可以写入"
		}
		return false, fmt.Sprintf("通行证读不出来：%v", err)
	}
	if !strings.EqualFold(token.Verdict, "PASS") || !token.ApplyAllowed {
		return false, "通行证不是 PASS"
	}
	if token.ExpiresAt != "" {
		if when, err := time.Parse(time.RFC3339, token.ExpiresAt); err == nil {
			if time.Now().UTC().After(when) {
				return false, "写入许可已过期（" + token.ExpiresAt + "）"
			}
		}
	}
	return true, "通行证有效到 " + token.ExpiresAt
}

// analyzeStatus maps the artefacts onto exactly one state and one next action.
// "Not measured yet" is kept apart from "measured and failing": a customer who
// never supplied a pin plan has not broken anything.
func analyzeStatus(report *statusReport, gatePath string) statusResult {
	if report == nil {
		return statusResult{
			Schema: "easycirq-sch-status/v1", State: "not_measured",
			Headline: "这块板还没有做过离线检查",
			Next:     "把你想做的板子说给 AI 听就行；画完并检查过之后，这里会告诉你还差什么",
			Blockers: []statusEntry{}, Missing: []statusEntry{},
		}
	}
	statusOf := map[string]string{}
	for _, kpi := range report.KPIs {
		statusOf[kpi.ID] = kpi.Status
	}
	result := statusResult{
		Schema: "easycirq-sch-status/v1", Verdict: report.Verdict,
		Project: report.Project, Page: report.Page,
		Blockers: []statusEntry{}, Missing: []statusEntry{},
	}
	for _, blocker := range report.Blockers {
		entry := statusEntry{KPI: blocker.KPI, Plain: plainFor(blocker.KPI), Reason: blocker.Reason}
		if s := statusOf[blocker.KPI]; s == "missing" || s == "unknown" {
			result.Missing = append(result.Missing, entry)
		} else {
			result.Blockers = append(result.Blockers, entry)
		}
	}
	unmeasured := 0
	for _, kpi := range report.KPIs {
		if !kpi.Advisory && (kpi.Status == "missing" || kpi.Status == "unknown") {
			unmeasured++
		}
	}
	switch {
	case strings.EqualFold(report.Verdict, "PASS") && unmeasured > 0:
		// a PASS verdict with an unmeasured check is not a pass: the card has
		// to say what is missing, never "ready"
		result.State, result.Headline = "incomplete", "还不能判断：有些检查还没做"
		result.Next = "补齐下面这些检查需要的资料，再跑一轮"
	case strings.EqualFold(report.Verdict, "PASS") && !report.Stability.ApplyAllowed:
		result.State, result.Headline = "gate_stale", "检查通过，但还没拿到写入许可"
		result.Next = "连续两轮通过后才会获得许可；再跑一轮即可"
	case strings.EqualFold(report.Verdict, "BLOCKED") && len(result.Blockers) > 0:
		result.State, result.Headline = "blocked", "暂时不能写入：还有必须修掉的问题"
		result.Next = "按下面的清单逐条修，修完重新测量；修完之前不要画图"
	case strings.EqualFold(report.Verdict, "BLOCKED"):
		result.State, result.Headline = "incomplete", "还不能判断：有些检查还没做"
		result.Next = "补齐下面这些检查需要的资料，再跑一轮"
	case strings.EqualFold(report.Verdict, "REVIEW"):
		result.State, result.Headline = "review", "可以写入，但有几项软指标没达标"
		result.Next = "确认这些提醒项可接受后继续；否则先调整再测"
	default:
		if live, _ := gateLive(gatePath); live {
			result.State, result.Headline = "ready_to_write", "检查通过，可以写入图纸了"
			result.Next = "执行写入；写完保存、重开、回读，再跑一次检查"
		} else {
			// "通行证" is our internal name for the write permission; say what it
			// means for the customer instead.
			result.State, result.Headline = "gate_stale", "检查通过了，但写入许可已失效"
			result.Next = "重新跑一轮检查即可重新获得写入许可"
		}
	}
	return result
}

func renderStatus(result statusResult) string {
	var b strings.Builder
	fmt.Fprintf(&b, "【%s】\n", result.Headline)
	if result.Project != "" {
		fmt.Fprintf(&b, "工程 %s / %s\n", result.Project, result.Page)
	}
	if len(result.Blockers) > 0 {
		b.WriteString("必须修的问题：\n")
		for _, entry := range result.Blockers {
			fmt.Fprintf(&b, "  - %s\n", entry.Plain)
			if entry.Reason != "" {
				fmt.Fprintf(&b, "    %s\n", entry.Reason)
			}
		}
	}
	if len(result.Missing) > 0 {
		b.WriteString("还没检查的项目（补上资料即可）：\n")
		for _, entry := range result.Missing {
			fmt.Fprintf(&b, "  - %s\n", entry.Plain)
		}
	}
	fmt.Fprintf(&b, "下一步：%s", result.Next)
	return b.String()
}

// ── status ────────────────────────────────────────────────────────────────

func newStatusCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var kpiReport, gate string
	var asJSON bool
	c := &cobra.Command{
		Use:   "status",
		Short: "One line: where this board stands and what the next step is",
		Long: `Reads the last offline KPI report (and the write permission) and prints one
state plus one next action, in plain language. It never talks to EDA and never
re-runs a check: a missing input simply means that state was not reached.

States: not_measured | blocked | incomplete | review | ready_to_write | gate_stale

Exit codes: 0 ready to write, 1 blocked/review, 2 not measured or invalid.`,
		Args: cobra.NoArgs,
		Example: `  easycirq status
  easycirq status --kpi-report reports/p1/kpi-report.json
  easycirq status --json`,
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
			result := analyzeStatus(report, gatePath)
			if asJSON {
				raw, _ := json.MarshalIndent(result, "", "  ")
				fmt.Fprintln(stdout, string(raw))
			} else {
				fmt.Fprintln(stdout, renderStatus(result))
			}
			switch result.State {
			case "ready_to_write":
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
		"write permission file (default .easycirq/gate.json)")
	c.Flags().BoolVar(&asJSON, "json", false, "print JSON")
	return c
}
