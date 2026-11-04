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

// acceptanceCheck is one thing a person measured on the physical board.
// A result without evidence is "unknown", never a pass: hardware acceptance is
// the third evidence level and must not borrow the schematic's verdict.
type acceptanceCheck struct {
	ID       string `json:"id"`
	Title    string `json:"title"`
	Result   string `json:"result"` // pass | fail | unknown
	Evidence string `json:"evidence"`
	By       string `json:"by,omitempty"`
}

type acceptanceFile struct {
	Schema  string           `json:"schema"`
	Project string           `json:"project"`
	Page    string           `json:"page"`
	Board   string           `json:"board"`
	Checks  []acceptanceCheck `json:"checks"`
}

type acceptanceLine struct {
	Title    string `json:"title"`
	Result   string `json:"result"`
	Evidence string `json:"evidence,omitempty"`
	Why      string `json:"why,omitempty"`
}

type acceptanceResult struct {
	Schema   string           `json:"schema"`
	State    string           `json:"state"`
	Headline string           `json:"headline"`
	Next     string           `json:"next"`
	Lines    []acceptanceLine `json:"lines"`
	Project  string           `json:"project,omitempty"`
	Board    string           `json:"board,omitempty"`
}

// requiredAcceptance lists the three things a board must prove before a
// customer can call it working. Missing ones are reported, not assumed.
var requiredAcceptance = []struct{ id, title string }{
	{"solder", "焊接"},
	{"power", "上电"},
	{"function", "功能"},
}

func analyzeAcceptance(data *acceptanceFile) acceptanceResult {
	result := acceptanceResult{Schema: "easycirq-sch-acceptance/v1",
		Lines: []acceptanceLine{}}
	if data == nil {
		result.State, result.Headline = "missing", "⏳ 还没有验收记录"
		result.Next = "打样回来后，把焊接、上电、功能三项的实测结果填进 .easycirq/acceptance.json"
		return result
	}
	result.Project, result.Board = data.Project, data.Board

	seen := map[string]bool{}
	unknownCount, failCount, passCount := 0, 0, 0
	for _, check := range data.Checks {
		line := acceptanceLine{Title: check.Title, Result: check.Result, Evidence: check.Evidence}
		if line.Title == "" {
			line.Title = check.ID
		}
		seen[check.ID] = true
		switch {
		case strings.EqualFold(check.Result, "pass") && strings.TrimSpace(check.Evidence) == "":
			line.Result, line.Why = "unknown", "写了通过但没有实测证据"
			unknownCount++
		case strings.EqualFold(check.Result, "pass"):
			passCount++
		case strings.EqualFold(check.Result, "fail"):
			if line.Why == "" {
				line.Why = "实测未通过"
			}
			failCount++
		default:
			line.Result = "unknown"
			// Say what the accepted values are: a customer who typed "ok" has no
			// way to know the vocabulary is pass / fail / unknown.
			line.Why = fmt.Sprintf("结论只能填 pass、fail 或 unknown，你填的是 %q", strings.TrimSpace(check.Result))
			unknownCount++
		}
		result.Lines = append(result.Lines, line)
	}
	for _, required := range requiredAcceptance {
		if seen[required.id] {
			continue
		}
		result.Lines = append(result.Lines, acceptanceLine{
			Title: required.title, Result: "unknown", Why: "还没记录这一项"})
		unknownCount++
	}

	switch {
	case failCount > 0:
		result.State, result.Headline = "failed", "❌ 这块板还不能算可用"
		result.Next = "按上面的失败项返修或换件，修完重新验一遍"
	case unknownCount > 0:
		result.State, result.Headline = "pending", "⏳ 还差实测证据"
		result.Next = "补齐上面标注的实测记录（谁测的、测到什么值），再跑一次 easycirq acceptance"
	default:
		result.State, result.Headline = "accepted", "✅ 这块板可以交付使用"
		result.Next = "把这张卡和实测记录一起归档；有问题照上面的证据追溯"
	}
	_ = passCount
	return result
}

