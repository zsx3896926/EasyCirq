package app

// cmd_enterprise.go — the 企业知识库 subcommand group.
//
// Why this exists: every enterprise capability already works, but each one is a
// Python script the customer has to invoke as `python easycirq/scripts/xxx.py`.
// That is the wrong thing to hand a company: it says "this product is a pile of
// scripts", and it makes the customer learn where the skill dir lives.
//
// The checks themselves stay in Python — 315 scripts already exist, they are
// tested, and rewriting them in Go would be a rewrite, not an improvement. This
// is a thin, self-describing shell over them, so the surface a customer learns
// is `easycirq enterprise ...` and nothing else.
//
// Every subcommand here is a pass-through: it resolves the script through the
// same skill-asset ladder bom-enrich.py uses, runs it with the shared Python
// resolver, and forwards the exit code. No logic is duplicated.

import (
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"

	"github.com/spf13/cobra"
)

// enterpriseScript names one helper script under the skill's scripts/ dir.
type enterpriseScript struct {
	name string
	desc string
}

// The scripts this group wraps. Keep this list in step with what actually ships;
// a name here that is not in the package is a broken command, and
// TestEnterpriseScriptsShip catches it.
var (
	scriptRules    = enterpriseScript{"enterprise_rules.py", "企业规则检查"}
	scriptReview   = enterpriseScript{"enterprise_review.py", "审阅报告"}
	scriptSelfChk  = enterpriseScript{"enterprise_selfcheck.py", "知识库健康检查"}
	scriptLedger   = enterpriseScript{"review_ledger.py", "人审记录"}
	scriptKnowlg   = enterpriseScript{"enterprise_kb.py", "知识库浏览与导出"}
	scriptKnowSrch = enterpriseScript{"knowledge_search.py", "知识检索"}
	scriptParts    = enterpriseScript{"enterprise_parts.py", "企业器件参数"}
)

// resolveEnterpriseScript finds a helper script through the shared skill ladder.
func resolveEnterpriseScript(script enterpriseScript) (string, error) {
	asset := skillAsset{
		name: script.name,
		rels: []string{
			"easycirq/scripts/" + script.name,
			"easycirq-agent/scripts/" + script.name,
		},
		searchPath: false,
		flagHint:   "--script",
	}
	return asset.resolve("")
}

// runEnterpriseScript shells out to a helper and forwards its exit code.
//
// stdin/stdout/stderr pass straight through: these scripts print human-facing
// text (cards, tables, HTML paths) and their own errors, so wrapping the output
// would only lose information.
func runEnterpriseScript(script enterpriseScript, args []string,
	stdout, stderr io.Writer) error {
	path, err := resolveEnterpriseScript(script)
	if err != nil {
		return fmt.Errorf("%w\n脚本名: %s（应在技能目录的 scripts/ 下）",
			err, script.name)
	}
	py, err := pythonCommand(path, args...)
	if err != nil {
		return err
	}
	py.Stdin = os.Stdin
	py.Stdout = stdout
	py.Stderr = stderr
	if err := py.Run(); err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			// 脚本已经用自己的话解释过原因，别再套一层
			return errActionFailed
		}
		return fmt.Errorf("%s: %w", script.name, err)
	}
	return nil
}

