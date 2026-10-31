package app

import (
	"bytes"
	"strings"
	"testing"
	"time"
)

func cardReportFixture(verdict string, fail, missing []string) *statusReport {
	report := &statusReport{Project: "P", Page: "P1", Verdict: verdict}
	report.Stability.ApplyAllowed = strings.EqualFold(verdict, "PASS")
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

func TestCardBlockedSeparatesAdviceFromMissing(t *testing.T) {
	result := analyzeCard(cardReportFixture("BLOCKED", []string{"unconnected"}, []string{"bom_map"}), "", "")
	if result.State != "blocked" {
		t.Fatalf("state = %s, want blocked", result.State)
	}
	if len(result.Blockers) != 1 || result.Blockers[0].KPI != "unconnected" {
		t.Fatalf("blockers = %+v", result.Blockers)
	}
	if result.Blockers[0].Advice == "" {
		t.Fatal("a real defect must carry advice")
	}
	if len(result.Missing) != 1 || result.Missing[0].KPI != "bom_map" {
		t.Fatalf("missing = %+v", result.Missing)
	}
	if result.Missing[0].Advice != "" {
		t.Fatal("a missing check is not a defect: it must not carry fix advice")
	}
}

func TestCardIncompleteWhenOnlyEvidenceMissing(t *testing.T) {
	result := analyzeCard(cardReportFixture("BLOCKED", nil, []string{"pin_mux"}), "", "")
	if result.State != "incomplete" {
		t.Fatalf("state = %s, want incomplete", result.State)
	}
}

func TestCardReadyWithoutExplicitGate(t *testing.T) {
	result := analyzeCard(cardReportFixture("PASS", nil, nil), "/nonexistent/gate.json", "")
	if result.State != "ready" {
		t.Fatalf("state = %s, want ready (no gate was demanded)", result.State)
	}
}

func TestCardRequiresLiveGateWhenDemanded(t *testing.T) {
	dir := t.TempDir()
	gate := writeGate(t, dir, time.Now().Add(30*time.Minute), "PASS", true)
	result := analyzeCard(cardReportFixture("PASS", nil, nil), gate, gate)
	if result.State != "ready" {
		t.Fatalf("state = %s, want ready", result.State)
	}
	expired := writeGate(t, dir, time.Now().Add(-time.Minute), "PASS", true)
	result = analyzeCard(cardReportFixture("PASS", nil, nil), expired, expired)
	if result.State != "gate_stale" {
		t.Fatalf("state = %s, want gate_stale", result.State)
	}
}

func TestCardNotMeasured(t *testing.T) {
	result := analyzeCard(nil, "", "")
	if result.State != "not_measured" {
		t.Fatalf("state = %s, want not_measured", result.State)
	}
}

func TestRenderCardShowsCountsAndNext(t *testing.T) {
	result := analyzeCard(cardReportFixture("BLOCKED", []string{"unconnected"}, []string{"readback"}), "", "")
	var buf bytes.Buffer
	out := renderCard(result)
	buf.WriteString(out)
	text := buf.String()
	if !strings.Contains(text, "还不能打样") {
		t.Fatalf("headline missing: %s", text)
	}
	if !strings.Contains(text, "必查 0/2 通过") {
		t.Fatalf("counts missing: %s", text)
	}
	if !strings.Contains(text, "下一步：") {
		t.Fatalf("next step missing: %s", text)
	}
}
