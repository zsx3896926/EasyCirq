package app

import (
	"strings"
	"testing"
)

// The platform can silently rename a requested designator; the place command
// must surface it instead of returning ok.
func TestVerifyPlacedDesignator(t *testing.T) {
	comps := []layoutComp{
		{Designator: "R8", X: 620, Y: 320},
		{Designator: "R6", X: 100, Y: 100},
	}
	if err := verifyPlacedDesignator(comps, "R8", 620, 320); err != nil {
		t.Fatalf("exact designator should verify: %v", err)
	}
	if err := verifyPlacedDesignator(comps, "R12", 620, 320); err == nil {
		t.Fatal("renamed designator must fail verification")
	} else if !strings.Contains(err.Error(), "R8@") {
		t.Fatalf("error should name the actual part near the requested spot: %v", err)
	}
	if err := verifyPlacedDesignator(comps, "R9", 900, 900); err != nil {
		t.Fatalf("nothing near the coordinates is not proof of a rename: %v", err)
	}
	if err := verifyPlacedDesignator(comps, "", 0, 0); err != nil {
		t.Fatalf("empty designator is a no-op: %v", err)
	}
}
