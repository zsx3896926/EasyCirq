package app

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// doctor 查的是**环境能不能用**，和 audit 查库内容分工不同。
// 关键是三态分得清：配好了 / 没配（可选）/ 配错了，后者才该退非零。
func writeProbeJSON(t *testing.T, dir, name string) error {
	t.Helper()
	return os.WriteFile(filepath.Join(dir, name), []byte("{}"), 0o644)
}

func TestEnterpriseDoctorOptionalTristate(t *testing.T) {
	t.Setenv("EASYCIRQ_KNOWLEDGE_DIR", "")
	t.Setenv("EASYCIRQ_ENTERPRISE_HITS", "")
	checks := enterpriseDoctor(false)

	var kd *enterpriseCheck
	for i := range checks {
		if checks[i].Label == "知识目录" {
			kd = &checks[i]
		}
	}
	if kd == nil {
		t.Fatal("doctor 没有报知识目录")
	}
	if kd.OK {
		t.Fatalf("本机默认目录不存在或有文件，这条断言的场景没造出来：%+v", *kd)
	}
	if !kd.Optional {
		t.Error("没配知识库应当是可选（-），不是故障（✗）——和 setup 里同一条原则")
	}
}

func TestEnterpriseDoctorReportsConfiguredDir(t *testing.T) {
	dir := t.TempDir()
	if err := writeProbeJSON(t, dir, "rules.json"); err != nil {
		t.Fatal(err)
	}
	t.Setenv("EASYCIRQ_KNOWLEDGE_DIR", dir)
	t.Setenv("EASYCIRQ_ENTERPRISE_HITS", t.TempDir()+"/hits.json")
	checks := enterpriseDoctor(false)

	var ok bool
	for _, k := range checks {
		if k.Label == "知识目录" && k.OK && strings.Contains(k.State, "1 个文件") {
			ok = true
		}
	}
	if !ok {
		t.Fatalf("配好的目录没报成 OK：%+v", checks)
	}
}

// 设了环境变量但路径不存在 —— 这是**真问题**，必须非 Optional 且说出路径。
func TestEnterpriseDoctorWrongPathIsARealProblem(t *testing.T) {
	bad := t.TempDir() + "/nope"
	t.Setenv("EASYCIRQ_KNOWLEDGE_DIR", bad)
	t.Setenv("EASYCIRQ_ENTERPRISE_HITS", t.TempDir()+"/hits.json")
	checks := enterpriseDoctor(false)

	var kd *enterpriseCheck
	for i := range checks {
		if checks[i].Label == "知识目录" {
			kd = &checks[i]
		}
	}
	if kd == nil {
		t.Fatal("没有报知识目录")
	}
	if kd.OK || kd.Optional {
		t.Errorf("配错路径必须报成真问题（非 Optional），实际：%+v", *kd)
	}
	if !strings.Contains(kd.Detail, bad) {
		t.Errorf("要说出配的是哪个路径：%+v", *kd)
	}
}

// 计数文件路径必须和 Python 侧一致，否则 doctor 验的是一个地方、
// 检查运行时写的是另一个地方。
func TestEnterpriseDoctorHitsPathMatchesPythonDefault(t *testing.T) {
	t.Setenv("EASYCIRQ_ENTERPRISE_HITS", "")
	got := enterpriseRulesHitsPath()
	if !strings.HasSuffix(got, ".easycirq/audit/enterprise-hits.json") &&
		!strings.HasSuffix(got, `.easycirq\audit\enterprise-hits.json`) {
		t.Errorf("默认计数路径和 Python 侧不一致：%s", got)
	}
	// 显式设置要原样返回
	custom := t.TempDir() + "/custom-hits.json"
	t.Setenv("EASYCIRQ_ENTERPRISE_HITS", custom)
	if enterpriseRulesHitsPath() != custom {
		t.Errorf("显式路径没被尊重：%s", enterpriseRulesHitsPath())
	}
}

func TestEnterpriseDoctorRegistered(t *testing.T) {
	root := newEnterpriseCmd(&strings.Builder{}, &strings.Builder{})
	for _, c := range root.Commands() {
		if c.Name() == "doctor" {
			if c.RunE == nil {
				t.Error("doctor 没有 RunE")
			}
			return
		}
	}
	t.Error("enterprise 组里没有 doctor")
}
