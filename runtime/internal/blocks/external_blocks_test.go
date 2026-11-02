package blocks

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// 企业块库：外部目录里的块必须被加载，同 id 覆盖内置。
//
// 存在的理由：块库是 go:embed 的，企业加块就得重编二进制。而企业自己的标准电路
// 恰恰是最该能自己加的东西。环境变量打开这条路径。
func writeBlock(t *testing.T, dir, name, id, desc string) string {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	body := `{"id":"` + id + `","desc":"` + desc + `","category":"test",
	  "parts":{"R":{"part":"res.10k_0402","qty":1}},
	  "internal_nets":[["R.1","PORT:A"],["R.2","PORT:B"]],
	  "ports":{"A":{"dir":"in","at":"R.1"},"B":{"dir":"bidir","at":"R.2"}}}`
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadPicksUpExternalBlocks(t *testing.T) {
	dir := t.TempDir()
	writeBlock(t, dir, "company_amp.json", "block.company_amp", "企业标准放大级")
	t.Setenv("EASYCIRQ_BLOCKS_DIR", dir)

	all, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	found := false
	for _, b := range all {
		if b.ID == "block.company_amp" {
			found = true
			if b.Desc != "企业标准放大级" {
				t.Errorf("desc = %q", b.Desc)
			}
		}
	}
	if !found {
		t.Fatalf("外部块没被加载，共 %d 个块", len(all))
	}
}

func TestExternalBlockOverridesSameID(t *testing.T) {
	dir := t.TempDir()
	// 用一个真实存在的内置块 id 覆盖它
	builtin, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(builtin) == 0 {
		t.Skip("没有内置块可覆盖")
	}
	target := builtin[0].ID
	writeBlock(t, dir, "override.json", target, "企业改过的版本")
	t.Setenv("EASYCIRQ_BLOCKS_DIR", dir)

	all, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	var hits []Block
	for _, b := range all {
		if b.ID == target {
			hits = append(hits, b)
		}
	}
	if len(hits) != 1 {
		t.Fatalf("覆盖后应只剩 1 条，实际 %d 条", len(hits))
	}
	if hits[0].Desc != "企业改过的版本" {
		t.Fatalf("覆盖没生效：desc = %q", hits[0].Desc)
	}
}

func TestMalformedExternalBlockFailsLoudly(t *testing.T) {
	dir := t.TempDir()
	bad := filepath.Join(dir, "bad.json")
	if err := os.WriteFile(bad, []byte(`{"id":""}`), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("EASYCIRQ_BLOCKS_DIR", dir)

	_, err := Load()
	if err == nil {
		t.Fatal("坏的块必须报错，不许静默跳过")
	}
	if !strings.Contains(err.Error(), "bad.json") {
		t.Fatalf("错误必须点出文件名，实际：%v", err)
	}
}

func TestNoEnvKeepsBuiltinBehaviour(t *testing.T) {
	t.Setenv("EASYCIRQ_BLOCKS_DIR", "")
	base, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	for _, b := range base {
		if strings.HasPrefix(b.ID, "block.company_") {
			t.Fatalf("没设环境变量却加载了外部块 %s", b.ID)
		}
	}
}
