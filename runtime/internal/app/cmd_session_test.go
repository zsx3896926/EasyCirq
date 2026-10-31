package app

// Session-guard tests for the 2026-10-30 recovery deadlock: restarting EasyEDA
// changes windowId, `session gate` then reports STALE_WINDOW, and `session bind`
// — the only command that can repair the binding — was itself refused by the
// window-mismatch guard because bind dispatches project.open, a mutating action.
//
// The fix must keep BOTH properties:
//   a. an ordinary mutating action targeting a foreign window is still refused
//      (regression protection — the guard is not weakened), and
//   b. `session bind` may name the new window and overwrite the stale binding.

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
)

// ── fixtures ────────────────────────────────────────────────────────────────

// writeBoundSession points EASYCIRQ_SESSION_FILE at a temp file and records a
// binding, returning the file path. Mirrors what a previous (now stale) run left
// on disk.
func writeBoundSession(t *testing.T, windowID, projectUUID string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "session.json")
	t.Setenv("EASYCIRQ_SESSION_FILE", path)
	t.Setenv("EASYCIRQ_SESSION_ENFORCE", "")
	if err := writeSessionRecord(sessionRecord{WindowID: windowID, ProjectUUID: projectUUID}); err != nil {
		t.Fatalf("seed session: %v", err)
	}
	return path
}

// unboundSession points EASYCIRQ_SESSION_FILE at a path that does not exist, so
// the guard takes its legacy "no binding" branch.
func unboundSession(t *testing.T) {
	t.Helper()
	t.Setenv("EASYCIRQ_SESSION_FILE", filepath.Join(t.TempDir(), "absent.json"))
	t.Setenv("EASYCIRQ_SESSION_ENFORCE", "")
}

type sessionTestCall struct {
	Action string
	Window string
}

// sessionTestDaemon answers /health for a fixed window list and the actions the
// session commands dispatch, recording the window each action targeted.
type sessionTestDaemon struct {
	mu    sync.Mutex
	calls []sessionTestCall
}

func (d *sessionTestDaemon) snapshot() []sessionTestCall {
	d.mu.Lock()
	defer d.mu.Unlock()
	return append([]sessionTestCall(nil), d.calls...)
}

