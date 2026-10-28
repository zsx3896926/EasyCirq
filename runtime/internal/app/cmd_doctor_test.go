package app

import (
	"archive/zip"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

// doctor/capabilities must be truthful even with no host attached: this test
// pins the "unknown, never supported" rule for probe-gated capabilities and the
// "unsupported, never inferred" rule for actions that do not exist.

func TestBuildCapabilitiesNoConnectorIsUnknownNotSupported(t *testing.T) {
	items := buildCapabilities(protocol.AllActions(), 0, nil)
	if len(items) == 0 {
		t.Fatal("expected capability items")
	}
	for _, it := range items {
		if it.Status == "supported" {
			t.Fatalf("%s reported supported with no connector connected", it.ID)
		}
		if it.ActionCount > 0 && it.Status != "unknown" {
			t.Fatalf("%s has %d actions but status = %s, want unknown", it.ID, it.ActionCount, it.Status)
		}
	}
}

func TestBuildCapabilitiesUnsupportedItemsStayUnsupported(t *testing.T) {
	items := buildCapabilities(protocol.AllActions(), 1, nil)
	byID := map[string]capabilityItem{}
	for _, it := range items {
		byID[it.ID] = it
	}
	for _, id := range []string{"gerber.export", "drill.export", "cpl.export"} {
		it, ok := byID[id]
		if !ok {
			t.Fatalf("missing capability %s", id)
		}
		if it.Status != "unsupported" {
			t.Fatalf("%s status = %s, want unsupported (no typed action exists)", id, it.Status)
		}
		if it.Reason == "" {
			t.Fatalf("%s must explain why it is unsupported", id)
		}
	}
}

func TestBuildCapabilitiesSupportedNeedsConnectorAndActions(t *testing.T) {
	items := buildCapabilities(protocol.AllActions(), 1, nil)
	seen := 0
	for _, it := range items {
		if it.Status == "supported" {
			seen++
			if it.ActionCount == 0 {
				t.Fatalf("%s supported with zero actions", it.ID)
			}
			if it.Reason == "" {
				t.Fatalf("%s supported without a reason", it.ID)
			}
		}
	}
	if seen == 0 {
		t.Fatal("expected at least one supported capability with a connector present")
	}
}

func TestDoctorVerdictBlockedWithoutDaemon(t *testing.T) {
	rep := doctorReport{
		Daemon:    doctorDaemon{Status: "stopped"},
		Connector: doctorConnector{Status: "disconnected"},
		Skill:     doctorSkill{Status: "installed"},
	}
	verdict, steps := doctorVerdict(rep)
	if verdict != "blocked" {
		t.Fatalf("verdict = %s, want blocked when daemon is stopped", verdict)
	}
	if len(steps) == 0 {
		t.Fatal("blocked verdict must carry next steps")
	}
}

func TestDoctorVerdictDegradedWithoutConnector(t *testing.T) {
	rep := doctorReport{
		Daemon:    doctorDaemon{Status: "running", PID: 1, Port: 23111},
		Connector: doctorConnector{Status: "disconnected"},
		Skill:     doctorSkill{Status: "installed"},
	}
	verdict, steps := doctorVerdict(rep)
	if verdict != "degraded" {
		t.Fatalf("verdict = %s, want degraded when daemon runs but no connector is attached", verdict)
	}
	if len(steps) == 0 {
		t.Fatal("degraded verdict should tell the user how to attach the connector")
	}
}

func TestDoctorVerdictFlagsStalePIDFile(t *testing.T) {
	rep := doctorReport{
		Daemon: doctorDaemon{Status: "running", PID: 42, Port: 23111, PIDFilePID: 7},
		Connector: doctorConnector{Status: "connected", Count: 1,
			ExpectedName: expectedConnectorName, ExpectedVer: expectedConnectorVersion},
		Skill: doctorSkill{Status: "installed"},
	}
	verdict, _ := doctorVerdict(rep)
	if verdict != "degraded" {
		t.Fatalf("verdict = %s, want degraded for a stale pid file", verdict)
	}
}

func TestSkillFrontMatterValue(t *testing.T) {
	text := "---\nname: easycirq\nversion: 1.2.3\ndescription: x\n---\n# body\n"
	if got := skillFrontMatterValue(text, "version"); got != "1.2.3" {
		t.Fatalf("version = %q", got)
	}
	if got := skillFrontMatterValue("no front matter", "version"); got != "" {
		t.Fatalf("expected empty for missing front matter, got %q", got)
	}
}

func TestReadConnectorManifestFromEext(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.eext")
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	zw := zip.NewWriter(f)
	w, err := zw.Create("extension.json")
	if err != nil {
		t.Fatal(err)
	}
	manifest := `{"name":"easycirq-connector","uuid":"a6e6b788551945b399e150d80efa6e31","version":"0.1.0","displayName":"d","publisher":"p","engines":{"eda":">=3.2.0"}}`
	if _, err := w.Write([]byte(manifest)); err != nil {
		t.Fatal(err)
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	m, err := readConnectorManifest(path)
	if err != nil {
		t.Fatalf("readConnectorManifest: %v", err)
	}
	if m.Name != "easycirq-connector" || m.Version != "0.1.0" {
		t.Fatalf("unexpected manifest: %+v", m)
	}
	if m.EngineEDA != ">=3.2.0" {
		t.Fatalf("engine = %q", m.EngineEDA)
	}
}

func TestReadConnectorManifestRejectsNonZip(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bad.eext")
	if err := os.WriteFile(path, []byte("not a zip"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := readConnectorManifest(path); err == nil {
		t.Fatal("expected an error for a non-zip .eext")
	} else if !strings.Contains(err.Error(), "eext") {
		t.Fatalf("error should mention the .eext package: %v", err)
	}
}
