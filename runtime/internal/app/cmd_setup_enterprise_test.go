package app

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// setup 里的企业知识库那一行有三态，且**必须区分得清**：
//
//	目录有 json        -> ✓ 已配置
//	默认目录不存在      -> - 未配置（可选，不是故障）
//	**用户设了**但不存在 -> ✗ 配错了，并说出配的是哪个路径
//
// 最后一态最要紧：设了 EASYCIRQ_KNOWLEDGE_DIR 却写错路径的人，
// 会以为公司库已经生效。这正是"看起来配好了其实没配"。
func writeKBFile(t *testing.T, dir, name string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, name), []byte("{}"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestEnterpriseKnowledgeNotConfiguredIsOptionalNotFailure(t *testing.T) {
	home := t.TempDir() // 默认目录不存在
	line := enterpriseKnowledgeState("", home)
	if line.OK {
		t.Fatalf("未配置却报 OK：%+v", line)
	}
	if !line.Optional {
		t.Error("未配置应当是可选（渲染成 - 而不是 ✗），否则等于把「还没开始」报成故障")
	}
	if !strings.Contains(line.State, "未配置") {
		t.Errorf("措辞不对：%q", line.State)
	}
}

func TestEnterpriseKnowledgeConfiguredAtDefaultPath(t *testing.T) {
	home := t.TempDir()
	writeKBFile(t, filepath.Join(home, ".easycirq", "knowledge"), "rules.json")
	line := enterpriseKnowledgeState("", home)
	if !line.OK {
		t.Fatalf("默认路径有文件却报未配置：%+v", line)
	}
	if !strings.Contains(line.State, "1 个文件") {
		t.Errorf("没报文件数：%q", line.State)
	}
}

func TestEnterpriseKnowledgeExplicitPathWithFiles(t *testing.T) {
	dir := t.TempDir()
	writeKBFile(t, dir, "rules.json")
	writeKBFile(t, dir, "kb.json")
	line := enterpriseKnowledgeState(dir, t.TempDir())
	if !line.OK {
		t.Fatalf("显式路径有文件却报未配置：%+v", line)
	}
	if !strings.Contains(line.State, "2 个文件") || !strings.Contains(line.State, dir) {
		t.Errorf("应当同时报文件数和路径：%q", line.State)
	}
}

// 这是最重要的一条：设了环境变量但路径写错，必须显示成问题并说出路径。
func TestEnterpriseKnowledgeWrongExplicitPathIsAFailureNamingThePath(t *testing.T) {
	bad := filepath.Join(t.TempDir(), "nope")
	line := enterpriseKnowledgeState(bad, t.TempDir())
	if line.OK {
		t.Fatal("路径不存在却报 OK")
	}
	if line.Optional {
		t.Error("配错路径不能算「可选未配置」——那是真问题，要显示成 ✗")
	}
	if !strings.Contains(line.State, bad) {
		t.Errorf("必须说出配的是哪个路径：%q", line.State)
	}
}

func TestEnterpriseKnowledgeExplicitEmptyDirIsReported(t *testing.T) {
	dir := t.TempDir() // 存在但没有 json
	line := enterpriseKnowledgeState(dir, t.TempDir())
	if line.OK {
		t.Fatal("空目录不该报 OK")
	}
	if !strings.Contains(line.State, "没有 .json") {
		t.Errorf("空目录要说清原因：%q", line.State)
	}
}

// 非 .json 文件不算条目：目录里躺着 README 不代表库配好了。
func TestEnterpriseKnowledgeIgnoresNonJSONFiles(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "README.md"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	line := enterpriseKnowledgeState(dir, t.TempDir())
	if line.OK {
		t.Errorf("只有非 json 文件却报 OK：%+v", line)
	}
}

// setup 里那一行确实在列表里，且不影响 verdict（它是可选附加项）。
func TestSetupLinesIncludeEnterpriseKnowledge(t *testing.T) {
	var rep doctorReport
	lines := setupLines(rep)
	found := false
	for _, l := range lines {
		if l.Label == "企业知识库" {
			found = true
		}
	}
	if !found {
		t.Error("setup 里没有「企业知识库」这一行——客户装完就看不到这功能")
	}
}
