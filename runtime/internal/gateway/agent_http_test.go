package gateway

// agent_http_test.go — 「工程师机器不装 easycirq.exe」的实际验证。
//
// CLI 只是 /action 的一个 HTTP 客户端。这条测试**不经过 CLI**：
// 直接往 gateway 的 /action 发一个 JSON 请求，由连接器在客户端执行并回读。
//
// 这就是「不装 CLI」的技术依据：任何能发 HTTP 的东西都能驱动同一个接口。

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"github.com/coder/websocket"
	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

// 这一段证明：一个裸 HTTP 请求就能让真实的连接器执行动作并回读结果，
// 全程没有任何 easycirq.exe 参与。
func TestRawHTTPDrivesConnectorWithoutCLI(t *testing.T) {
	_, base := newGateway(t, table(t, Token{Token: "tok", Engineer: "甲"}))

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	conn := dialConnector(t, base, "tok", "win-1")
	defer conn.Close(websocket.StatusNormalClosure, "")
	go echoWith(ctx, conn, "甲")
	time.Sleep(200 * time.Millisecond)

	// ── 这就是全部：一个 HTTP POST，没有任何 CLI ──
	payload := map[string]any{
		"type":     "request",
		"version":  "v1",
		"action":   "schematic.pages.list",
		"windowId": "win-1",
	}
	body, _ := json.Marshal(payload)
	req, err := http.NewRequest(http.MethodPost, "http://"+base+"/action",
		bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer tok")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("裸 HTTP 请求失败：%d %+v", resp.StatusCode, out)
	}
	if servedBy(out) != "甲" {
		t.Fatalf("动作没到达连接器：%+v", out)
	}
}

// 同一个请求，没有 token —— 必须被拒，且连接器一次都不被打扰。
func TestRawHTTPWithoutTokenIsRefused(t *testing.T) {
	_, base := newGateway(t, table(t, Token{Token: "tok", Engineer: "甲"}))
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	conn := dialConnector(t, base, "tok", "win-1")
	defer conn.Close(websocket.StatusNormalClosure, "")
	go echoWith(ctx, conn, "甲")
	time.Sleep(150 * time.Millisecond)

	body, _ := json.Marshal(protocol.Request{
		Envelope: protocol.Envelope{ID: "r", Type: protocol.TypeRequest, Version: "v1"},
		Action:   "schematic.pages.list",
	})
	resp, err := http.Post("http://"+base+"/action",
		"application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("没有 token 却放行：%d", resp.StatusCode)
	}
}
