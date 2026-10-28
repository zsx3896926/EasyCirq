package app

import (
	"fmt"
	"testing"
)

// pagePrimitives.pins compatibility.
//
// FIELD REPORT (GameForge-X1): a live EasyEDA Pro connector returned a complete
// pagePrimitives inventory PLUS an additive "pins" class, and compose refused
// the snapshot with "incomplete class inventory" because the guard compared the
// class COUNT instead of the required classes.
//
// The fixtures below are SYNTHETIC and shaped after the field report: the real
// captured response was not available on this machine (the reported path
// D:/Users/27675/... is not accessible), so this is a shaped regression, not a
// replay of captured host bytes. Replace/extend it when the sanitized field
// capture is available; the assertions must stay the same.
//
// What the fix must guarantee:
//   - an additive, known class (pins) no longer fails an otherwise complete snapshot;
//   - every required class is still enforced (missing one still fails);
//   - an UNKNOWN additive class still fails (it may be identity-bearing);
//   - a malformed known-extra class still fails.

func composeGuardCompletePage() map[string]any {
	page := map[string]any{}
	for _, kind := range []string{
		"components", "wires", "buses", "arcs", "circles", "rectangles",
		"polygons", "texts", "attributes", "objects",
	} {
		page[kind] = []any{}
	}
	return page
}

func composeGuardResult(page map[string]any) map[string]any {
	return map[string]any{
		"wiresAvailable":      true,
		"pinNetsAvailable":    true,
		"pagePrimitives":      page,
		"components":          []any{},
		"wires":               []any{},
		"connectivitySummary": zeroConnectivitySummary(),
	}
}

func zeroConnectivitySummary() map[string]any {
	return map[string]any{
		"scope": "activePage",
		"wires": float64(0), "buses": float64(0), "netflags": float64(0),
		"netports": float64(0), "netlabels": float64(0), "shortSymbols": float64(0),
	}
}

func TestComposeGuardAcceptsAdditivePinsClass(t *testing.T) {
	page := composeGuardCompletePage()
	page["pins"] = []any{
		map[string]any{"primitiveId": "pin-1", "number": "1", "net": "VCC"},
		map[string]any{"primitiveId": "pin-2", "number": "2", "net": "GND"},
	}
	if _, err := schComposeProtectedPage(composeGuardResult(page)); err != nil {
		t.Fatalf("additive pagePrimitives.pins must not fail the snapshot: %v", err)
	}
}

func TestComposeGuardStillRequiresEveryKnownClass(t *testing.T) {
	for _, missing := range []string{
		"components", "wires", "buses", "arcs", "circles",
		"rectangles", "polygons", "texts", "attributes", "objects",
	} {
		page := composeGuardCompletePage()
		delete(page, missing)
		if _, err := schComposeProtectedPage(composeGuardResult(page)); err == nil {
			t.Fatalf("missing required class %q must still be refused", missing)
		}
	}
}

func TestComposeGuardRejectsUnknownExtraClass(t *testing.T) {
	page := composeGuardCompletePage()
	page["holograms"] = []any{map[string]any{"primitiveId": "h1"}}
	_, err := schComposeProtectedPage(composeGuardResult(page))
	if err == nil {
		t.Fatal("an unrecognized primitive class must still be refused")
	}
	if got := fmt.Sprint(err); !containsAll(got, "holograms", "unrecognized") {
		t.Fatalf("error should name the unknown class and say unrecognized: %v", err)
	}
}

func TestComposeGuardRejectsMalformedPinsClass(t *testing.T) {
	page := composeGuardCompletePage()
	page["pins"] = "not-an-array"
	if _, err := schComposeProtectedPage(composeGuardResult(page)); err == nil {
		t.Fatal("malformed pagePrimitives.pins must be refused instead of ignored")
	}
}

func TestComposeGuardAcceptsSnapshotWithoutPinsClass(t *testing.T) {
	page := composeGuardCompletePage()
	if _, err := schComposeProtectedPage(composeGuardResult(page)); err != nil {
		t.Fatalf("legacy snapshots without pins must keep working: %v", err)
	}
}

func containsAll(s string, subs ...string) bool {
	for _, sub := range subs {
		found := false
		for i := 0; i+len(sub) <= len(s); i++ {
			if s[i:i+len(sub)] == sub {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}
