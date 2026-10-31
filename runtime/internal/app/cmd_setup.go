package app

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"github.com/spf13/cobra"
)

// setupLine is one row of the first-run checklist.
type setupLine struct {
	Label string
	OK    bool
	State string
}

// zhState maps a raw status word to the customer-facing one; a status the
// customer has never seen (e.g. "installed") is not allowed to leak through.
func zhState(raw string, table map[string]string, fallback string) string {
	if text, ok := table[strings.ToLower(raw)]; ok {
		return text
	}
	if raw == "" {
		return fallback
	}
	return raw
}

// setupLines turns the doctor report into the four things a customer needs to
// know about their installation, in their own words.
func setupLines(rep doctorReport) []setupLine {
	lines := []setupLine{{Label: "运行时", OK: true,
		State: strings.TrimSpace(rep.Runtime.Name + " " + rep.Runtime.Version)}}

	daemonOK := strings.EqualFold(rep.Daemon.Status, "running")
	daemonState := zhState(rep.Daemon.Status,
		map[string]string{"running": "运行中", "stopped": "未运行"}, "未知")
	if daemonOK && rep.Daemon.Port > 0 {
		daemonState = fmt.Sprintf("运行中（端口 %d）", rep.Daemon.Port)
	}
	lines = append(lines, setupLine{Label: "后台服务", OK: daemonOK, State: daemonState})

	connectorOK := strings.EqualFold(rep.Connector.Status, "connected")
	connectorState := zhState(rep.Connector.Status,
		map[string]string{"connected": "已连接", "disconnected": "未连接"}, "未知")
	if connectorOK {
		connectorState = "已连接"
		if rep.Host.EasyEDAVersion != "" {
			connectorState += "（EasyEDA Pro " + rep.Host.EasyEDAVersion + "）"
		}
	}
	lines = append(lines, setupLine{Label: "EasyEDA 插件", OK: connectorOK, State: connectorState})

	skillOK := strings.EqualFold(rep.Skill.Status, "installed")
	lines = append(lines, setupLine{Label: "技能包", OK: skillOK,
		State: zhState(rep.Skill.Status,
			map[string]string{"installed": "已安装", "missing": "未安装", "unknown": "未知"}, "未知")})
	return lines
}

func renderSetup(rep doctorReport, out io.Writer) {
	fmt.Fprintln(out, "EasyCirq 安装检查")
	fmt.Fprintln(out)
	for _, line := range setupLines(rep) {
		mark := "✓"
		if !line.OK {
			mark = "✗"
		}
		fmt.Fprintf(out, "  %s %-14s %s\n", mark, line.Label, line.State)
	}
	fmt.Fprintln(out)
	if strings.EqualFold(rep.Verdict, "ok") {
		fmt.Fprintln(out, "一切就绪。下一步：说清你要做什么板子，或者运行 easycirq status 看当前状态。")
		return
	}
	fmt.Fprintln(out, "还差一步，按顺序做：")
	for index, step := range rep.NextSteps {
		fmt.Fprintf(out, "  %d. %s\n", index+1, step)
	}
	if len(rep.NextSteps) == 0 {
		fmt.Fprintln(out, "  重新运行 easycirq setup 查看最新状态。")
	}
	fmt.Fprintln(out)
	fmt.Fprintln(out, "做完再运行一次 easycirq setup，全部显示 ✓ 就可以开始了。")
}

// ── setup ─────────────────────────────────────────────────────────────────

func newSetupCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var asJSON bool
	c := &cobra.Command{
		Use:   "setup",
		Short: "First-run check: what is ready and what is the one next step",
		Long: `Reads the same evidence as doctor and prints a five-line checklist in plain
language, then the shortest path to a working installation. It never installs,
imports or restarts anything by itself: every step is printed for you to do,
because importing a connector and allowing external interaction must happen
inside EasyEDA.

Exit codes: 0 ready, 2 not ready.`,
		Args:      cobra.NoArgs,
		Example:   `  easycirq setup`,
		RunE: func(cmd *cobra.Command, args []string) error {
			rep := collectDoctorReport(cfg)
			if asJSON {
				raw, _ := json.MarshalIndent(rep, "", "  ")
				fmt.Fprintln(stdout, string(raw))
			} else {
				renderSetup(rep, stdout)
			}
			if strings.EqualFold(rep.Verdict, "ok") {
				return nil
			}
			return exitCodeError{code: 2}
		},
	}
	c.Flags().BoolVar(&asJSON, "json", false, "print the doctor report as JSON")
	return c
}
