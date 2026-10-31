package app

import (
	"testing"

	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

// Task-start deliverable check (field lesson from GameForge-X1):
// an existing API must never be reported as a verified capability, and a
// deliverable with no typed action and no GUI path must be "unsupported"
// rather than silently omitted.

func TestDeliverablesReportApiUntestedByDefault(t *testing.T) {
	items := buildDeliverables(protocol.AllActions(), 1, nil)
	if len(items) == 0 {
		t.Fatal("expected deliverable items")
	}
	for _, it := range items {
		if it.Status == "measured" {
			t.Fatalf("%s claims measured without a recorded host run", it.ID)
		}
		if it.Reason == "" {
			t.Fatalf("%s has no reason", it.ID)
		}
	}
}

func TestDeliverablesGuiOnlyMeansNoTypedAction(t *testing.T) {
	items := buildDeliverables(protocol.AllActions(), 1, nil)
	byID := map[string]deliverableItem{}
	for _, it := range items {
		byID[it.ID] = it
	}
	// The rule, not a fixed list: gui_only means "no typed action backs this,
	// only the official GUI export". gerber/drill/cpl stopped being gui_only on
	// 2026-10-28 when pcb.manufacture.gerber/.cpl landed, so a hard-coded
	// expectation for those ids went stale.
	for _, it := range items {
		if it.Status == "gui_only" {
			if len(it.Actions) != 0 {
				t.Fatalf("%s is gui_only but claims actions: %v", it.ID, it.Actions)
			}
			if !it.HostPath {
				t.Fatalf("%s is gui_only without a GUI path", it.ID)
			}
		}
		if it.Status == "measured" && len(it.Actions) == 0 {
			t.Fatalf("%s is measured without any typed action", it.ID)
		}
	}
	for _, id := range []string{"export.gerber", "export.drill", "export.cpl"} {
		it, ok := byID[id]
		if !ok {
			t.Fatalf("missing deliverable %s", id)
		}
		if len(it.Actions) == 0 {
			t.Fatalf("%s should now have a typed action (pcb.manufacture.*)", id)
		}
		if it.Status == "gui_only" {
			t.Fatalf("%s still reports gui_only although actions exist", id)
		}
	}
}

func TestDeliverablesCorePathsHaveActions(t *testing.T) {
	items := buildDeliverables(protocol.AllActions(), 0, nil)
	byID := map[string]deliverableItem{}
	for _, it := range items {
		byID[it.ID] = it
	}
	for _, id := range []string{"schematic.capture", "pcb.sync", "pcb.stackup", "pcb.routing", "pcb.drc", "export.bom"} {
		it, ok := byID[id]
		if !ok {
			t.Fatalf("missing deliverable %s", id)
		}
		if len(it.Actions) == 0 {
			t.Fatalf("%s has no backing typed action but should have some", id)
		}
		if it.Status != "api_untested" {
			t.Fatalf("%s status = %s, want api_untested before any host run", id, it.Status)
		}
	}
}

func TestDeliverablesMeasuredOnlyWithEvidence(t *testing.T) {
	items := buildDeliverables(protocol.AllActions(), 1, map[string]bool{"pcb.drc": true})
	for _, it := range items {
		if it.ID == "pcb.drc" {
			if it.Status != "measured" {
				t.Fatalf("pcb.drc status = %s, want measured when evidence is recorded", it.Status)
			}
			return
		}
	}
	t.Fatal("pcb.drc deliverable missing")
}
