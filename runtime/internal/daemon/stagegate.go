package daemon

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

// gateSchema is the on-disk format the offline KPI checker issues.
const gateSchema = "easycirq-gate/v1"

// gateToken is the write permission issued by the offline checker
// (easycirq/scripts/sch_kpi.py). It is bound to a project and page, carries the
// PASS verdict and the stability result, and expires.
type gateToken struct {
	Schema       string            `json:"schema"`
	Project      string            `json:"project"`
	ProjectUUID  string            `json:"project_uuid,omitempty"`
	Page         string            `json:"page"`
	Verdict      string            `json:"verdict"`
	ApplyAllowed bool              `json:"apply_allowed"`
	ExpiresAt    string            `json:"expires_at"`
	Nonce        string            `json:"nonce"`
	RoundsPass   int               `json:"rounds_pass"`
	KPIs         map[string]string `json:"kpis"`
}

// deliverySpecs indexes the actions the gate protects: those that make a claim
// about the board's readiness (manufacturing data, netlists, exports).
//
// It is deliberately NOT every mutating action. Drawing a board - placing,
// wiring, routing - is how a board comes into existence, and an empty page can
// never pass the offline check, so gating every write deadlocks "build it from
// scratch". The invariant the objective needs is "no delivery claim without
// evidence", which is what GateRequired marks. ActionSpec.GateRequired is the
// single source of truth, so a new delivery action is covered automatically.
var deliverySpecs = sync.OnceValue(func() map[string]protocol.ActionSpec {
	index := map[string]protocol.ActionSpec{}
	for _, action := range protocol.AllActions() {
		if action.GateRequired {
			index[action.Name] = action
		}
	}
	return index
})

// gateMode resolves the enforcement mode: strict (default), warn (log and allow),
// or off. It exists so a customer who cannot run the checker yet is not bricked,
// while the shipping default still refuses ungated writes. An explicit value in
// EASYCIRQ_GATE_MODE always wins; with nothing set, unit-test binaries default to
// off so daemon behaviour tests are not forced to carry a token.
func gateMode() string {
	if raw := strings.ToLower(strings.TrimSpace(os.Getenv("EASYCIRQ_GATE_MODE"))); raw != "" {
		switch raw {
		case "off", "warn", "strict":
			return raw
		}
	}
	if flag.Lookup("test.v") != nil {
		// go test registers -test.v; on Windows the binary is .test.exe, so a
		// suffix check would miss it.
		return "off"
	}
	return "strict"
}

// gatePathFor resolves where the token lives. The CLI runs in the project
// workspace, so <OutputDir>/.easycirq/gate.json is the natural place; the env
// override keeps CI and out-of-tree callers possible.
func gatePathFor(req *protocol.Request) string {
	if override := strings.TrimSpace(os.Getenv("EASYCIRQ_GATE")); override != "" {
		return override
	}
	dir := strings.TrimSpace(req.OutputDir)
	if dir == "" {
		if cwd, err := os.Getwd(); err == nil {
			dir = cwd
		}
	}
	return filepath.Join(dir, ".easycirq", "gate.json")
}

func readGateToken(path string) (*gateToken, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var token gateToken
	if err := json.Unmarshal(raw, &token); err != nil {
		return nil, fmt.Errorf("gate token is not valid JSON: %w", err)
	}
	return &token, nil
}

// checkMutationGate refuses a mutating typed action when there is no live,
// PASS verdict for the target project. A read action, or gate mode warn/off,
// passes straight through.
func (s *Server) checkMutationGate(req *protocol.Request) *protocol.Response {
	if _, mutates := deliverySpecs()[req.Action]; !mutates {
		return nil
	}
	mode := gateMode()
	if mode == "off" {
		return nil
	}

	path := gatePathFor(req)
	refuse := func(code, message, detail string) *protocol.Response {
		resp := errorResponse(req.ID, code, message, detail)
		return &resp
	}

	token, err := readGateToken(path)
	if err != nil {
		if mode == "warn" {
			return nil
		}
		return refuse("GATE_REQUIRED",
			"这次写入被拦下了：还没有这一页通过离线检查的通行证",
			fmt.Sprintf("先跑离线门禁（verdict=PASS 且 apply_allowed=true）签发 %s，当前读不到：%v。临时放行请设 EASYCIRQ_GATE_MODE=warn", path, err))
	}
	if token.Schema != gateSchema {
		return refuse("GATE_INVALID",
			"离线检查通行证格式不对",
			fmt.Sprintf("期望 %s，读到 %q", gateSchema, token.Schema))
	}
	if !strings.EqualFold(token.Verdict, "PASS") || !token.ApplyAllowed {
		return refuse("GATE_NOT_PASS",
			"这一页的离线检查还没通过，不能写入",
			fmt.Sprintf("通行证 verdict=%s apply_allowed=%v；先修掉阻断项再重跑门禁", token.Verdict, token.ApplyAllowed))
	}
	if token.ExpiresAt != "" {
		if expires, parseErr := time.Parse(time.RFC3339, token.ExpiresAt); parseErr == nil {
			if time.Now().UTC().After(expires) {
				return refuse("GATE_EXPIRED",
					"离线检查结果已过期，需要重新测量",
					fmt.Sprintf("通行证 %s 过期（%s）；重新跑一轮门禁即可", path, token.ExpiresAt))
			}
		}
	}
	if req.Project != "" && (token.Project != "" || token.ProjectUUID != "") {
		// a caller may target the project by name or by uuid; the token is
		// valid for either, but never for a different project
		matches := strings.EqualFold(req.Project, token.Project) ||
			(token.ProjectUUID != "" && strings.EqualFold(req.Project, token.ProjectUUID))
		if !matches {
			return refuse("GATE_PROJECT_MISMATCH",
				"通行证不属于这个工程",
				fmt.Sprintf("通行证签给 %q（uuid %q），本次写入目标是 %q",
					token.Project, token.ProjectUUID, req.Project))
		}
	}
	return nil
}

// Workflow stage files are retained for historical reporting and compatibility
// with `easycirq workflow` / `easycirq pcb stage`. They are no longer an
// authorization mechanism for typed actions. These no-op hooks intentionally
// remain source-compatible with older integrations while dispatch proceeds from
// live document evidence.
func (s *Server) checkStageGate(_ *protocol.Request) *protocol.Response { return nil }

// A successful action no longer cascades into stage invalidation or demands a
// new sign-off. Explicit workflow commands may still edit their own records.
func (s *Server) maybeInvalidateStage(_ *protocol.Request, _ *protocol.Response) {}
