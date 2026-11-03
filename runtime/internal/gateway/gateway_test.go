package gateway

// gateway_test.go — 多租户路由的端到端验证。
//
// 用假连接器（和 daemon 的 connect_test.go 同一套路），因此这些测试证明的
// 是**真实的连接路由**，不是"构造了一个 URL 字符串"。
//
// 最关键的一条：token A 的连接**绝不**能收到 token B 的请求。

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"
	"github.com/coder/websocket/wsjson"
	"github.com/zsx3896926/EasyCirq/runtime/internal/daemon"
	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

func table(t *testing.T, entries ...Token) *TokenTable {
	t.Helper()
	return &TokenTable{Tokens: entries}
}

// newGateway 起一个 gateway，返回它的 httptest server（含 host:port 的 base）。
func newGateway(t *testing.T, tbl *TokenTable) (*Server, string) {
	t.Helper()
	var log bytes.Buffer
	opts := Options{
		Tokens:     tbl,
		Log:        &log,
		PublicPort: 443,
		DaemonOptions: daemon.Options{
			Version:   "test",
			PortStart: 1,
			PortEnd:   1,
			Host:      "127.0.0.1",
		},
	}
	gw := New(opts)
	srv := httptest.NewServer(gw.Routes())
	t.Cleanup(func() {
		srv.Close()
		gw.Close()
	})
	return gw, strings.TrimPrefix(srv.URL, "http://")
}

// dialConnector 以某个 token 连上 /eda 并完成注册。
func dialConnector(t *testing.T, base, token, windowID string) *websocket.Conn {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	c, _, err := websocket.Dial(ctx, "ws://"+base+"/eda?token="+token, nil)
	if err != nil {
		t.Fatalf("dial connector: %v", err)
	}
	reg := protocol.Register{
		Type:             protocol.TypeRegister,
		WindowID:         windowID,
		ConnectorVersion: "test",
		EasyEDAVersion:   "test",
		Capabilities:     []string{"schematic.v1"},
	}
	if err := wsjson.Write(ctx, c, reg); err != nil {
		t.Fatalf("send register: %v", err)
	}
	return c
}

// echoWith 回复每个请求，把 action 和它自己声明的标签一起回显。
// 标签用来验证「这个响应来自哪个连接」。
func echoWith(ctx context.Context, c *websocket.Conn, label string) {
	for {
		_, data, err := c.Read(ctx)
		if err != nil {
			return
		}
		var typed protocol.Typed
		if json.Unmarshal(data, &typed) != nil || typed.Type != protocol.TypeRequest {
			continue
		}
		var req protocol.Request
		if json.Unmarshal(data, &req) != nil {
			continue
		}
		resp := protocol.Response{
			Envelope: protocol.Envelope{ID: req.ID, Type: protocol.TypeResponse, Version: "v1"},
			OK:       true,
			Result:   map[string]any{"echo": req.Action, "served_by": label},
		}
		_ = wsjson.Write(ctx, c, resp)
	}
}

// postActionWindow 带 windowId 发命令——用来验证「哪个窗口被命中」。
func postActionWindow(t *testing.T, base, token, action, windowID string) (int, map[string]any) {
	t.Helper()
	body, _ := json.Marshal(protocol.Request{
		Envelope: protocol.Envelope{ID: "req-w", Type: protocol.TypeRequest,
			Version: "v1", WindowID: windowID},
		Action: action,
	})
	req, err := http.NewRequest(http.MethodPost, "http://"+base+"/action", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("post action: %v", err)
	}
	defer resp.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return resp.StatusCode, out
}

// servedBy 从响应里取回显标签。
func servedBy(out map[string]any) string {
	res, _ := out["result"].(map[string]any)
	if res == nil {
		return ""
	}
	s, _ := res["served_by"].(string)
	return s
}

