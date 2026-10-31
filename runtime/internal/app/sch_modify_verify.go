package app

import (
	"fmt"
	"strings"
)

// modifiedDesignatorVerdict turns the post-modify page read into a verdict.
// Two real platform behaviours make this necessary: modify returned ok:false
// while the part HAD moved, and modify returned ok:true while the designator
// was unchanged. Callers that trust the ack keep wiring/renumbering the wrong
// part, so the ack is never the source of truth.
func modifiedDesignatorVerdict(comps []layoutComp, primitiveID, want string, dispatchErr error) error {
	want = strings.TrimSpace(want)
	if want == "" {
		return dispatchErr
	}
	var actual string
	found := false
	for _, c := range comps {
		if c.ID == primitiveID {
			actual = strings.TrimSpace(c.Designator)
			found = true
			break
		}
	}
	if !found {
		for _, c := range comps {
			if strings.EqualFold(strings.TrimSpace(c.Designator), want) {
				actual = strings.TrimSpace(c.Designator)
				found = true
				break
			}
		}
	}
	if !found {
		if dispatchErr != nil {
			return fmt.Errorf("%v — and the component %s is not on the page afterwards (the write did NOT land; re-read with `sch list` before retrying)", dispatchErr, primitiveID)
		}
		return fmt.Errorf("modify reported success but component %s is not on the page — re-read with `sch list`", primitiveID)
	}
	if strings.EqualFold(actual, want) {
		if dispatchErr != nil {
			// The ack said failure but the page shows the new designator: the
			// write DID take effect, so the caller must not retry blindly.
			return fmt.Errorf("%v — LANDED anyway: component %s is now %q (the write took effect despite the error; do not retry)", dispatchErr, primitiveID, actual)
		}
		return nil
	}
	if dispatchErr != nil {
		return fmt.Errorf("%v — LANDED anyway: component %s is now %q (the write took effect despite the error)", dispatchErr, primitiveID, actual)
	}
	return fmt.Errorf("modify reported success but designator is still %q, not %q (the rename was NOT applied)", actual, want)
}

// verifyModifiedDesignator reads the page back after a designator modify and
// reports what actually landed. Reads are best-effort: if the page cannot be
// read we fall back to the dispatch result rather than inventing a verdict.
func verifyModifiedDesignator(cfg *appConfig, window, primitiveID, want string, dispatchErr error) error {
	want = strings.TrimSpace(want)
	if want == "" {
		return dispatchErr
	}
	res, lerr := requestAction(cfg, "schematic.components.list", window, map[string]any{})
	if lerr != nil {
		return dispatchErr
	}
	comps, perr := parseLayoutComps(res.Result)
	if perr != nil || len(comps) == 0 {
		return dispatchErr
	}
	return modifiedDesignatorVerdict(comps, primitiveID, want, dispatchErr)
}
