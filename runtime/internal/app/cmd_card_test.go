package app

import (
	"bytes"
	"os"
	"path/filepath"
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

func TestCardWithoutPCBScopesTheClaimToTheSchematic(t *testing.T) {
	// A green schematic does not make an orderable board. Without PCB input the
	// headline must not read as a whole-board verdict.
	report := cardReportFixture("PASS", nil, nil)
	card := analyzeCard(report, "", "")
	if card.State != "ready" {
		t.Fatalf("state = %s, want ready", card.State)
	}
	if !strings.Contains(card.Headline, "板子还没检查") {
		t.Fatalf("headline must scope the claim: %q", card.Headline)
	}
}

func TestCardWithCleanPCBClaimsWholeBoard(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "drc.json")
	os.WriteFile(path, []byte(`{"passed":true,"total":0,"violations":[]}`), 0o644)

	report := cardReportFixture("PASS", nil, nil)
	card := analyzeCard(report, "", "")
	mergePCB(&card, path)
	if card.State != "ready" {
		t.Fatalf("state = %s, want ready", card.State)
	}
	if !strings.Contains(card.Headline, "可以下单") {
		t.Fatalf("headline = %q", card.Headline)
	}
	if card.PCB == nil || !card.PCB.Passed {
		t.Fatalf("pcb summary missing: %+v", card.PCB)
	}
}

func TestCardWithDirtyPCBIsBlocked(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "drc.json")
	os.WriteFile(path, []byte(`{"passed":false,"total":2,"violations":[{"rule":"Clearance Error","message":"(NTC_MID): e5 to (GND) distance is 0mil"}]}`), 0o644)

	report := cardReportFixture("PASS", nil, nil)
	card := analyzeCard(report, "", "")
	mergePCB(&card, path)
	if card.State != "blocked" {
		t.Fatalf("state = %s, want blocked", card.State)
	}
	if !strings.Contains(card.Headline, "板子") {
		t.Fatalf("headline = %q", card.Headline)
	}
	out := renderCard(card)
	if !strings.Contains(out, "板子检查：未通过") {
		t.Fatalf("rendered card hides the PCB verdict:\n%s", out)
	}
}

func TestCardShowsTheConcreteItemBehindABlocker(t *testing.T) {
	report := cardReportFixture("BLOCKED", []string{"unconnected"}, []string{})
	report.Blockers[0].Reason = "未连接/悬空 实测 1 count > 门限 0（BB_VIN）"
	card := analyzeCard(report, "", "")
	out := renderCard(card)
	if !strings.Contains(out, "BB_VIN") {
		t.Fatalf("card does not name the offending net:\n%s", out)
	}
	if !strings.Contains(out, "有引脚或网络没有接上：BB_VIN") {
		t.Fatalf("the name should follow the plain label:\n%s", out)
	}
}

func TestCardBlockerWithoutNamesHasNoDanglingColon(t *testing.T) {
	report := cardReportFixture("BLOCKED", []string{"unconnected"}, []string{})
	report.Blockers[0].Reason = "未连接/悬空 实测 1 count > 门限 0"
	card := analyzeCard(report, "", "")
	out := renderCard(card)
	if strings.Contains(out, "没有接上：\n") {
		t.Fatalf("a blocker without names must not render a trailing colon:\n%s", out)
	}
}