func postAction(t *testing.T, base, token, action string) (int, map[string]any) {
	t.Helper()
	body, _ := json.Marshal(protocol.Request{
		Envelope: protocol.Envelope{ID: "req-1", Type: protocol.TypeRequest, Version: "v1"},
		Action:   action,
	})
	req, err := http.NewRequest(http.MethodPost, "http://"+base+"/action", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("post action: %v", err)
	}
	defer resp.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return resp.StatusCode, out
}

// ── token 表 ─────────────────────────────────────────────────────────────

func TestTokenTableRejectsDuplicateAndUnnamed(t *testing.T) {
	cases := map[string]string{
		`{"tokens":[{"token":"a","engineer":"x"},{"token":"a","engineer":"y"}]}`: "duplicate",
		`{"tokens":[{"token":"","engineer":"x"}]}`:                              "empty token",
		`{"tokens":[{"token":"a"}]}`:                                            "no engineer",
		`{"tokens":[{"token":"a","engineer":"x","bogus":1}]}`:                   "unknown field",
	}
	for body, want := range cases {
		_, err := LoadTokenTable(strings.NewReader(body))
		if err == nil {
			t.Errorf("%s: 应当拒绝", want)
			continue
		}
		if !strings.Contains(err.Error(), want) {
			t.Errorf("%s: 报错应含 %q，实际：%v", want, want, err)
		}
	}
}

func TestTokenTableAcceptsValid(t *testing.T) {
	tt, err := LoadTokenTable(strings.NewReader(
		`{"tokens":[{"token":"abc","engineer":"张工","expires":"2099-01-01T00:00:00Z"}]}`))
	if err != nil {
		t.Fatalf("合法表被拒：%v", err)
	}
	if len(tt.Tokens) != 1 || tt.Tokens[0].Engineer != "张工" {
		t.Fatalf("解析不对：%+v", tt.Tokens)
	}
}

// ── 鉴权 ────────────────────────────────────────────────────────────────

func TestConnectorWithoutTokenIsRejected(t *testing.T) {
	_, base := newGateway(t, table(t, Token{Token: "t-a", Engineer: "甲"}))
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	c, _, err := websocket.Dial(ctx, "ws://"+base+"/eda", nil)
	if err == nil {
		c.Close(websocket.StatusNormalClosure, "")
		t.Fatal("没有 token 却连上了")
	}
}

func TestConnectorWithUnknownTokenIsRejected(t *testing.T) {
	_, base := newGateway(t, table(t, Token{Token: "t-a", Engineer: "甲"}))
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	c, _, err := websocket.Dial(ctx, "ws://"+base+"/eda?token=nope", nil)
	if err == nil {
		c.Close(websocket.StatusNormalClosure, "")
		t.Fatal("未知 token 却连上了")
	}
}

func TestExpiredTokenIsRejected(t *testing.T) {
	_, base := newGateway(t, table(t,
		Token{Token: "t-old", Engineer: "甲", Expires: "2020-01-01T00:00:00Z"}))
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	c, _, err := websocket.Dial(ctx, "ws://"+base+"/eda?token=t-old", nil)
	if err == nil {
		c.Close(websocket.StatusNormalClosure, "")
		t.Fatal("过期 token 却连上了")
	}
}

func TestActionRequiresBearer(t *testing.T) {
	_, base := newGateway(t, table(t, Token{Token: "t-a", Engineer: "甲"}))
	code, _ := postAction(t, base, "", "system.health")
	if code != http.StatusUnauthorized {
		t.Fatalf("没有 Bearer 应 401，实际 %d", code)
	}
}

func TestActionRejectsTokenInQuery(t *testing.T) {
	// 命令带 token 进 query，容易被写进 shell 历史和代理日志。
	_, base := newGateway(t, table(t, Token{Token: "t-a", Engineer: "甲"}))
	body, _ := json.Marshal(protocol.Request{
		Envelope: protocol.Envelope{ID: "r", Type: protocol.TypeRequest, Version: "v1"},
		Action:   "system.health",
	})
	resp, err := http.Post("http://"+base+"/action?token=t-a",
		"application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("/action 只认 Authorization 头，query 里的 token 不该被接受（实际 %d）",
			resp.StatusCode)
	}
}

