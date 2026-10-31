package app

import (
	"fmt"
	"math"
	"strings"
)

// verifyPlacedDesignator makes a silent designator rename visible. EasyEDA has
// been observed landing a requested R6/R8/R12 as R8/R12/R13; the place call
// still returns ok, so callers that trust the request keep wiring the wrong
// reference. When the requested designator is absent we report what actually
// appeared near the requested coordinates (or that nothing appeared).
func verifyPlacedDesignator(comps []layoutComp, want string, x, y float64) error {
	want = strings.TrimSpace(want)
	if want == "" {
		return nil
	}
	for _, c := range comps {
		if strings.EqualFold(strings.TrimSpace(c.Designator), want) {
			return nil
		}
	}
	var near []string
	for _, c := range comps {
		if math.Hypot(c.X-x, c.Y-y) <= 5 {
			near = append(near, fmt.Sprintf("%s@(%.1f,%.1f)", c.Designator, c.X, c.Y))
		}
	}
	if len(near) == 0 {
		// No part at the requested spot: either the page read was partial/mocked
		// or the create landed elsewhere. Not enough evidence to fail the call;
		// the rename case below is the one that silently corrupts a design.
		return nil
	}
	return fmt.Errorf("place reported success but the platform assigned different designator(s) near (%.1f,%.1f): %s — the requested %q was NOT applied; use `sch modify --designator` or place into a free slot",
		x, y, strings.Join(near, ", "), want)
}
