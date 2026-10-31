package app

import (
	"fmt"
	"strings"
)

// placeDesignatorConflict reports a designator collision before a placement is
// dispatched. Placing with --designator must be idempotent-safe: the platform
// can land the primitive and still answer with a geometry error, which is how a
// duplicate R2 ended up on a real page (2026-10-30 RetroCam-01). Refusing the
// collision up front keeps the page clean without a place→list→modify round trip.
func placeDesignatorConflict(existing []string, want string) error {
	want = strings.TrimSpace(want)
	if want == "" {
		return nil
	}
	var hits []string
	for _, des := range existing {
		if strings.EqualFold(strings.TrimSpace(des), want) {
			hits = append(hits, strings.TrimSpace(des))
		}
	}
	if len(hits) == 0 {
		return nil
	}
	return fmt.Errorf("designator %q already exists on this page (%d instance(s): %s) — pick another --designator or delete the old instance first (`sch prim-delete --ids <id>`); refusing to place a duplicate",
		want, len(hits), strings.Join(hits, ", "))
}
