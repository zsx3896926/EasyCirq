package app

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func writeGate(t *testing.T, dir string, expires time.Time, verdict string, allowed bool) string {
	t.Helper()
	path := filepath.Join(dir, "gate.json")
	body := `{"schema":"easycirq-gate/v1","project":"P","page":"P1","verdict":"` +
		verdict + `","apply_allowed":` + map[bool]string{true: "true", false: "false"}[allowed] +
		`,"expires_at":"` + expires.UTC().Format(time.RFC3339) + `"}`
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("write gate: %v", err)
	}
	return path
}

func statusReportFixture(verdict string, fail, missing []string) *statusReport {
	report := &statusReport{Project: "P", Page: "P1", Verdict: verdict}
	for _, kpi := range fail {
		report.KPIs = append(report.KPIs, statusKPI{ID: kpi, Status: "fail"})
		report.Blockers = append(report.Blockers, statusBlocker{KPI: kpi, Reason: "r"})
	}
	for _, kpi := range missing {
		report.KPIs = append(report.KPIs, statusKPI{ID: kpi, Status: "missing"})
		report.Blockers = append(report.Blockers, statusBlocker{KPI: kpi, Reason: "缺证据"})
	}
	return report
}

func TestStatusNotMeasured(t *testing.T) {
	result := analyzeStatus(nil, "")
	if result.State != "not_measured" {
		t.Fatalf("state = %s, want not_measured", result.State)
	}
}

func TestStatusBlockedSeparatesDefectsFromMissingEvidence(t *testing.T) {
	report := statusReportFixture("BLOCKED", []string{"unconnected"}, []string{"pin_mux"})
	result := analyzeStatus(report, "")
	if result.State != "blocked" {
		t.Fatalf("state = %s, want blocked", result.State)
	}
	if len(result.Blockers) != 1 || result.Blockers[0].KPI != "unconnected" {
		t.Fatalf("blockers = %+v", result.Blockers)
	}
	if len(result.Missing) != 1 || result.Missing[0].KPI != "pin_mux" {
		t.Fatalf("missing = %+v", result.Missing)
	}
}

func TestStatusIncompleteWhenOnlyEvidenceIsMissing(t *testing.T) {
	report := statusReportFixture("BLOCKED", nil, []string{"pin_mux", "readback"})
	result := analyzeStatus(report, "")
	if result.State != "incomplete" {
		t.Fatalf("state = %s, want incomplete", result.State)
	}
	if len(result.Blockers) != 0 {
		t.Fatalf("blockers = %+v, want none", result.Blockers)
	}
}

func TestStatusReview(t *testing.T) {
	report := statusReportFixture("REVIEW", nil, nil)
	result := analyzeStatus(report, "")
	if result.State != "review" {
		t.Fatalf("state = %s, want review", result.State)
	}
}

func TestStatusReadyNeedsLiveGate(t *testing.T) {
	if testing.Short() {
		t.Skip("filesystem gate token")
	}
	dir := t.TempDir()
	gate := writeGate(t, dir, time.Now().Add(30*time.Minute), "PASS", true)
	report := statusReportFixture("PASS", nil, nil)
	result := analyzeStatus(report, gate)
	if result.State != "ready_to_write" {
		t.Fatalf("state = %s, want ready_to_write", result.State)
	}
}

func TestStatusExpiredGateIsStale(t *testing.T) {
	dir := t.TempDir()
	gate := writeGate(t, dir, time.Now().Add(-time.Minute), "PASS", true)
	report := statusReportFixture("PASS", nil, nil)
	result := analyzeStatus(report, gate)
	if result.State != "gate_stale" {
		t.Fatalf("state = %s, want gate_stale", result.State)
	}
}

func TestStatusMissingGateIsStale(t *testing.T) {
	report := statusReportFixture("PASS", nil, nil)
	result := analyzeStatus(report, filepath.Join(t.TempDir(), "absent.json"))
	if result.State != "gate_stale" {
		t.Fatalf("state = %s, want gate_stale", result.State)
	}
}

func TestStatusPlainLabelsCoverEveryKPI(t *testing.T) {
	for _, kpi := range []string{"unconnected", "cross_zone", "overlaps", "erc",
		"decoupling", "bom_map", "naming", "readback"} {
		if plainFor(kpi) == kpi {
			t.Fatalf("KPI %q has no plain label", kpi)
		}
	}
	if plainFor("unknown_kpi") != "unknown_kpi" {
		t.Fatal("unknown KPI must fall back to its id")
	}
}
