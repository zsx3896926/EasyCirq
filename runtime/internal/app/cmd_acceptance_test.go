package app

import (
	"strings"
	"testing"
)

func acceptanceFixture(checks ...acceptanceCheck) *acceptanceFile {
	return &acceptanceFile{Schema: "easycirq-acceptance/v1", Project: "P",
		Board: "B1", Checks: checks}
}

func TestAcceptanceMissingRecord(t *testing.T) {
	result := analyzeAcceptance(nil)
	if result.State != "missing" {
		t.Fatalf("state = %s, want missing", result.State)
	}
}

func TestAcceptanceAllPassWithEvidence(t *testing.T) {
	result := analyzeAcceptance(acceptanceFixture(
		acceptanceCheck{ID: "solder", Title: "焊接", Result: "pass", Evidence: "照片 IMG_001.jpg"},
		acceptanceCheck{ID: "power", Title: "上电", Result: "pass", Evidence: "3.3V 实测 3.28V"},
		acceptanceCheck{ID: "function", Title: "功能", Result: "pass", Evidence: "56℃ 触发蜂鸣"},
	))
	if result.State != "accepted" {
		t.Fatalf("state = %s, want accepted: %+v", result.State, result.Lines)
	}
}

func TestAcceptancePassWithoutEvidenceIsUnknown(t *testing.T) {
	result := analyzeAcceptance(acceptanceFixture(
		acceptanceCheck{ID: "solder", Title: "焊接", Result: "pass", Evidence: ""},
		acceptanceCheck{ID: "power", Title: "上电", Result: "pass", Evidence: "3.28V"},
		acceptanceCheck{ID: "function", Title: "功能", Result: "pass", Evidence: "响了"},
	))
	if result.State != "pending" {
		t.Fatalf("state = %s, want pending", result.State)
	}
	for _, line := range result.Lines {
		if line.Title == "焊接" {
			if line.Result != "unknown" {
				t.Fatalf("pass without evidence must be unknown: %+v", line)
			}
			if !strings.Contains(line.Why, "证据") {
				t.Fatalf("should explain why: %+v", line)
			}
		}
	}
}

func TestAcceptanceFailIsFailed(t *testing.T) {
	result := analyzeAcceptance(acceptanceFixture(
		acceptanceCheck{ID: "solder", Title: "焊接", Result: "pass", Evidence: "照片"},
		acceptanceCheck{ID: "power", Title: "上电", Result: "fail", Evidence: "输出 0V"},
		acceptanceCheck{ID: "function", Title: "功能", Result: "pass", Evidence: "无"},
	))
	if result.State != "failed" {
		t.Fatalf("state = %s, want failed", result.State)
	}
}

func TestAcceptanceMissingRequiredCheckIsPending(t *testing.T) {
	result := analyzeAcceptance(acceptanceFixture(
		acceptanceCheck{ID: "solder", Title: "焊接", Result: "pass", Evidence: "照片"},
	))
	if result.State != "pending" {
		t.Fatalf("state = %s, want pending", result.State)
	}
	missing := 0
	for _, line := range result.Lines {
		if line.Result == "unknown" && strings.Contains(line.Why, "还没记录") {
			missing++
		}
	}
	if missing != 2 {
		t.Fatalf("missing required checks = %d, want 2: %+v", missing, result.Lines)
	}
}

func TestRenderAcceptanceShowsMarksAndNext(t *testing.T) {
	result := analyzeAcceptance(acceptanceFixture(
		acceptanceCheck{ID: "solder", Title: "焊接", Result: "pass", Evidence: "照片"},
		acceptanceCheck{ID: "power", Title: "上电", Result: "fail", Evidence: "0V"},
		acceptanceCheck{ID: "function", Title: "功能", Result: "pass", Evidence: "无"},
	))
	out := renderAcceptance(result)
	if !strings.Contains(out, "不能算可用") {
		t.Fatalf("headline missing: %s", out)
	}
	if !strings.Contains(out, "✗") {
		t.Fatalf("failed mark missing: %s", out)
	}
	if !strings.Contains(out, "下一步：") {
		t.Fatalf("next step missing: %s", out)
	}
}
