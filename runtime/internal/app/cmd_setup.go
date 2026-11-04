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

// setupLine is one row of the first-run checklist.
type setupLine struct {
	Label string
	OK    bool
	State string
	// Optional marks a line that is an add-on, not a requirement. When an
	// optional line is not OK it renders as "-" rather than "✗", because a
	// company that never configured a knowledge base has not done anything
	// wrong — it has just not started. Rendering that as a failure would train
	// people to ignore the marks, which is the opposite of the point.
	Optional bool
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
	lines := []setupLine{{Label: "软件", OK: true,
		State: strings.TrimSpace(rep.Runtime.Name + " " + rep.Runtime.Version)}}

	daemonOK := strings.EqualFold(rep.Daemon.Status, "running")
	daemonState := zhState(rep.Daemon.Status,
		map[string]string{"running": "运行中", "stopped": "未运行"}, "未知")
	if daemonOK && rep.Daemon.Port > 0 {
		daemonState = "运行中"
	}
	lines = append(lines, setupLine{Label: "后台运行", OK: daemonOK, State: daemonState})

	connectorOK := strings.EqualFold(rep.Connector.Status, "connected")
	connectorState := zhState(rep.Connector.Status,
		map[string]string{"connected": "已连接", "disconnected": "未连接"}, "未知")
	if connectorOK {
		connectorState = "已连接"
		if rep.Host.EasyEDAVersion != "" {
			connectorState += "（EasyEDA Pro " + rep.Host.EasyEDAVersion + "）"
		}
	}
	lines = append(lines, setupLine{Label: "EasyEDA", OK: connectorOK, State: connectorState})

	skillOK := strings.EqualFold(rep.Skill.Status, "installed")
	lines = append(lines, setupLine{Label: "技能", OK: skillOK,
		State: zhState(rep.Skill.Status,
			map[string]string{"installed": "已装入", "missing": "未装入", "unknown": "未知"}, "未知")})
	lines = append(lines, enterpriseKnowledgeLine())
	return lines
}

// enterpriseKnowledgeLine reports whether a company knowledge library is
// configured, without parsing it.
//
// Why not parse here: the loading rules (which files count, what a valid schema
// is, which entries are dead) live in Python and are already tested. Duplicating
// a weaker version in Go would let the two disagree, and the Go one would be the
// one the customer sees first. This line answers "is there a library and did the
// path resolve", and points at `easycirq enterprise ls` for the rest.
//
// The three outcomes are deliberately distinct:
//   - a directory with files            -> configured
//   - the default directory absent      -> not configured (optional, "-")
//   - a directory the user SET is absent -> wrong path, and it says which one
//
// The last case matters most: someone who set EASYCIRQ_KNOWLEDGE_DIR and got it
// wrong would otherwise believe the company library is in effect.
func enterpriseKnowledgeLine() setupLine {
	home, err := os.UserHomeDir()
	if err != nil {
		return setupLine{Label: "企业知识库", Optional: true, State: "无法确定用户目录"}
	}
	return enterpriseKnowledgeState(os.Getenv("EASYCIRQ_KNOWLEDGE_DIR"), home)
}

// enterpriseKnowledgeState is the testable core: env and home are injected so
// the three outcomes can be asserted without touching the real user profile.
func enterpriseKnowledgeState(rawEnv, home string) setupLine {
	env := strings.TrimSpace(rawEnv)
	dir := env
	explicit := env != ""
	if dir == "" {
		dir = filepath.Join(home, ".easycirq", "knowledge")
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		if explicit {
			// 配了但路径不对——这是真问题，要让人看见配的是哪一条
			return setupLine{Label: "企业知识库", Optional: false,
				State: "目录不存在：" + dir}
		}
		return setupLine{Label: "企业知识库", Optional: true,
			State: "未配置（可选；运行 easycirq enterprise ls 了解怎么开始）"}
	}

	files := 0
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(strings.ToLower(e.Name()), ".json") {
			files++
		}
	}
	if files == 0 {
		if explicit {
			return setupLine{Label: "企业知识库", Optional: false,
				State: "目录里没有 .json：" + dir}
		}
		return setupLine{Label: "企业知识库", Optional: true,
			State: "空库（" + dir + "）"}
	}
	return setupLine{Label: "企业知识库", OK: true,
		State: fmt.Sprintf("%d 个文件（%s）", files, dir)}
}

func renderSetup(rep doctorReport, out io.Writer) {
	fmt.Fprintln(out, "EasyCirq 安装检查")
	fmt.Fprintln(out)
	for _, line := range setupLines(rep) {
		mark := "✓"
		if !line.OK {
			mark = "✗"
			if line.Optional {
				mark = "-"
			}
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
		Args:    cobra.NoArgs,
		Example: `  easycirq setup`,
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
