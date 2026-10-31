package app

import "testing"

func TestPlaceDesignatorConflict(t *testing.T) {
	existing := []string{"U1", "R1", "R2", "C1"}
	cases := []struct {
		name string
		want string
		fail bool
	}{
		{"free designator", "R3", false},
		{"empty wants no check", "", false},
		{"duplicate stops the place", "R2", true},
		{"case insensitive duplicate", "r2", true},
		{"whitespace trimmed", "  C1 ", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := placeDesignatorConflict(existing, tc.want)
			if tc.fail && err == nil {
				t.Fatalf("want=%q should be refused", tc.want)
			}
			if !tc.fail && err != nil {
				t.Fatalf("want=%q should be allowed: %v", tc.want, err)
			}
		})
	}
}
