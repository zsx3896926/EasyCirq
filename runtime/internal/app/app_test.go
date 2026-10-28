package app

import (
	"bytes"
	"strings"
	"testing"

	"github.com/zsx3896926/hardware-design-skill/runtime/internal/version"
)

func TestRunVersion(t *testing.T) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer

	code := Run([]string{"version"}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("expected exit 0, got %d: %s", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), version.Name) {
		t.Fatalf("version output missing project name: %q", stdout.String())
	}
}

func TestRunUnknownCommand(t *testing.T) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer

	code := Run([]string{"wat"}, &stdout, &stderr)
	if code != 1 {
		t.Fatalf("expected exit 1, got %d", code)
	}
	if !strings.Contains(stderr.String(), "unknown command") {
		t.Fatalf("stderr missing unknown command message: %q", stderr.String())
	}
}

func TestRunUnknownSubcommand(t *testing.T) {
	for _, args := range [][]string{
		{"sch", "not-a-command"},
		{"pcb", "not-a-command"},
		{"project", "not-a-command"},
		{"pcb", "config", "not-a-command"},
	} {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			var stdout bytes.Buffer
			var stderr bytes.Buffer
			if code := Run(args, &stdout, &stderr); code != 1 {
				t.Fatalf("expected exit 1, got %d; stdout=%q stderr=%q", code, stdout.String(), stderr.String())
			}
			if !strings.Contains(stderr.String(), "unknown command") {
				t.Fatalf("stderr missing unknown command message: %q", stderr.String())
			}
		})
	}
}

func TestRunSubcommandGroupHelp(t *testing.T) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	if code := Run([]string{"sch"}, &stdout, &stderr); code != 0 {
		t.Fatalf("expected exit 0, got %d: %s", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), "Schematic operations") {
		t.Fatalf("group help missing: %q", stdout.String())
	}
}

func TestParsePortRange(t *testing.T) {
	start, end, err := parsePortRange("23111-23120")
	if err != nil {
		t.Fatalf("parsePortRange returned error: %v", err)
	}
	if start != 23111 || end != 23120 {
		t.Fatalf("unexpected range: %d-%d", start, end)
	}
}
