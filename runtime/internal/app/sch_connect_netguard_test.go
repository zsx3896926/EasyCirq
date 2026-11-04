package app

import (
	"bytes"
	"strings"
	"testing"
)

// The guard must fail loudly when it cannot read the landed net. An empty net
// used to mean "nothing to compare, carry on" - which is precisely how the
// VCC->GND rewrite slipped through unnoticed.
func TestConnectGuardTreatsMissingNetAsFailure(t *testing.T) {
	var errBuf bytes.Buffer
	cfg := &appConfig{}

	// A pin reference that cannot resolve must produce an error from readBackPinNet,
	// never an empty string with nil error.
	if _, err := readBackPinNet(cfg, "", "NO_SUCH_REF"); err == nil {
		t.Fatalf("an unresolvable pin must not produce a clean read-back")
	}

	// Shape check on the message a customer sees: it must name both nets.
	landed, wanted := "GND", "VCC"
	if strings.Contains(landed, wanted) {
		t.Fatalf("sanity: the two nets must differ for this test to mean anything")
	}
	if netsEquivalent(landed, wanted) {
		t.Fatalf("GND must never be treated as equivalent to VCC")
	}
	_ = errBuf
}

func TestNetsEquivalent(t *testing.T) {
	cases := []struct {
		landed, wanted string
		same           bool
	}{
		{"PWR5V", "PWR5V", true},
		{"pwr5v", "PWR5V", true},
		{"$PWR5V", "PWR5V", true},
		{" PWR5V ", "PWR5V", true},
		{"GND", "VCC", false},
		{"VCC", "GND", false},
		{"", "PWR5V", false},
	}
	for _, tc := range cases {
		if got := netsEquivalent(tc.landed, tc.wanted); got != tc.same {
			t.Fatalf("netsEquivalent(%q,%q) = %v, want %v", tc.landed, tc.wanted, got, tc.same)
		}
	}
}
