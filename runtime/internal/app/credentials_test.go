package app

// credentials_test.go — 登录凭据与「命令往哪发」。

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func withCredFile(t *testing.T) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "credentials.json")
	t.Setenv(envCredentials, path)
	return path
}

func TestSaveAndLoadCredentials(t *testing.T) {
	withCredFile(t)
	path, err := saveCredentials(Credentials{
		Server: "https://easycirq.company.com/", // 结尾斜杠要被去掉
		Token:  "tok-123",
		Engineer: "张工",
	})
	if err != nil {
		t.Fatal(err)
	}
	cred, remote, err := loadCredentials()
	if err != nil {
		t.Fatal(err)
	}
	if !remote {
		t.Fatal("存了凭据却报未登录")
	}
	if cred.Server != "https://easycirq.company.com" {
		t.Errorf("server 结尾斜杠没去掉：%q", cred.Server)
	}
	if cred.Token != "tok-123" || cred.Engineer != "张工" {
		t.Errorf("凭据内容不对：%+v", cred)
	}
	_ = path
}

// 没登录是正常状态，不是错误。
func TestNoCredentialMeansLocalMode(t *testing.T) {
	withCredFile(t)
	_, remote, err := loadCredentials()
	if err != nil {
		t.Fatalf("没有凭据不该报错：%v", err)
	}
	if remote {
		t.Fatal("没有凭据却报已登录")
	}
}

// 文件坏了必须报错，**不能静默回落到本机**——
// 那样工程师会以为在操作公司服务器，其实在本机窗口。
func TestCorruptCredentialsIsAnErrorNotASilentFallback(t *testing.T) {
	path := withCredFile(t)
	if err := os.WriteFile(path, []byte("{ 不是 json"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, remote, err := loadCredentials()
	if err == nil {
		t.Fatal("凭据文件损坏却静默通过")
	}
	if remote {
		t.Fatal("损坏时不该报已登录")
	}
	if !strings.Contains(err.Error(), "损坏") {
		t.Errorf("报错要说清是损坏：%v", err)
	}
	if !strings.Contains(err.Error(), "login") {
		t.Errorf("报错要告诉人怎么办：%v", err)
	}
}

func TestCredentialsMissingFieldsIsAnError(t *testing.T) {
	path := withCredFile(t)
	if err := os.WriteFile(path, []byte(`{"server":"https://h"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	_, _, err := loadCredentials()
	if err == nil || !strings.Contains(err.Error(), "token") {
		t.Fatalf("缺 token 必须报错：%v", err)
	}
}

func TestClearCredentialsIsIdempotent(t *testing.T) {
	withCredFile(t)
	if err := clearCredentials(); err != nil {
		t.Fatalf("没有文件时清除不该报错：%v", err)
	}
	if _, err := saveCredentials(Credentials{Server: "https://h", Token: "t"}); err != nil {
		t.Fatal(err)
	}
	if err := clearCredentials(); err != nil {
		t.Fatal(err)
	}
	if _, remote, _ := loadCredentials(); remote {
		t.Fatal("清除后仍报已登录")
	}
}

func TestRedactTokenNeverShowsWhole(t *testing.T) {
	tok := "SUPER-SECRET-VALUE"
	got := redactToken(tok)
	if strings.Contains(got, tok) {
		t.Fatalf("脱敏后仍含完整 token：%q", got)
	}
	if redactToken("abc") != "***" {
		t.Fatalf("短 token 应全遮：%q", redactToken("abc"))
	}
}

// ── 命令往哪发 ──────────────────────────────────────────────────────────

func TestEndpointIsRemoteWhenLoggedIn(t *testing.T) {
	withCredFile(t)
	if _, err := saveCredentials(Credentials{
		Server: "https://easycirq.company.com", Token: "tok"}); err != nil {
		t.Fatal(err)
	}
	// 本机没有 daemon（scan 为空）也不该出错——登录了就不需要本机
	ep, err := resolveActionEndpoint(&appConfig{}, healthResult{})
	if err != nil {
		t.Fatalf("已登录却报错：%v", err)
	}
	if !ep.remote {
		t.Fatal("已登录却没发往远端")
	}
	if ep.url != "https://easycirq.company.com/action" {
		t.Errorf("URL 不对：%q", ep.url)
	}
	if ep.token != "tok" {
		t.Errorf("token 没带上：%q", ep.token)
	}
}

// 没登录又没有本机 daemon：报错必须把两条路都说出来。
func TestEndpointWithoutLoginAndDaemonExplainsBothPaths(t *testing.T) {
	withCredFile(t)
	_, err := resolveActionEndpoint(&appConfig{}, healthResult{})
	if err == nil {
		t.Fatal("两边都没有却没报错")
	}
	for _, want := range []string{"daemon start", "login --server"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("报错缺 %q：%v", want, err)
		}
	}
}

// ── 登录必须真的验证 token ──────────────────────────────────────────────

func TestProbeAuthAcceptsKnownTokenRejectsUnknown(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/action", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer good" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	if err := probeServerAuth(srv.URL, "good"); err != nil {
		t.Fatalf("正确的 token 被拒：%v", err)
	}
	if err := probeServerAuth(srv.URL, "bad"); err == nil {
		t.Fatal("错误的 token 竟然通过了 —— 这正是 2026-11-03 实测到的缺陷")
	}
}

func TestProbeHealthRejectsNonGateway(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"service":"something-else"}`))
	}))
	defer srv.Close()
	if _, err := probeServerHealth(srv.URL); err == nil {
		t.Fatal("不是 EasyCirq 网关却接受了")
	}
}
