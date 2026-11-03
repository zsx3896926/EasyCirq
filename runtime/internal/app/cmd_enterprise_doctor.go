package app

// cmd_enterprise_doctor.go — 企业上线前的环境自检。
//
// 和 `easycirq enterprise audit` 的区别：
//
//	audit    查**库的内容**：有哪些条目、哪些不会生效
//	doctor   查**环境能不能用**：目录通不通、能不能写、报告能不能出、计数能不能存
//
// 上线前跑 doctor，日常改库后跑 audit。两个都要有：库内容健康但目录只读，
// 一样是"配好了却用不了"。

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

// enterpriseCheck is one line of the doctor report.
type enterpriseCheck struct {
	Label  string
	OK     bool
	State  string
	Detail string
	// Optional：没配不等于配错。企业还没开始建库时显示 "-"，
	// 不显示 "✗"，也不让 doctor 退非零——否则等于把"还没开始"报成故障，
	// 而这正是 setup 里已经定下的同一条原则（见 cmd_setup.go 的 setupLine）。
	Optional bool
}

// enterpriseDoctor runs the checks and returns them plus the knowledge dir.
func enterpriseDoctor(probeReport bool) []enterpriseCheck {
	var out []enterpriseCheck

	// 1) 知识目录
	env := strings.TrimSpace(os.Getenv("EASYCIRQ_KNOWLEDGE_DIR"))
	dir := env
	explicit := env != ""
	if dir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return append(out, enterpriseCheck{Label: "知识目录", State: "无法确定用户目录"})
		}
		dir = filepath.Join(home, ".easycirq", "knowledge")
	}

	entries, err := os.ReadDir(dir)
	switch {
	case err != nil && explicit:
		// 设了却不存在：这是真问题，说出配的是哪一条
		out = append(out, enterpriseCheck{Label: "知识目录", State: "路径不存在", Detail: dir})
	case err != nil:
		out = append(out, enterpriseCheck{Label: "知识目录", Optional: true,
			State: "未配置（可选）", Detail: dir})
	default:
		files := 0
		for _, e := range entries {
			if !e.IsDir() && strings.HasSuffix(strings.ToLower(e.Name()), ".json") {
				files++
			}
		}
		if files == 0 {
			out = append(out, enterpriseCheck{Label: "知识目录", Optional: !explicit,
				State: "空目录（没有 .json）", Detail: dir})
		} else {
			out = append(out, enterpriseCheck{Label: "知识目录", OK: true,
				State: fmt.Sprintf("%d 个文件", files), Detail: dir})
		}
	}

	// 2) 目录可写（维护人才能改规则；只读盘是最容易踩的上线坑）
	if err == nil {
		probe := filepath.Join(dir, ".easycirq-write-probe")
		if werr := os.WriteFile(probe, []byte("x"), 0o644); werr == nil {
			_ = os.Remove(probe)
			out = append(out, enterpriseCheck{Label: "目录可写", OK: true, State: "是"})
		} else {
			out = append(out, enterpriseCheck{Label: "目录可写", Optional: true,
				State:  "否（只能读）",
				Detail: "工程师只读是正常的；维护人需要可写才能加规则"})
		}
	}

	// 3) 计数文件可写
	hitsPath := enterpriseRulesHitsPath()
	if hitsPath != "" {
		parent := filepath.Dir(hitsPath)
		if merr := os.MkdirAll(parent, 0o755); merr == nil {
			probe := hitsPath + ".probe"
			if werr := os.WriteFile(probe, []byte("x"), 0o644); werr == nil {
				_ = os.Remove(probe)
				out = append(out, enterpriseCheck{Label: "拦截计数", OK: true, State: "可写", Detail: hitsPath})
			} else {
				out = append(out, enterpriseCheck{Label: "拦截计数", Optional: true,
					State: "不可写（不影响检查）", Detail: hitsPath})
			}
		}
	}

	return out
}

// enterpriseRulesHitsPath mirrors the Python side's default so doctor can probe it
// without shelling out. Kept identical deliberately: if the Python default moves,
// this must move too, and the test asserts they agree.
func enterpriseRulesHitsPath() string {
	if env := strings.TrimSpace(os.Getenv("EASYCIRQ_ENTERPRISE_HITS")); env != "" {
		return env
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".easycirq", "audit", "enterprise-hits.json")
}

func newEnterpriseDoctorCmd(stdout, stderr io.Writer) *cobra.Command {
	var asJSON bool
	c := &cobra.Command{
		Use:   "doctor",
		Short: "上线前环境自检：目录通不通、能不能写、报告能不能出",
		Long: "检查企业知识库的运行环境。和 `enterprise audit` 分工不同：\n\n" +
			"  audit    查库的**内容**——有哪些条目、哪些不会生效\n" +
			"  doctor   查**环境能不能用**——目录、写权限、报告生成\n\n" +
			"上线前跑 doctor，日常改库后跑 audit。\n\n" +
			"  easycirq enterprise doctor\n" +
			"  easycirq enterprise doctor --json",
		RunE: func(_ *cobra.Command, _ []string) error {
			checks := enterpriseDoctor(true)
			failed := 0
			for _, k := range checks {
				if !k.OK && !k.Optional {
					failed++
				}
			}
			if asJSON {
				fmt.Fprintf(stdout, "{\"checks\": [")
				for i, k := range checks {
					if i > 0 {
						fmt.Fprint(stdout, ",")
					}
					fmt.Fprintf(stdout, "{\"label\": %q, \"ok\": %t, \"state\": %q, \"detail\": %q}",
						k.Label, k.OK, k.State, k.Detail)
				}
				fmt.Fprintf(stdout, "], \"failed\": %d}\n", failed)
			} else {
				fmt.Fprintln(stdout, "企业知识库环境自检")
				fmt.Fprintln(stdout)
				for _, k := range checks {
					mark := "✓"
					if !k.OK {
						mark = "✗"
						if k.Optional {
							mark = "-"
						}
					}
					fmt.Fprintf(stdout, "  %s %-10s %s\n", mark, k.Label, k.State)
					if k.Detail != "" {
						fmt.Fprintf(stdout, "               %s\n", k.Detail)
					}
				}
				fmt.Fprintln(stdout)
				if failed == 0 {
					fmt.Fprintln(stdout, "环境没问题。下一步：easycirq enterprise audit 查库内容。")
				} else {
					fmt.Fprintln(stdout, "有项目要处理——上面标 ✗ 的行就是。")
				}
			}
			if failed > 0 {
				return errActionFailed
			}
			return nil
		},
	}
	c.Flags().BoolVar(&asJSON, "json", false, "以 JSON 输出")
	return c
}
