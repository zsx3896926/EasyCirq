package app

import "testing"

// A project with net-name variants / one-pin nets is a legitimate state: the
// non-strict run must not fail (otherwise the JSON report gets mixed with an
// error message in captured output), while --strict must still fail closed.
func TestSchNetsFindingsAreDataUnlessStrict(t *testing.T) {
	variants := schNetsReport{
		Total: 3,
		OK:    false,
		Variants: []schNetVariant{{
			Normalized: "33V",
			Nets:       []schNetInfo{{Name: "+3V3", Pins: 2}, {Name: "3V3", Pins: 5}},
		}},
	}
	if err := schNetsStrictVerdict(variants, false); err != nil {
		t.Fatalf("non-strict findings must not fail the command: %v", err)
	}
	if err := schNetsStrictVerdict(variants, true); err == nil {
		t.Fatal("strict mode must reject net-name variants")
	}

	lonely := schNetsReport{Total: 2, OK: true, Lonely: []schNetInfo{{Name: "LED_A", Pins: 1}}}
	if err := schNetsStrictVerdict(lonely, false); err != nil {
		t.Fatalf("non-strict one-pin net must not fail the command: %v", err)
	}
	if err := schNetsStrictVerdict(lonely, true); err == nil {
		t.Fatal("strict mode must reject one-pin nets")
	}

	clean := schNetsReport{Total: 4, OK: true}
	if err := schNetsStrictVerdict(clean, true); err != nil {
		t.Fatalf("clean report must pass strict: %v", err)
	}
}
