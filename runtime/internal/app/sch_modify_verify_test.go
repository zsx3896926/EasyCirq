package app

import (
	"errors"
	"strings"
	"testing"
)

// The platform has returned ok:false while the part moved, and ok:true while the
// rename was never applied. Both must be reported as what actually landed.
func TestModifiedDesignatorVerdict(t *testing.T) {
	comps := []layoutComp{
		{ID: "id-a", Designator: "R21"},
		{ID: "id-b", Designator: "C7"},
	}
	cases := []struct {
		name     string
		comps    []layoutComp
		id       string
		want     string
		dispatch error
		wantSub  string
		wantErr  bool
	}{
		{name: "applied", comps: comps, id: "id-a", want: "R21"},
		{name: "not applied", comps: comps, id: "id-a", want: "R22", wantErr: true, wantSub: "the rename was NOT applied"},
		{name: "error but landed", comps: comps, id: "id-a", want: "R21", dispatch: errors.New("boom"), wantErr: true, wantSub: "LANDED anyway"},
		{name: "error and absent", comps: comps, id: "id-zzz", want: "R99", dispatch: errors.New("boom"), wantErr: true, wantSub: "did NOT land"},
		{name: "ok but absent", comps: comps, id: "id-zzz", want: "R99", wantErr: true, wantSub: "not on the page"},
		{name: "empty want is a pass-through", comps: comps, id: "id-a", want: ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := modifiedDesignatorVerdict(tc.comps, tc.id, tc.want, tc.dispatch)
			if tc.wantErr && err == nil {
				t.Fatalf("expected an error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if tc.wantSub != "" && !strings.Contains(err.Error(), tc.wantSub) {
				t.Fatalf("error %q should mention %q", err.Error(), tc.wantSub)
			}
		})
	}
}
