package app

import "testing"

// Designators are project-scoped in EasyEDA; a duplicate makes the platform
// silently renumber one part on save, so the audit must catch it.
func TestDesignatorDuplicates(t *testing.T) {
	clean := []designatorEntry{
		{Page: "P1", Designator: "R1"},
		{Page: "P1", Designator: "R2"},
		{Page: "P2", Designator: "R21"},
	}
	if got := designatorDuplicates(clean); len(got) != 0 {
		t.Fatalf("clean project must report no duplicates, got %v", got)
	}

	dup := []designatorEntry{
		{Page: "P1", Designator: "R6"},
		{Page: "P3", Designator: "R6"},
		{Page: "P3", Designator: "C7"},
	}
	got := designatorDuplicates(dup)
	if len(got) != 1 {
		t.Fatalf("expected exactly one duplicate, got %v", got)
	}
	if pages, ok := got["R6"]; !ok || len(pages) != 2 {
		t.Fatalf("R6 must be reported on two pages, got %v", got)
	}

	if got := designatorDuplicates(nil); len(got) != 0 {
		t.Fatalf("empty input must be clean, got %v", got)
	}
	if got := designatorDuplicates([]designatorEntry{{Page: "P1", Designator: "  "}}); len(got) != 0 {
		t.Fatalf("blank designators must be ignored, got %v", got)
	}
}
