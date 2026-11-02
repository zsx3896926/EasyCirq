package blocks

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// 企业自建块：字段缺失、引用错位必须**拒绝加载**，而不是「能加载但用不了」。
//
// 2026-11-03 实测的缺陷：缺 ports / parts / internal_nets、甚至 port 指向不存在
// 的器件，`blocks ls` 全都正常显示、退出码 0。客户看到自己的块出现在列表里就
// 以为成了，真正 block-apply 时才炸。这一组把那些情况钉死。
func writeRaw(t *testing.T, dir, name, body string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, name), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func goodBody() map[string]any {
	return map[string]any{
		"id":       "block.company_good",
		"desc":     "一个完整的块",
		"category": "test",
		"author":   "@tester",
		"source":   "unit test",
		"parts": map[string]any{
			"R": map[string]any{"part": "res.10k_0402", "qty": 1},
		},
		"internal_nets": [][]string{{"R.1", "PORT:A"}, {"R.2", "PORT:B"}},
		"ports": map[string]any{
			"A": map[string]any{"dir": "in", "at": "R.1"},
			"B": map[string]any{"dir": "bidir", "at": "R.2"},
		},
	}
}

func loadWith(t *testing.T, body map[string]any) error {
	t.Helper()
	dir := t.TempDir()
	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	writeRaw(t, dir, "b.json", string(raw))
	t.Setenv("EASYCIRQ_BLOCKS_DIR", dir)
	_, err = Load()
	return err
}

func TestGoodExternalBlockLoads(t *testing.T) {
	if err := loadWith(t, goodBody()); err != nil {
		t.Fatalf("完整的块应当加载成功：%v", err)
	}
}

func TestMissingRequiredFieldIsRejected(t *testing.T) {
	for _, field := range []string{"desc", "category", "author", "source",
		"parts", "ports", "internal_nets"} {
		body := goodBody()
		delete(body, field)
		err := loadWith(t, body)
		if err == nil {
			t.Errorf("缺 %s 应当拒绝加载，实际通过了", field)
			continue
		}
		if !strings.Contains(err.Error(), field) {
			t.Errorf("缺 %s 的报错没点出字段名：%v", field, err)
		}
	}
}

func TestPortPointingAtUnknownPartIsRejected(t *testing.T) {
	body := goodBody()
	body["ports"] = map[string]any{
		"A": map[string]any{"dir": "in", "at": "GHOST.VIN"},
	}
	err := loadWith(t, body)
	if err == nil {
		t.Fatal("port 指向不存在的器件应当拒绝加载")
	}
	if !strings.Contains(err.Error(), "GHOST") {
		t.Errorf("报错要点出那个器件名：%v", err)
	}
}

func TestPortWithMalformedAtIsRejected(t *testing.T) {
	body := goodBody()
	body["ports"] = map[string]any{
		"A": map[string]any{"dir": "in", "at": "noDotHere"},
	}
	err := loadWith(t, body)
	if err == nil {
		t.Fatal("at 不是 <part>.<pin> 格式应当拒绝")
	}
}

func TestInternalNetReferencingUnknownPortIsRejected(t *testing.T) {
	body := goodBody()
	body["internal_nets"] = [][]string{{"R.1", "PORT:NOPE"}}
	err := loadWith(t, body)
	if err == nil {
		t.Fatal("internal_nets 引用不存在的 port 应当拒绝")
	}
	if !strings.Contains(err.Error(), "NOPE") {
		t.Errorf("报错要点出那个 port：%v", err)
	}
}

func TestInternalNetReferencingUnknownPartIsRejected(t *testing.T) {
	body := goodBody()
	body["internal_nets"] = [][]string{{"GHOST.1", "PORT:A"}}
	err := loadWith(t, body)
	if err == nil {
		t.Fatal("internal_nets 引用不存在的器件应当拒绝")
	}
}
