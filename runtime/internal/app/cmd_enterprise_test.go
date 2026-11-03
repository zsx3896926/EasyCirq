package app

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// `easycirq enterprise` 只是把 Python 脚本包一层。这一组钉三件事：
//   1. 组里每个子命令都能解析到真实脚本（否则是死命令）
//   2. 脚本找不到时的报错要说清探测了哪些路径、怎么修
//   3. 子命令不吞脚本自己的 flag
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

// 组里出现的每个脚本名都必须真的存在于仓库的 easycirq/scripts 下——
// 否则客户装完会得到"找不到脚本"的死命令。
func TestEnterpriseScriptsExistInRepo(t *testing.T) {
	repo, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	scripts := []enterpriseScript{
		scriptRules, scriptReview, scriptSelfChk, scriptLedger,
		scriptKnowlg, scriptKnowSrch, scriptParts,
	}
	for _, sc := range scripts {
		path := filepath.Join(repo, "easycirq", "scripts", sc.name)
		if _, err := os.Stat(path); err != nil {
			t.Errorf("脚本 %s 不在仓库的 easycirq/scripts 下：%v", sc.name, err)
		}
	}
}

// 找不到脚本时，报错必须列出探测过的路径并给出修法。
// 「能加载」的反面是「说清为什么没加载」——这是整个目标反复强调的那条线。
func TestMissingScriptErrorExplainsItself(t *testing.T) {
	sc := enterpriseScript{name: "definitely_not_a_real_script.py"}
	_, err := resolveEnterpriseScript(sc)
	if err == nil {
		t.Fatal("不存在的脚本居然解析成功了")
	}
	msg := err.Error()
	for _, want := range []string{"probed", "EASYCIRQ_SKILLS_DIR"} {
		if !strings.Contains(msg, want) {
			t.Errorf("报错里缺 %q：\n%s", want, msg)
		}
	}
	if !strings.Contains(msg, sc.name) {
		t.Errorf("报错没点出脚本名：\n%s", msg)
	}
}

// 脚本自己的 flag 不能被 cobra 吃掉：--netlist / --html-out 这些都归脚本管。
func TestEnterprisePassThroughDisablesFlagParsing(t *testing.T) {
	for _, name := range []string{"ls", "check", "report", "promote"} {
		cmd := passThrough(name, "s", "l",
			enterpriseScript{name: "x.py"},
			&strings.Builder{}, &strings.Builder{})
		if !cmd.DisableFlagParsing {
			t.Errorf("%s 没开 DisableFlagParsing，脚本的 flag 会被 cobra 吃掉", name)
		}
	}
}

// 组里的子命令必须真挂上（不是只有名字的空壳）。
func TestEnterpriseSubcommandsAreRunnable(t *testing.T) {
	root := newEnterpriseCmd(&strings.Builder{}, &strings.Builder{})
	for _, c := range root.Commands() {
		if c.RunE == nil && c.Run == nil {
			t.Errorf("子命令 %q 没有 Run，是个空壳", c.Name())
		}
	}
}
