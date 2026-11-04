package gateway

// llm_test.go — LLM 转发的验收。
//
// 这里证明的是**链路与边界**，不是"能调通某个真实模型"：
// 用假的 upstream 验证 key 从哪来、往哪送、会不会漏给客户端。
// 真实模型调用需要客户的 C1/C2 答复和内网 key，未做。

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// newLLMGateway 起一个启用 LLM 转发的 gateway，指向给定的 upstream。
func newLLMGateway(t *testing.T, baseURL, keyEnv string) (string, *bytes.Buffer) {
	t.Helper()
	var log bytes.Buffer
	gw := New(Options{
		Tokens: &TokenTable{Tokens: []Token{
			{Token: "tok-a", Engineer: "甲"},
			{Token: "tok-old", Engineer: "旧", Expires: "2020-01-01T00:00:00Z"},
		}},
		Log: &log,
		LLM: LLMOptions{BaseURL: baseURL, APIKeyEnv: keyEnv},
	})
	srv := httptest.NewServer(gw.Routes())
	t.Cleanup(func() { srv.Close(); gw.Close() })
	return strings.TrimPrefix(srv.URL, "http://"), &log
}

func postLLM(t *testing.T, base, token, path, body string) (int, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost,
		"http://"+base+path, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("post llm: %v", err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, string(out)
}

// upstream 记录收到的 Authorization，用来验证真 key 有没有送到、送的对不对。
func fakeUpstream(t *testing.T, seen *string, status int, reply string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*seen = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(reply))
	}))
	t.Cleanup(srv.Close)
	return srv
}

// ── key 从环境变量来，不进命令行也进不了配置 ----------

func TestLLMForwardsWithServerSideKey(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{"choices":[{"message":{"content":"hi"}}]}`)
	t.Setenv("TEST_LLM_KEY", "sk-real-company-key")

	base, _ := newLLMGateway(t, up.URL, "TEST_LLM_KEY")
	code, body := postLLM(t, base, "tok-a", "/llm/v1/chat/completions",
		`{"model":"x","messages":[]}`)
	if code != 200 {
		t.Fatalf("转发失败：%d %s", code, body)
	}
	if seen != "Bearer sk-real-company-key" {
		t.Fatalf("上游收到的 Authorization 不对：%q", seen)
	}
	// 响应原样回
	if !strings.Contains(body, "choices") {
		t.Fatalf("响应没透传：%s", body)
	}
}

func TestLLMClientTokenNeverReachesUpstream(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{}`)
	t.Setenv("TEST_LLM_KEY", "sk-real")
	base, _ := newLLMGateway(t, up.URL, "TEST_LLM_KEY")

	postLLM(t, base, "tok-a", "/llm/v1/chat/completions", `{}`)
	if strings.Contains(seen, "tok-a") {
		t.Fatalf("工程师的 token 被送到上游了：%q", seen)
	}
}

func TestLLMWithoutConfiguredBaseReturns503Not500(t *testing.T) {
	base, _ := newLLMGateway(t, "", "")
	code, body := postLLM(t, base, "tok-a", "/llm/v1/chat/completions", `{}`)
	if code != http.StatusServiceUnavailable {
		t.Fatalf("没配置时应 503（明确的「未启用」），实际 %d：%s", code, body)
	}
	if !strings.Contains(body, "not configured") {
		t.Errorf("要说清是没配置：%s", body)
	}
}

// 配了地址却没有 key：这是配置错误，必须和"没启用"区分开。
func TestLLMConfiguredButKeyMissingIsAnExplicitError(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{}`)
	t.Setenv("TEST_LLM_KEY", "")
	base, _ := newLLMGateway(t, up.URL, "TEST_LLM_KEY")

	code, body := postLLM(t, base, "tok-a", "/llm/v1/chat/completions", `{}`)
	if code != http.StatusInternalServerError {
		t.Fatalf("缺 key 应 500，实际 %d：%s", code, body)
	}
	if !strings.Contains(body, "TEST_LLM_KEY") {
		t.Errorf("要说出是哪个环境变量为空：%s", body)
	}
	if seen != "" {
		t.Fatalf("没有 key 却向上游发了请求：%q", seen)
	}
}

// ── 鉴权 ────────────────────────────────────────────────────────────────

func TestLLMRequiresValidToken(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{}`)
	t.Setenv("TEST_LLM_KEY", "sk-real")
	base, _ := newLLMGateway(t, up.URL, "TEST_LLM_KEY")

	for _, tok := range []string{"", "nope", "tok-old"} {
		code, _ := postLLM(t, base, tok, "/llm/v1/chat/completions", `{}`)
		if code != http.StatusUnauthorized {
			t.Errorf("token=%q 应 401，实际 %d", tok, code)
		}
	}
	if seen != "" {
		t.Fatal("未鉴权的请求却到了上游")
	}
}