// newEnterpriseCmd returns the "enterprise" command group.
func newEnterpriseCmd(stdout, stderr io.Writer) *cobra.Command {
	c := &cobra.Command{
		Use:   "enterprise",
		Short: "企业知识库：把公司规范/实测参数/人审经验接进来",
		Long: "企业把自己的规范、器件实测参数、标准电路和人审经验放进知识目录，" +
			"不改源码、不重装，下一次检查就生效。\n\n" +
			"知识目录默认 ~/.easycirq/knowledge/，可用 EASYCIRQ_KNOWLEDGE_DIR 指定" +
			"（企业部署时通常指向共享目录，全员共用一份）。\n\n" +
			"  easycirq enterprise ls            看库里有什么\n" +
			"  easycirq enterprise show <id>     看某一条的全文\n" +
			"  easycirq enterprise check         按企业规则查一块板\n" +
			"  easycirq enterprise review        一份给人看的审阅结论\n" +
			"  easycirq enterprise audit         库健康检查（哪些条目不会生效）\n" +
			"  easycirq enterprise doctor        环境自检（目录、写权限）\n" +
			"  easycirq enterprise report        导出可分享的 HTML 报告\n" +
			"  easycirq enterprise promote       把人审记录写进企业规则\n" +
			"  easycirq enterprise parts         企业器件参数 / 查内置键\n" +
			"  easycirq enterprise search        按板子检索企业知识\n\n" +
			"规则能拦住交付；知识只做提示，永远不影响结论。",
	}
	c.AddCommand(
		newEnterpriseLsCmd(stdout, stderr),
		newEnterpriseShowCmd(stdout, stderr),
		newEnterpriseCheckCmd(stdout, stderr),
		newEnterpriseReviewCmd(stdout, stderr),
		newEnterpriseAuditCmd(stdout, stderr),
		newEnterpriseReportCmd(stdout, stderr),
		newEnterprisePromoteCmd(stdout, stderr),
		newEnterprisePartsCmd(stdout, stderr),
		newEnterpriseSearchCmd(stdout, stderr),
		newEnterpriseHarvestCmd(stdout, stderr),
		newEnterpriseDoctorCmd(stdout, stderr),
	)
	return c
}

// passThrough builds a subcommand that forwards every argument it does not
// consume to the helper script. Flags are pass-through on purpose: the scripts
// own their own flags, and duplicating them here would drift.
func passThrough(use, short, long string, script enterpriseScript,
	stdout, stderr io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:                use,
		Short:              short,
		Long:               long,
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			return runEnterpriseScript(script, args, stdout, stderr)
		},
	}
}

func newEnterpriseLsCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("ls", "看库里有什么（规则/知识/器件）",
		"列出企业知识库的三类条目，并标出不会生效的。\n\n"+
			"  easycirq enterprise ls\n"+
			"  easycirq enterprise ls --json",
		scriptKnowlg, stdout, stderr)
}

func newEnterpriseShowCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("show <id>", "看某一条的全文",
		"打印一条规则、知识或器件参数的完整 JSON。\n\n"+
			"  easycirq enterprise show no-0402\n"+
			"  easycirq enterprise show mosfet.ao3400a_sot23",
		scriptKnowlg, stdout, stderr)
}

func newEnterpriseCheckCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("check --netlist <list.json>", "按企业规则查一块板",
		"对导出网表跑企业规则。退出码 0 通过 / 1 违反 hard 规则 / 2 有规则判不了。\n\n"+
			"  easycirq enterprise check --netlist board.json\n"+
			"  easycirq enterprise check --netlist board.json --describe",
		scriptRules, stdout, stderr)
}

func newEnterpriseReviewCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("review --netlist <list.json>", "一份给人看的审阅结论",
		"规则决定能不能交付，知识只做提示。违反时给出依据条款和找人。\n\n"+
			"  easycirq enterprise review --netlist board.json --intent intent.json",
		scriptReview, stdout, stderr)
}

func newEnterpriseAuditCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("audit", "库健康检查：哪些条目不会生效",
		"检查读不进来的文件、没有 verified_on 的规则、永远检索不到的知识。\n\n"+
			"  easycirq enterprise audit",
		scriptSelfChk, stdout, stderr)
}

func newEnterpriseReportCmd(stdout, stderr io.Writer) *cobra.Command {
	c := &cobra.Command{
		Use:   "report --html-out <kb.html>",
		Short: "导出可分享的 HTML 报告",
		Long: "生成自包含 HTML（不依赖网络），可放内网共享、直接分发。\n\n" +
			"  easycirq enterprise report --html-out kb.html\n" +
			"  easycirq enterprise report --html-out kb.html --title \"公司规范库\"",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			// 没给输出路径时脚本会退化成"列条目"，那不是 report 该干的事。
			//
			// 两个名字都要认：`--out` 是目标与文档里写的那个，
			// `--html-out` 是更早的写法。2026-11-03 实测发现只认后者，
			// 于是文档里的 `--out` 直接失败——文档承诺了实现没做的事。
			hasOut := false
			for _, a := range args {
				if a == "--out" || strings.HasPrefix(a, "--out=") ||
					a == "--html-out" || strings.HasPrefix(a, "--html-out=") {
					hasOut = true
					break
				}
			}
			if !hasOut {
				return fmt.Errorf("report 需要 --out <路径>：\n" +
					"  easycirq enterprise report --out kb.html\n" +
					"（只想看库里有什么，用 easycirq enterprise ls）")
			}
			return runEnterpriseScript(scriptKnowlg, args, stdout, stderr)
		},
	}
	return c
}

