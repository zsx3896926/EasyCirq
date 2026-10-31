package app

import (
	"bytes"
	"strings"
	"testing"
)

func doctorFixture(daemon, connector, skill string, next ...string) doctorReport {
	rep := doctorReport{Verdict: "blocked", NextSteps: next}
	rep.Runtime.Name = "easycirq"
	rep.Runtime.Version = "1.1.0"
	rep.Daemon.Status = daemon
	rep.Daemon.Port = 23111
	rep.Connector.Status = connector
	rep.Skill.Status = skill
	rep.Host.EasyEDAVersion = "4.1.78"
	if daemon == "running" && connector == "connected" && skill == "installed" {
		rep.Verdict = "ok"
	}
	return rep
}

func TestSetupLinesMapStates(t *testing.T) {
	lines := setupLines(doctorFixture("running", "connected", "installed"))
	if len(lines) != 4 {
		t.Fatalf("lines = %d, want 4", len(lines))
	}
	for _, line := range lines {
		if !line.OK {
			t.Fatalf("%s should be ok: %+v", line.Label, line)
		}
	}
	if !strings.Contains(lines[1].State, "23111") {
		t.Fatalf("daemon line should name the port: %+v", lines[1])
	}
	if !strings.Contains(lines[2].State, "4.1.78") {
		t.Fatalf("connector line should name the host version: %+v", lines[2])
	}
}

func TestSetupLinesShowFailures(t *testing.T) {
	lines := setupLines(doctorFixture("stopped", "disconnected", "missing"))
	if lines[1].OK || lines[2].OK || lines[3].OK {
		t.Fatalf("expected three failures: %+v", lines)
	}
}

func TestRenderSetupReady(t *testing.T) {
	var buf bytes.Buffer
	renderSetup(doctorFixture("running", "connected", "installed"), &buf)
	out := buf.String()
	if !strings.Contains(out, "一切就绪") {
		t.Fatalf("ready output should say so: %s", out)
	}
}

func TestRenderSetupBlockedPrintsSteps(t *testing.T) {
	var buf bytes.Buffer
	renderSetup(doctorFixture("stopped", "disconnected", "installed",
		"启动 daemon：easycirq daemon start",
		"在 EasyEDA 导入连接器并允许外部交互"), &buf)
	out := buf.String()
	if !strings.Contains(out, "还差一步") {
		t.Fatalf("blocked output should say what is left: %s", out)
	}
	if !strings.Contains(out, "1. 启动 daemon") || !strings.Contains(out, "2. 在 EasyEDA") {
		t.Fatalf("next steps should be numbered: %s", out)
	}
	if !strings.Contains(out, "easycirq setup") {
		t.Fatalf("should tell the customer to re-run setup: %s", out)
	}
}

func TestRenderSetupBlockedWithoutSteps(t *testing.T) {
	var buf bytes.Buffer
	renderSetup(doctorFixture("stopped", "disconnected", "installed"), &buf)
	out := buf.String()
	if !strings.Contains(out, "重新运行 easycirq setup") {
		t.Fatalf("empty next steps should still give an action: %s", out)
	}
}