// ── 多租户隔离（最重要的一条）──────────────────────────────────────────

func TestTwoTenantsAreIsolated(t *testing.T) {
	_, base := newGateway(t, table(t,
		Token{Token: "t-甲", Engineer: "甲"},
		Token{Token: "t-乙", Engineer: "乙"},
	))

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	a := dialConnector(t, base, "t-甲", "win-甲")
	defer a.Close(websocket.StatusNormalClosure, "")
	go echoWith(ctx, a, "甲")

	b := dialConnector(t, base, "t-乙", "win-乙")
	defer b.Close(websocket.StatusNormalClosure, "")
	go echoWith(ctx, b, "乙")

	// 给两个连接一点时间完成注册
	time.Sleep(200 * time.Millisecond)

	// ① 各自打自己的窗口：都应当被路由到自己的连接并拿到回显。
	//    echoWith 把 served_by 回显出来，所以能看出是谁答的。
	code, out := postActionWindow(t, base, "t-甲", "schematic.pages.list", "win-甲")
	if code != http.StatusOK {
		t.Fatalf("甲打自己窗口失败：%d %+v", code, out)
	}
	if got := servedBy(out); got != "甲" {
		t.Fatalf("甲的请求被 %q 回答了，应当由甲回答：%+v", got, out)
	}

	code, out = postActionWindow(t, base, "t-乙", "schematic.pages.list", "win-乙")
	if code != http.StatusOK {
		t.Fatalf("乙打自己窗口失败：%d %+v", code, out)
	}
	if got := servedBy(out); got != "乙" {
		t.Fatalf("乙的请求被 %q 回答了：%+v", got, out)
	}

	// ② 关键一条：甲拿乙的 windowId 去打，必须**打不到**。
	//    如果两个租户共用了连接表，这里就会成功——那才是真的串了。
	code, out = postActionWindow(t, base, "t-甲", "schematic.pages.list", "win-乙")
	if code == http.StatusOK {
		t.Fatalf("甲用乙的 windowId 竟然成功了，租户没隔离：%+v", out)
	}

	// ③ 两个租户的 daemon 必须是不同实例
	gw, _ := newGateway(t, table(t,
		Token{Token: "x1", Engineer: "一"},
		Token{Token: "x2", Engineer: "二"},
	))
	if _, err := gw.tenantFor(Token{Token: "x1", Engineer: "一"}); err != nil {
		t.Fatal(err)
	}
	if _, err := gw.tenantFor(Token{Token: "x2", Engineer: "二"}); err != nil {
		t.Fatal(err)
	}
	if gw.tenants["x1"] == gw.tenants["x2"] {
		t.Fatal("两个 token 共用了同一个租户运行时")
	}
}

// ── 日志脱敏 ────────────────────────────────────────────────────────────

func TestRedactNeverLeaksTheWholeToken(t *testing.T) {
	tok := "SUPER-SECRET-TOKEN-VALUE"
	got := redact(tok)
	if strings.Contains(got, tok) {
		t.Fatalf("脱敏后仍含完整 token：%q", got)
	}
	if got == "" {
		t.Fatal("脱敏后不该是空串")
	}
	// 短 token 完全遮住
	if redact("abc") != "***" {
		t.Fatalf("短 token 应完全遮住，实际 %q", redact("abc"))
	}
}

func TestHealthIsUnauthenticatedAndCountsTenants(t *testing.T) {
	gw, base := newGateway(t, table(t,
		Token{Token: "t1", Engineer: "一"},
		Token{Token: "t2", Engineer: "二"},
	))
	resp, err := http.Get("http://" + base + "/health")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("/health 应免鉴权，实际 %d", resp.StatusCode)
	}
	var out map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&out)
	if out["service"] != "easycirq-gateway" {
		t.Fatalf("service 字段不对：%+v", out)
	}
	if int(out["tokens"].(float64)) != 2 {
		t.Fatalf("token 数不对：%+v", out)
	}
	_ = gw
}
