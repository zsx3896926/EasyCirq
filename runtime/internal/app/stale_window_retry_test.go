package app

// Fix 3 的守卫：窗口 ID 变了要自动重试，但**只在唯一窗口时**。
//
// 多个窗口时猜错会把命令发到另一块板上——比失败更糟，所以必须不重试。

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestSoleLiveWindow(t *testing.T) {
	one := "window IDs change on reconnect. Connected now: " +
		"a43874f8-6578-42d3-b78d-34384d1f2c9c [project=(no project) doc=? host=electron]."
	got, ok := soleLiveWindow(one)
	if !ok || got != "a43874f8-6578-42d3-b78d-34384d1f2c9c" {
		t.Fatalf("soleLiveWindow(one) = %q,%v", got, ok)
	}

	two := "Connected now: a43874f8-6578-42d3-b78d-34384d1f2c9c [project=a doc=1]," +
		" 813e5d4d-f031-4106-aa44-74831cf6b2e3 [project=b doc=2]."
	if _, ok := soleLiveWindow(two); ok {
		t.Fatal("two windows must NOT auto-retry (routing to the wrong board is worse than failing)")
	}

	if _, ok := soleLiveWindow("no windows here"); ok {
		t.Fatal("missing marker must not yield a window")
	}
	if _, ok := soleLiveWindow(""); ok {
		t.Fatal("empty detail must not yield a window")
	}
}

// staleDaemon 第一次回 STALE_WINDOW（带一个可选窗口），之后成功。
func staleDaemon(t *testing.T, detail string) (*appConfig, *[]string, func()) {
	t.Helper()
	var mu sync.Mutex
	seen := []string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/health":
			_, _ = w.Write([]byte(`{"service":"easycirq-agent","windows":[{"windowId":"w1"}]}`))
		case "/action":
			var body struct {
				WindowID string `json:"windowId,omitempty"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			mu.Lock()
			seen = append(seen, body.WindowID)
			first := len(seen) == 1
			mu.Unlock()
			if first {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte(`{"ok":false,"error":{"code":"STALE_WINDOW",` +
					`"message":"window is not connected","detail":"` + detail + `"}}`))
				return
			}
			_, _ = w.Write([]byte(`{"ok":true,"result":{}}`))
		default:
			http.NotFound(w, r)
		}
	}))
	hostPort := strings.TrimPrefix(srv.URL, "http://")
	host, portStr, _ := strings.Cut(hostPort, ":")
	port, _ := strconv.Atoi(portStr)
	cfg := &appConfig{host: host, ports: strconv.Itoa(port) + "-" + strconv.Itoa(port)}
	return cfg, &seen, srv.Close
}

func TestStaleWindowRetriesOnTheSoleWindow(t *testing.T) {
	detail := "window IDs change on reconnect. Connected now: " +
		"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee [project=(no project) doc=? host=electron]."
	cfg, seen, cleanup := staleDaemon(t, detail)
	defer cleanup()

	res, err := requestActionTimed(cfg, "schematic.pages.list",
		"deadbeef-0000-0000-0000-000000000000", nil, 5*time.Second)
	if err != nil {
		t.Fatalf("expected the retry to succeed, got %v", err)
	}
	if res == nil || !res.OK {
		t.Fatalf("res = %#v", res)
	}
	if len(*seen) != 2 {
		t.Fatalf("want 2 attempts (stale + retry), got %d: %v", len(*seen), *seen)
	}
	if (*seen)[1] != "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" {
		t.Fatalf("retry went to %q, want the connected window", (*seen)[1])
	}
}

func TestStaleWindowDoesNotRetryWhenAmbiguous(t *testing.T) {
	detail := "Connected now: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee [p=(x)]," +
		" 11111111-2222-3333-4444-555555555555 [p=(y)]."
	cfg, seen, cleanup := staleDaemon(t, detail)
	defer cleanup()

	if _, err := requestActionTimed(cfg, "schematic.pages.list",
		"deadbeef-0000-0000-0000-000000000000", nil, 5*time.Second); err == nil {
		t.Fatal("two windows: must fail rather than guess")
	}
	if len(*seen) != 1 {
		t.Fatalf("must not retry when ambiguous, attempts=%v", *seen)
	}
}
