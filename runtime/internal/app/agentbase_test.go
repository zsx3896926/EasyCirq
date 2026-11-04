package app

// agentbase_test.go — login 之后 Agent 该指向哪里。

import (
	"os"
	"strings"
	"testing"
)

// login 必须把 Agent 的 base_url 落定成本机代理地址。
//
// 这不是"顺手打印一句"：指向服务器地址就得把 token 写进 Agent 的配置文件，
// 而这类文件经常被截图、贴群、提交到仓库。回环地址里没有任何凭据。
func TestLoginPinsAgentBaseURLToLocalProxy(t *testing.T) {
	withCredFile(t)
	if _, err := saveCredentials(Credentials{
		Server:       "https://easycirq.company.com",
		Token:        "tok",
		Engineer:     "张工",
		AgentBaseURL: defaultAgentBaseURL,
	}); err != nil {
		t.Fatal(err)
	}
	cred, remote, err := loadCredentials()
	if err != nil || !remote {
		t.Fatalf("读凭据失败：%v remote=%v", err, remote)
	}
	if cred.AgentBaseURL != "http://127.0.0.1:23190/v1" {
		t.Fatalf("Agent base_url 应为本机代理，实际 %q", cred.AgentBaseURL)
	}
	// 关键：这个地址里不许出现 token 或服务器主机名
	for _, bad := range []string{"tok", "easycirq.company.com", "sk-"} {
		if strings.Contains(cred.AgentBaseURL, bad) {
			t.Fatalf("base_url 里带了不该带的东西 %q：%s", bad, cred.AgentBaseURL)
		}
	}
}

// 老凭据文件（没有 agentBaseUrl 字段）读出来要自动补默认值，
// 不用让人重新登录。
func TestOldCredentialsGainDefaultAgentBaseURL(t *testing.T) {
	path := withCredFile(t)
	if err := os.WriteFile(path, []byte(`{"server":"https://h","token":"t"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	cred, remote, err := loadCredentials()
	if err != nil || !remote {
		t.Fatalf("老凭据读不出来：%v", err)
	}
	if cred.AgentBaseURL != defaultAgentBaseURL {
		t.Fatalf("老凭据没补上默认 base_url，实际 %q", cred.AgentBaseURL)
	}
}

// status 要把 base_url 显示出来，否则人不知道 Agent 该配什么。
func TestLoginStatusShowsAgentBaseURL(t *testing.T) {
	withCredFile(t)
	if _, err := saveCredentials(Credentials{
		Server:       "https://h",
		Token:        "tok",
		AgentBaseURL: defaultAgentBaseURL,
	}); err != nil {
		t.Fatal(err)
	}
	var out strings.Builder
	// 服务器不可达也会走到打印 base_url 那一步
	_ = printLoginStatus(&out)
	if !strings.Contains(out.String(), "http://127.0.0.1:23190/v1") {
		t.Fatalf("status 没显示 Agent base_url：%s", out.String())
	}
}
