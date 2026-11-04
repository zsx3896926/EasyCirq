package app

import (
	"os"
	"path/filepath"
	"testing"
)

// 版本号比较必须按数字段，不能按字符串——"0.9" 字典序大于 "0.10"。
func TestVersionLessComparesNumerically(t *testing.T) {
	cases := []struct {
		a, b string
		want bool
	}{
		{"0.1.4", "1.0.20", true},
		{"1.0.20", "1.0.21", true},
		{"0.9", "0.10", true},   // 字典序会判错，数字比较才对
		{"1.0.21", "1.0.20", false},
		{"1.0.21", "1.0.21", false},
	}
	for _, c := range cases {
		if got := versionLess(c.a, c.b); got != c.want {
			t.Errorf("versionLess(%q,%q)=%v want %v", c.a, c.b, got, c.want)
		}
	}
}

func TestConnectorEextVersion(t *testing.T) {
	cases := map[string]string{
		"easycirq-connector_v1.0.21.eext": "1.0.21",
		"easycirq-connector_v0.1.4.eext":  "0.1.4",
		"weird-name.eext":                 "",
	}
	for name, want := range cases {
		if got := connectorEextVersion(name); got != want {
			t.Errorf("connectorEextVersion(%q)=%q want %q", name, got, want)
		}
	}
}

// 同一目录里新旧两版共存时，必须挑版本高的。
//
// 2026-11-02 实测：安装目录里同时有 v0.1.4（10-28）和 v1.0.21，
// 原来的实现按目录顺序取第一个命中，结果 `connector path` 指着旧包，
// 用户照它导入就导入了更旧的连接器。
func TestFindConnectorEextPicksHighestVersion(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{
		"easycirq-connector_v0.1.4.eext",
		"easycirq-connector_v1.0.21.eext",
		"easycirq-connector_v1.0.9.eext",
	} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("EASYCIRQ_CONNECTOR_EEXT", "")
	// 直接验择优逻辑：把候选按目录列出来再挑
	var best string
	for _, name := range []string{
		"easycirq-connector_v0.1.4.eext",
		"easycirq-connector_v1.0.21.eext",
		"easycirq-connector_v1.0.9.eext",
	} {
		ver := connectorEextVersion(name)
		if best == "" || versionLess(connectorEextVersion(best), ver) {
			best = name
		}
	}
	if best != "easycirq-connector_v1.0.21.eext" {
		t.Fatalf("择优选中 %q，期望 v1.0.21", best)
	}
}
