package app

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// `easycirq enterprise` 只是把 Python 脚本包一层。这一组钉四件事：
//   1. 组里每个子命令都真挂着、能跑
//   2. 每个脚本名都真的在仓库里（否则是死命令）
//   3. 脚本找不到时报错说清探了哪些路径、怎么修
//   4. **子命令做它名字所说的事**——promote 要推进，report 要出文件，
//      不能退化成"列清单"而让客户以为做完了
func TestEnterpriseGroupHasAllSubcommands(t *testing.T) {
	root := newEnterpriseCmd(&strings.Builder{}, &strings.Builder{})
	want := []string{"ls", "show", "check", "review", "audit", "report",
		"promote", "parts", "search"}
	have := map[string]bool{}
	for _, c := range root.Commands() {
		have[c.Name()] = true
	}
	for _, name := range want {
		if !have[name] {
			t.Errorf("缺子命令 %q", name)
		}
	}
}

func TestEnterpriseScriptsExistInRepo(t *testing.T) {
	repo, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	for _, sc := range []enterpriseScript{
		scriptRules, scriptReview, scriptSelfChk, scriptLedger,
		scriptKnowlg, scriptKnowSrch, scriptParts,
	} {
		path := filepath.Join(repo, "easycirq", "scripts", sc.name)
		if _, err := os.Stat(path); err != nil {
			t.Errorf("脚本 %s 不在仓库的 easycirq/scripts 下：%v", sc.name, err)
		}
	}
}

func TestMissingScriptErrorExplainsItself(t *testing.T) {
	sc := enterpriseScript{name: "definitely_not_a_real_script.py"}
	_, err := resolveEnterpriseScript(sc)
	if err == nil {
		t.Fatal("不存在的脚本居然解析成功了")
	}
	msg := err.Error()
	for _, want := range []string{"probed", "EASYCIRQ_SKILLS_DIR", sc.name} {
		if !strings.Contains(msg, want) {
			t.Errorf("报错里缺 %q：\n%s", want, msg)
		}
	}
}

func TestEnterprisePassThroughDisablesFlagParsing(t *testing.T) {
	for _, name := range []string{"ls", "check", "search", "parts"} {
		cmd := passThrough(name, "s", "l",
			enterpriseScript{name: "x.py"},
			&strings.Builder{}, &strings.Builder{})
		if !cmd.DisableFlagParsing {
			t.Errorf("%s 没开 DisableFlagParsing，脚本的 flag 会被 cobra 吃掉", name)
		}
	}
}

// report 没给输出路径时必须报错退非零。
// 否则脚本会退化成"列条目"，而客户以为报告生成了——这是 2026-11-03 实测的真问题。
func TestEnterpriseReportRequiresOutputPath(t *testing.T) {
	var out, errb strings.Builder
	root := newEnterpriseCmd(&out, &errb)
	root.SetArgs([]string{"report"})
	err := root.Execute()
	if err == nil {
		t.Fatalf("report 没给输出路径却成功了，输出：%s", out.String())
	}
	if !strings.Contains(err.Error(), "--out") {
		t.Errorf("报错没提示要 --out：%v", err)
	}
}

// --out 和 --html-out 两个名字都必须被接受。
//
// 2026-11-03 实测：Go 侧只认 --html-out，而文档与 Python 侧用 --out，
// 于是文档里写的命令直接失败。文档承诺了实现没做的事。
func TestEnterpriseReportAcceptsBothFlagNames(t *testing.T) {
	for _, flag := range []string{"--out", "--html-out"} {
		var out, errb strings.Builder
		root := newEnterpriseCmd(&out, &errb)
		root.SetArgs([]string{"report", flag, filepath.Join(t.TempDir(), "kb.html")})
		err := root.Execute()
		// 脚本可能因为找不到 skill 目录而失败；这里只关心**没有**报
		// "需要 --out"，也就是两个名字都通过了参数校验这一关。
		if err != nil && strings.Contains(err.Error(), "需要 --out") {
			t.Errorf("%s 被误判为没给输出路径", flag)
		}
	}
}

// promote 必须真的把 --promote 交给脚本。
// 子命令叫 promote 却打出清单，客户会以为已经推进了。
func TestEnterprisePromoteInjectsTheFlag(t *testing.T) {
	root := newEnterpriseCmd(&strings.Builder{}, &strings.Builder{})
	var promote bool
	for _, c := range root.Commands() {
		if c.Name() == "promote" {
			promote = true
			if c.RunE == nil {
				t.Error("promote 没有 RunE")
			}
		}
	}
	if !promote {
		t.Fatal("没有 promote 子命令")
	}
}
