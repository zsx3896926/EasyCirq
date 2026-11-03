package app

// cmd_llmproxy_test.go — 本机 LLM 代理。

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// fakeCompanyServer 记录收到的 Authorization，并回一个可辨识的响应。
func fakeCompanyServer(t *testing.T, seen *string, status int) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*seen = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"来自公司服务器"}}]}`))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func callProxy(t *testing.T, h http.Handler, path, body string) (int, string) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	// 回环来源，才能通过 loopbackOnly
	req.RemoteAddr = "127.0.0.1:54321"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	out, _ := io.ReadAll(rec.Result().Body)
	return rec.Code, string(out)
}

func TestProxyForwardsWithEngineerToken(t *testing.T) {
	var seen string
	company := fakeCompanyServer(t, &seen, 200)
	h := newLLMProxyHandler(Credentials{Server: company.URL, Token: "eng-token"})

	code, body := callProxy(t, h, "/v1/chat/completions", `{"messages":[]}`)
	if code != 200 {
		t.Fatalf("转发失败：%d %s", code, body)
	}
	if seen != "Bearer eng-token" {
		t.Fatalf("公司服务器收到的凭据不对：%q", seen)
	}
	if !strings.Contains(body, "来自公司服务器") {
		t.Fatalf("响应没透传：%s", body)
	}
}

// Agent 配的是 /v1，代理要接到服务器的 /llm/v1/...
func TestProxyMapsV1ToServerLLMPath(t *testing.T) {
	var gotPath string
	var seen string
	company := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		seen = r.Header.Get("Authorization")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer company.Close()

	h := newLLMProxyHandler(Credentials{Server: company.URL, Token: "t"})
	callProxy(t, h, "/v1/models", `{}`)
	if gotPath != "/llm/v1/models" {
		t.Fatalf("路径映射不对：%q", gotPath)
	}
	if seen != "Bearer t" {
		t.Fatalf("token 没带上：%q", seen)
	}
}

// 上游状态码原样回：429 被改写会让调用方以为自己没问题。
func TestProxyPreservesUpstreamStatus(t *testing.T) {
	var seen string
	company := fakeCompanyServer(t, &seen, http.StatusTooManyRequests)
	h := newLLMProxyHandler(Credentials{Server: company.URL, Token: "t"})
	code, _ := callProxy(t, h, "/v1/chat/completions", `{}`)
	if code != http.StatusTooManyRequests {
		t.Fatalf("状态码被改写：%d", code)
	}
}

// 只有本机能用：哪怕误绑 0.0.0.0，外网来源也要被拒。
func TestProxyRejectsNonLoopbackClients(t *testing.T) {
	var seen string
	company := fakeCompanyServer(t, &seen, 200)
	h := loopbackOnly(newLLMProxyHandler(Credentials{Server: company.URL, Token: "t"}))

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	req.RemoteAddr = "203.0.113.9:5000" // 外网地址
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("外网来源应 403，实际 %d", rec.Code)
	}
	if seen != "" {
		t.Fatal("外网请求被转发到公司服务器了")
	}
}

func TestProxyAcceptsLoopbackVariants(t *testing.T) {
	for _, addr := range []string{"127.0.0.1:1", "[::1]:1"} {
		var seen string
		company := fakeCompanyServer(t, &seen, 200)
		h := loopbackOnly(newLLMProxyHandler(Credentials{Server: company.URL, Token: "t"}))
		req := httptest.NewRequest(http.MethodPost, "/v1/x", strings.NewReader(`{}`))
		req.RemoteAddr = addr
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code == http.StatusForbidden {
			t.Errorf("回环地址 %s 被误拒", addr)
		}
	}
}

// 服务器连不上时，报错要说清是"公司服务器不可达"，不是笼统的 500。
func TestProxyReportsUnreachableServerClearly(t *testing.T) {
	h := newLLMProxyHandler(Credentials{Server: "http://127.0.0.1:1", Token: "t"})
	code, body := callProxy(t, h, "/v1/chat/completions", `{}`)
	if code != http.StatusBadGateway {
		t.Fatalf("应 502，实际 %d", code)
	}
	if !strings.Contains(body, "company server unreachable") {
		t.Errorf("报错要指向上游不可达：%s", body)
	}
}

// 代理进程本身**不存真 key**：它只有 token。
// 这条钉住"真 key 只可能在服务器"这句话。
func TestProxyHandlerHoldsOnlyTheToken(t *testing.T) {
	cred := Credentials{Server: "https://h", Token: "tok-only"}
	// Credentials 结构里没有 key 字段；这里用序列化确认它不会意外带上什么。
	data, err := json.Marshal(cred)
	if err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{"sk-", "api_key", "apiKey", "secret"} {
		if bytes.Contains(data, []byte(bad)) {
			t.Fatalf("凭据里出现了疑似密钥字段：%s", data)
		}
	}
}