// 没有 token 的 gateway 是一个开放的 LLM 代理人，谁发现地址都能白用额度。
func TestLLMWithNoTokenTableRejectsEveryone(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{}`)
	t.Setenv("TEST_LLM_KEY", "sk-real")
	gw := New(Options{Tokens: nil, LLM: LLMOptions{
		BaseURL: up.URL, APIKeyEnv: "TEST_LLM_KEY"}})
	srv := httptest.NewServer(gw.Routes())
	defer srv.Close()
	base := strings.TrimPrefix(srv.URL, "http://")

	code, _ := postLLM(t, base, "anything", "/llm/v1/chat/completions", `{}`)
	if code != http.StatusUnauthorized {
		t.Fatalf("没有 token 表时应一律拒绝，实际 %d", code)
	}
	if seen != "" {
		t.Fatal("没有 token 表却转发了")
	}
}

// ── 路径与状态码 ────────────────────────────────────────────────────────

func TestLLMPathIsPassedThroughUnchanged(t *testing.T) {
	var gotPath string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		_, _ = w.Write([]byte(`{}`))
	}))
	defer up.Close()
	t.Setenv("TEST_LLM_KEY", "k")
	base, _ := newLLMGateway(t, up.URL, "TEST_LLM_KEY")

	postLLM(t, base, "tok-a", "/llm/v1/models", `{}`)
	if gotPath != "/v1/models" {
		t.Fatalf("路径没原样透传：%q", gotPath)
	}
}

func TestLLMUpstreamErrorStatusIsPreserved(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, http.StatusTooManyRequests, `{"error":"rate limited"}`)
	t.Setenv("TEST_LLM_KEY", "k")
	base, _ := newLLMGateway(t, up.URL, "TEST_LLM_KEY")

	code, body := postLLM(t, base, "tok-a", "/llm/v1/chat/completions", `{}`)
	if code != http.StatusTooManyRequests {
		t.Fatalf("上游 429 被改写成 %d —— 调用方会以为是自己出错", code)
	}
	if !strings.Contains(body, "rate limited") {
		t.Errorf("错误体没透传：%s", body)
	}
}

// ── 审计只记元数据 ──────────────────────────────────────────────────────

func TestLLMAuditLogsActorAndStatusWithoutContent(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{"hello":"world"}`)
	t.Setenv("TEST_LLM_KEY", "sk-real")
	base, log := newLLMGateway(t, up.URL, "TEST_LLM_KEY")

	secret := "顶层机密：这块板是给客户 X 做的"
	postLLM(t, base, "tok-a", "/llm/v1/chat/completions",
		`{"messages":[{"role":"user","content":"`+secret+`"}]}`)

	text := log.String()
	if !strings.Contains(text, "甲") {
		t.Errorf("审计要记是谁：%s", text)
	}
	if strings.Contains(text, secret) {
		t.Fatalf("审计把提示词内容写进日志了：%s", text)
	}
	if strings.Contains(text, "world") {
		t.Fatalf("审计把响应内容写进日志了：%s", text)
	}
	if strings.Contains(text, "sk-real") {
		t.Fatalf("审计把真 key 写进日志了：%s", text)
	}
}

// health 要能看出 LLM 转发有没有启用。
func TestHealthReportsLLMEnabled(t *testing.T) {
	var seen string
	up := fakeUpstream(t, &seen, 200, `{}`)
	t.Setenv("TEST_LLM_KEY", "k")

	for _, tc := range []struct {
		baseURL string
		want    bool
	}{
		{up.URL, true},
		{"", false},
	} {
		gw := New(Options{Tokens: &TokenTable{Tokens: []Token{{Token: "t", Engineer: "x"}}},
			LLM: LLMOptions{BaseURL: tc.baseURL, APIKeyEnv: "TEST_LLM_KEY"}})
		srv := httptest.NewServer(gw.Routes())
		resp, err := http.Get(srv.URL + "/health")
		if err != nil {
			t.Fatal(err)
		}
		var out map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&out)
		resp.Body.Close()
		srv.Close()
		gw.Close()
		if got := out["llm"].(bool); got != tc.want {
			t.Errorf("baseURL=%q 时 llm 应为 %v，实际 %v", tc.baseURL, tc.want, got)
		}
	}
}