func newSessionTestDaemon(t *testing.T, windows ...string) (*appConfig, *sessionTestDaemon, func()) {
	t.Helper()
	state := &sessionTestDaemon{}
	health := map[string]any{"service": "easycirq-agent", "windows": []any{}}
	for _, w := range windows {
		health["windows"] = append(health["windows"].([]any), map[string]any{"windowId": w})
	}
	healthJSON, err := json.Marshal(health)
	if err != nil {
		t.Fatalf("marshal health fixture: %v", err)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/health":
			_, _ = w.Write(healthJSON)
		case "/action":
			var body struct {
				Action   string         `json:"action"`
				WindowID string         `json:"windowId"`
				Payload  map[string]any `json:"payload"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			state.mu.Lock()
			state.calls = append(state.calls, sessionTestCall{Action: body.Action, Window: body.WindowID})
			state.mu.Unlock()
			switch body.Action {
			case "project.open":
				uuid, _ := body.Payload["projectUuid"].(string)
				_ = json.NewEncoder(w).Encode(map[string]any{
					"ok": true, "result": map[string]any{"uuid": uuid},
					"context": map[string]any{"projectUuid": uuid, "documentUuid": "d1", "documentType": "schematic"},
				})
			case "document.current":
				_ = json.NewEncoder(w).Encode(map[string]any{
					"ok": true,
					"result": map[string]any{
						"uuid": "d1", "parentProjectUuid": "p1",
						"projectName": "demo", "documentType": "schematic",
					},
				})
			default:
				_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "result": map[string]any{}})
			}
		default:
			http.NotFound(w, r)
		}
	}))
	hostPort := strings.TrimPrefix(srv.URL, "http://")
	host, portText, _ := strings.Cut(hostPort, ":")
	if _, err := strconv.Atoi(portText); err != nil {
		srv.Close()
		t.Fatalf("parse test daemon port: %v", err)
	}
	return &appConfig{host: host, ports: portText + "-" + portText}, state, srv.Close
}

// ── (a) regression: ordinary writes stay gated ──────────────────────────────

func TestSessionGuardStillRejectsForeignWindowWrites(t *testing.T) {
	path := writeBoundSession(t, "w-old", "p1")
	if bindRebindWindow.Load() {
		t.Fatal("bind rebind mark must be off outside `session bind`")
	}
	cfg := &appConfig{}
	for _, action := range []string{"project.open", "schematic.component.place", "schematic.save"} {
		if !actionMutates(action) {
			t.Fatalf("%s must remain a mutating action or the guard test proves nothing", action)
		}
		err := enforceSession(cfg, action, "w-new")
		if err == nil || !strings.Contains(err.Error(), "session mismatch") {
			t.Fatalf("%s on a foreign window must be refused with session mismatch, got %v", action, err)
		}
		if !strings.Contains(err.Error(), "w-old") || !strings.Contains(err.Error(), path) {
			t.Fatalf("%s refusal must name the bound window and file: %v", action, err)
		}
		if err := enforceSession(cfg, action, "w-old"); err != nil {
			t.Fatalf("%s on the bound window must pass: %v", action, err)
		}
	}
	// Reads are never gated and the binding on disk is untouched by refusals.
	if err := enforceSession(cfg, "document.open", "w-new"); err != nil {
		t.Fatalf("non-mutating action must not be gated: %v", err)
	}
	record, err := readSessionRecord()
	if err != nil {
		t.Fatal(err)
	}
	if record.WindowID != "w-old" || record.ProjectUUID != "p1" {
		t.Fatalf("refused writes must not touch the binding: %+v", record)
	}
}

// ── (b) new behaviour: session bind repairs the binding ─────────────────────

func TestSessionBindRebindsAfterWindowIdChurn(t *testing.T) {
	path := writeBoundSession(t, "w-old", "p1")
	cfg, daemon, closeServer := newSessionTestDaemon(t, "w1")
	defer closeServer()

	// Without the rebind mark the very same route is refused — this is the
	// deadlock being fixed, asserted on the live code path (not a mock).
	if err := enforceSession(&appConfig{}, "project.open", "w1"); err == nil {
		t.Fatal("project.open on a changed window must be refused outside `session bind`")
	}

	var stdout, stderr bytes.Buffer
	code := Run([]string{
		"session", "bind", "--window", "w1", "--project-uuid", "p1", "--allow-discard-unsaved",
		"--host", cfg.host, "--ports", cfg.ports,
	}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("session bind after windowId churn must succeed, exit=%d stdout=%s stderr=%s",
			code, stdout.String(), stderr.String())
	}
	if bindRebindWindow.Load() {
		t.Fatal("bind rebind mark must be cleared once the command returns")
	}

	record, err := readSessionRecord()
	if err != nil {
		t.Fatal(err)
	}
	if record.WindowID != "w1" || record.ProjectUUID != "p1" {
		t.Fatalf("binding was not repaired: %+v", record)
	}
	if record.Path != path {
		t.Fatalf("binding must be written to %s, wrote %s", path, record.Path)
	}
	if record.DocumentUUID != "d1" || record.DocumentType != "schematic" {
		t.Fatalf("binding lost the live document identity: %+v", record)
	}
	if !strings.Contains(stdout.String(), `"windowId": "w1"`) {
		t.Fatalf("bind must report the recorded record: %s", stdout.String())
	}

	// The routing action was dispatched to the NEW window, and afterwards the
	// plain write guard uses the new binding (old window is now the foreign one).
	sawProjectOpen := false
	for _, call := range daemon.snapshot() {
		if call.Action == "project.open" {
			sawProjectOpen = true
			if call.Window != "w1" {
				t.Fatalf("project.open targeted %s, want w1", call.Window)
			}
		}
	}
	if !sawProjectOpen {
		t.Fatal("bind never dispatched project.open")
	}
	if err := enforceSession(&appConfig{}, "schematic.save", "w1"); err != nil {
		t.Fatalf("after rebind the new window must pass: %v", err)
	}
	if err := enforceSession(&appConfig{}, "schematic.save", "w-old"); err == nil {
		t.Fatal("after rebind the stale window must be refused")
	}
}

// ── (b') the exemption is narrow, not a hole ────────────────────────────────

func TestSessionRebindKeepsProjectSemanticsAndWindowRequirement(t *testing.T) {
	writeBoundSession(t, "w-old", "p1")

	// A bind routed through a different project must not pass silently.
	err := withBindRebindWindow(func() error {
		return enforceSession(&appConfig{project: "p2"}, "project.open", "w1")
	})
	if err == nil || !strings.Contains(err.Error(), "project") {
		t.Fatalf("rebind must still check the project leg, got %v", err)
	}

	// The recorded project routes fine.
	if err := withBindRebindWindow(func() error {
		return enforceSession(&appConfig{project: "p1"}, "project.open", "w1")
	}); err != nil {
		t.Fatalf("rebind with the recorded project must pass: %v", err)
	}

	// --window stays mandatory: the exemption is about WHICH window, not about
	// writing with no window at all.
	if err := withBindRebindWindow(func() error {
		return enforceSession(&appConfig{}, "project.open", "  ")
	}); err == nil {
		t.Fatal("rebind must not accept a blank window")
	}

	// The mark is restored even when the gated work fails.
	sentinel := errors.New("boom")
	if err := withBindRebindWindow(func() error { return sentinel }); !errors.Is(err, sentinel) {
		t.Fatalf("withBindRebindWindow must propagate the error, got %v", err)
	}
	if bindRebindWindow.Load() {
		t.Fatal("bind rebind mark leaked after an error")
	}
}

// ── (c) unbound workspaces behave exactly as before ─────────────────────────

func TestSessionGuardUnboundWorkspaceIsLegacy(t *testing.T) {
	unboundSession(t)
	cfg := &appConfig{}
	for _, action := range []string{"project.open", "schematic.component.place"} {
		if err := enforceSession(cfg, action, "any-window"); err != nil {
			t.Fatalf("%s without a binding must pass (legacy): %v", action, err)
		}
	}
	// Blank window is still refused once a binding exists; without one it is fine.
	if err := enforceSession(cfg, "project.open", ""); err != nil {
		t.Fatalf("no binding -> no gate, got %v", err)
	}
	// The rebind mark must not create a gate that was not there.
	if err := withBindRebindWindow(func() error { return enforceSession(cfg, "project.open", "any-window") }); err != nil {
		t.Fatalf("rebind mark must not invent a gate without a binding: %v", err)
	}
	if bindRebindWindow.Load() {
		t.Fatal("bind rebind mark leaked")
	}
}

func TestSessionGuardEnforceOffStillBypasses(t *testing.T) {
	writeBoundSession(t, "w-old", "p1")
	t.Setenv("EASYCIRQ_SESSION_ENFORCE", "off")
	if err := enforceSession(&appConfig{}, "schematic.save", "w-new"); err != nil {
		t.Fatalf("EASYCIRQ_SESSION_ENFORCE=off must still bypass: %v", err)
	}
	if bindRebindWindow.Load() {
		t.Fatal("env bypass must not set the bind rebind mark")
	}
	// ... and the env bypass is not sticky for the explicit mark's bookkeeping.
	if err := withBindRebindWindow(func() error { return enforceSession(&appConfig{}, "schematic.save", "w-new") }); err != nil {
		t.Fatalf("bypass plus mark must pass: %v", err)
	}
}
