package daemon

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

const deliveryAction = "pcb.manufacture.gerber"
const buildAction = "schematic.component.place"

func writeGateFile(t *testing.T, dir string, token map[string]any) {
	t.Helper()
	path := filepath.Join(dir, ".easycirq", "gate.json")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir gate dir: %v", err)
	}
	raw, err := json.Marshal(token)
	if err != nil {
		t.Fatalf("marshal token: %v", err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatalf("write token: %v", err)
	}
}

func gateRequest(dir string) *protocol.Request {
	req := &protocol.Request{Action: deliveryAction, Project: "demo"}
	req.ID = "req-gate-test"
	req.OutputDir = dir
	return req
}

func validToken(expires time.Time) map[string]any {
	return map[string]any{
		"schema":        gateSchema,
		"project":       "demo",
		"page":          "P1",
		"verdict":       "PASS",
		"apply_allowed": true,
		"rounds_pass":   2,
		"expires_at":    expires.UTC().Format(time.RFC3339),
		"nonce":         "abc123",
		"kpis":          map[string]string{"unconnected": "pass"},
	}
}

func TestGateRequiredWithoutToken(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	resp := (&Server{}).checkMutationGate(gateRequest(dir))
	if resp == nil {
		t.Fatal("expected refusal without a gate token")
	}
	if resp.Error == nil || resp.Error.Code != "GATE_REQUIRED" {
		t.Fatalf("code = %+v, want GATE_REQUIRED", resp.Error)
	}
}

func TestGateAllowsPassToken(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	writeGateFile(t, dir, validToken(time.Now().Add(30*time.Minute)))
	if resp := (&Server{}).checkMutationGate(gateRequest(dir)); resp != nil {
		t.Fatalf("expected pass, got %+v", resp.Error)
	}
}

func TestGateRejectsExpiredToken(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	writeGateFile(t, dir, validToken(time.Now().Add(-time.Minute)))
	resp := (&Server{}).checkMutationGate(gateRequest(dir))
	if resp == nil || resp.Error == nil || resp.Error.Code != "GATE_EXPIRED" {
		t.Fatalf("expected GATE_EXPIRED, got %+v", resp)
	}
}

func TestGateRejectsBlockedToken(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	token := validToken(time.Now().Add(30 * time.Minute))
	token["verdict"] = "BLOCKED"
	token["apply_allowed"] = false
	writeGateFile(t, dir, token)
	resp := (&Server{}).checkMutationGate(gateRequest(dir))
	if resp == nil || resp.Error == nil || resp.Error.Code != "GATE_NOT_PASS" {
		t.Fatalf("expected GATE_NOT_PASS, got %+v", resp)
	}
}

func TestGateRejectsForeignProject(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	token := validToken(time.Now().Add(30 * time.Minute))
	token["project"] = "other-project"
	writeGateFile(t, dir, token)
	resp := (&Server{}).checkMutationGate(gateRequest(dir))
	if resp == nil || resp.Error == nil || resp.Error.Code != "GATE_PROJECT_MISMATCH" {
		t.Fatalf("expected GATE_PROJECT_MISMATCH, got %+v", resp)
	}
}

func TestGateWarnModeAllows(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "warn")
	dir := t.TempDir()
	if resp := (&Server{}).checkMutationGate(gateRequest(dir)); resp != nil {
		t.Fatalf("warn mode must allow, got %+v", resp.Error)
	}
}

func TestGateOffModeAllows(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "off")
	dir := t.TempDir()
	if resp := (&Server{}).checkMutationGate(gateRequest(dir)); resp != nil {
		t.Fatalf("off mode must allow, got %+v", resp.Error)
	}
}

func TestGateIgnoresReadActions(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	req := gateRequest(dir)
	req.Action = "schematic.components.list"
	if resp := (&Server{}).checkMutationGate(req); resp != nil {
		t.Fatalf("read action must not be gated, got %+v", resp.Error)
	}
}

func TestGateAcceptsProjectUUID(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	token := validToken(time.Now().Add(30 * time.Minute))
	token["project"] = "KPI-S5-Verify"
	token["project_uuid"] = "b8f1902cdd1648e9bae62b9c7170a397"
	writeGateFile(t, dir, token)

	req := gateRequest(dir)
	req.Project = "b8f1902cdd1648e9bae62b9c7170a397"
	if resp := (&Server{}).checkMutationGate(req); resp != nil {
		t.Fatalf("uuid-targeted write should pass, got %+v", resp.Error)
	}

	other := gateRequest(dir)
	other.Project = "deadbeefdeadbeefdeadbeefdeadbeef"
	resp := (&Server{}).checkMutationGate(other)
	if resp == nil || resp.Error == nil || resp.Error.Code != "GATE_PROJECT_MISMATCH" {
		t.Fatalf("foreign uuid must be refused, got %+v", resp)
	}
}

func TestBuildActionsAreNotGated(t *testing.T) {
	// Drawing is how a board comes into existence; an empty page can never pass
	// the offline check, so gating these would deadlock "build from scratch".
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	for _, action := range []string{
		buildAction,
		"schematic.wire.create",
		"schematic.netflag.create",
		"pcb.route.auto",
	} {
		req := gateRequest(t.TempDir())
		req.Action = action
		if resp := (&Server{}).checkMutationGate(req); resp != nil {
			t.Fatalf("%s is a build action and must not be gated, got %+v", action, resp.Error)
		}
	}
}

func TestDeliveryActionsAreGated(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	for _, action := range []string{
		"pcb.manufacture.gerber",
		"pcb.manufacture.cpl",
		"pcb.manufacture.netlist",
	} {
		req := gateRequest(t.TempDir())
		req.Action = action
		resp := (&Server{}).checkMutationGate(req)
		if resp == nil || resp.Error == nil || resp.Error.Code != "GATE_REQUIRED" {
			t.Fatalf("%s must require a token, got %+v", action, resp)
		}
	}
}

func TestGateOverridePath(t *testing.T) {
	t.Setenv("EASYCIRQ_GATE_MODE", "strict")
	dir := t.TempDir()
	custom := filepath.Join(dir, "custom-gate.json")
	t.Setenv("EASYCIRQ_GATE", custom)
	writeGateFile(t, dir, validToken(time.Now().Add(30*time.Minute)))
	// the default path has a token, the override does not: must refuse
	resp := (&Server{}).checkMutationGate(gateRequest(dir))
	if resp == nil || resp.Error == nil || resp.Error.Code != "GATE_REQUIRED" {
		t.Fatalf("expected GATE_REQUIRED from override path, got %+v", resp)
	}
}