func renderAcceptance(result acceptanceResult) string {
	var b strings.Builder
	b.WriteString(result.Headline + "\n\n")
	if result.Board != "" || result.Project != "" {
		fmt.Fprintf(&b, "工程 %s  板号 %s\n\n", result.Project, result.Board)
	}
	mark := map[string]string{"pass": "✓", "fail": "✗", "unknown": "?"}
	for _, line := range result.Lines {
		fmt.Fprintf(&b, "  %s %-8s %s\n", mark[line.Result], line.Title, line.Evidence)
		if line.Why != "" {
			fmt.Fprintf(&b, "      %s\n", line.Why)
		}
	}
	fmt.Fprintf(&b, "\n下一步：%s", result.Next)
	return b.String()
}

// ── acceptance ────────────────────────────────────────────────────────────

func newAcceptanceCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var path string
	var asJSON bool
	c := &cobra.Command{
		Use:   "acceptance",
		Short: "Post-prototype acceptance card: is the physical board working",
		Long: `Reads the acceptance record you filled in after the board came back and prints
one card: solder, power, function. A "pass" without measured evidence is treated
as unknown, never as a pass — hardware acceptance is the third evidence level and
must not borrow the schematic's or the EDA session's verdict.

Record format (.easycirq/acceptance.json):
  {"schema":"easycirq-acceptance/v1","project":"...","board":"...",
   "checks":[{"id":"solder","title":"焊接","result":"pass",
              "evidence":"照片 IMG_001.jpg","by":"客户"}, ...]}

Exit codes: 0 accepted, 1 failed/pending, 2 no record or invalid.`,
		Args:    cobra.NoArgs,
		Example: `  easycirq acceptance\n  easycirq acceptance --file .easycirq/acceptance.json`,
		RunE: func(cmd *cobra.Command, args []string) error {
			recordPath := path
			if recordPath == "" {
				if cwd, err := os.Getwd(); err == nil {
					recordPath = filepath.Join(cwd, ".easycirq", "acceptance.json")
				}
			}
			var data *acceptanceFile
			if _, err := os.Stat(recordPath); err == nil {
				raw, err := os.ReadFile(recordPath)
				if err != nil {
					// A silent non-zero exit is not explainable: say which file
					// could not be read and what to do next.
					fmt.Fprintf(stdout, "⏳ 验收记录读不出来：%s\n\n下一步：确认这个文件存在且能打开，或把实测结果写到默认位置 .easycirq/acceptance.json\n", recordPath)
					return exitCodeError{code: 2}
				}
				var loaded acceptanceFile
				if err := json.Unmarshal(raw, &loaded); err != nil {
					firstLine := ""
					if idx := strings.IndexByte(string(raw), '\n'); idx >= 0 {
						firstLine = string(raw)[:idx]
					} else {
						firstLine = string(raw)
					}
					if len(firstLine) > 80 {
						firstLine = firstLine[:80] + "…"
					}
					fmt.Fprintf(stdout, "⏳ 验收记录的格式看不懂：%s\n\n它应该是一个 JSON 对象，包含 checks 数组（焊接/上电/功能，每项写 result 和 evidence）。\n看起来像：%s\n下一步：改正格式后重新运行 easycirq acceptance\n", recordPath, firstLine)
					return exitCodeError{code: 2}
				}
				data = &loaded
			}
			result := analyzeAcceptance(data)
			if asJSON {
				raw, _ := json.MarshalIndent(result, "", "  ")
				fmt.Fprintln(stdout, string(raw))
			} else {
				fmt.Fprintln(stdout, renderAcceptance(result))
			}
			switch result.State {
			case "accepted":
				return nil
			case "failed", "pending":
				return exitCodeError{code: 1}
			default:
				return exitCodeError{code: 2}
			}
		},
	}
	c.Flags().StringVar(&path, "file", "",
		"acceptance record (default .easycirq/acceptance.json)")
	c.Flags().BoolVar(&asJSON, "json", false, "print JSON")
	return c
}