func newEnterprisePromoteCmd(stdout, stderr io.Writer) *cobra.Command {
	// 这里不能用 passThrough：脚本的默认动作是"列出来"，推进要显式 --promote。
	// 子命令叫 promote 却打出清单，是 2026-11-03 实测发现的真问题——
	// 客户会以为已经推进了，实际上一条都没写进去。
	c := &cobra.Command{
		Use:   "promote --ledger <ledger.json>",
		Short: "把人审记录写进企业规则",
		Long: "把 disposition=rule 的条目推进企业知识目录，并回读确认真的能加载。\n\n" +
			"  easycirq enterprise promote --ledger ledger.json\n" +
			"  easycirq enterprise promote --ledger ledger.json --dry-run",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			full := append([]string{"--promote"}, args...)
			return runEnterpriseScript(scriptLedger, full, stdout, stderr)
		},
	}
	return c
}

func newEnterprisePartsCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("parts", "企业器件参数",
		"查企业器件库，或列出内置标准件的键（要覆盖某个内置器件时先查它的键）。\n\n"+
			"  easycirq enterprise parts --list-builtin --filter mosfet\n"+
			"  easycirq enterprise parts --resolve mosfet.ao3400a_sot23",
		scriptParts, stdout, stderr)
}

func newEnterpriseSearchCmd(stdout, stderr io.Writer) *cobra.Command {
	return passThrough("search --netlist <list.json>", "按板子检索企业知识",
		"把这块板的相关知识检索出来，每条说明命中了什么。\n\n"+
			"  easycirq enterprise search --netlist board.json --intent intent.json\n"+
			"  easycirq enterprise search --audit",
		scriptKnowSrch, stdout, stderr)
}

// newEnterpriseHarvestCmd: 从历史 DRC 报告里聚类出**候选**规则。
//
// 它不是"自动生成规则"：候选里故意不带 disposition，所以 promote 会拒绝。
// "这算不算公司规范"必须由人写明——这正是人审不可绕过的那条纪律。
func newEnterpriseHarvestCmd(stdout, stderr io.Writer) *cobra.Command {
	c := &cobra.Command{
		Use:   "harvest",
		Short: "从历史工程的 DRC 报告里聚类出候选规则（必须人审）",
		Long: "把一批 DRC 报告聚类，回答三个问题：\n\n" +
			"  · 哪几类问题反复出现，各多少次\n" +
			"  · **哪一类能变成可执行规则**，哪一类不能、为什么\n" +
			"  · 能变的那些，产出 review-ledger 形状的**候选**\n\n" +
			"  easycirq enterprise harvest --drc <报告或目录> [--dump dump.json]\n" +
			"  easycirq enterprise harvest --drc ../retrocam-02/pcb --dump ../retrocam-02/pcb/dump2.json --out cand.json\n\n" +
			"**候选不是规则**：输出里没有 disposition，`enterprise promote` 会当场拒绝。\n" +
			"原因是判错两边都致命——判成规则会拿常识去拦板，判成知识则永远拦不住东西。\n\n" +
			"**一条必须知道的事实**：DRC 的两类违规都不直接对应现有谓词。\n" +
			"  Connection Error = 开路/未布通（这块板没做完，不是规范）\n" +
			"  Clearance Error  = 几何间距（现有 4 个谓词全是网表级，没有几何谓词）\n" +
			"所以真正能变成规则的只有一条间接路径：某器件在违规里反复出现 ⇒ 提 part_forbidden。\n" +
			"那需要 --dump 才补得上型号；没有 dump 就只报位号、不出候选。",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			return runEnterpriseScript(enterpriseScript{
				name: "enterprise_harvest.py",
			}, args, stdout, stderr)
		},
	}
	return c
}
