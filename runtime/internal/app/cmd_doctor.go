package app

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime/debug"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
	"github.com/zsx3896926/EasyCirq/runtime/internal/version"
)

// The doctor command is the single diagnosis entry point of the integrated
// toolchain. It answers, in one machine-readable document, the question the two
// former skill sets answered in two different places: which skill version is
// installed, which runtime build is on disk, which daemon is actually running,
// whether the connector in the EasyEDA window is OUR connector, which protocol
// version both sides speak, and whether a legacy upstream agent is still around
// (detected, never used).
//
// Design rules it must keep:
//   - disk state and running state are separate fields, never merged;
//   - every component reports a real path or build identity, not a guess;
//   - a missing or unverifiable piece is "blocked"/"unknown" with a next step,
//     never silently "ok";
//   - it never writes to the host and never touches the legacy toolchain.

// expectedConnectorName/Version describe the connector build that this runtime
// ships with. The release build overrides them with -ldflags so the CLI cannot
// silently disagree with the packaged .eext.
var (
	expectedConnectorName    = version.ConnectorName
	expectedConnectorVersion = version.ConnectorVersion
)

const (
	legacyServiceName  = "easyeda-agent"
	legacyPortStart    = 60832
	legacyPortEnd      = 60841
	doctorServiceCheck = protocol.ServiceName
)

type doctorReport struct {
	Schema      string          `json:"schema"`
	GeneratedAt string          `json:"generatedAt"`
	Verdict     string          `json:"verdict"` // ok | degraded | blocked
	Runtime     doctorRuntime   `json:"runtime"`
	Skill       doctorSkill     `json:"skill"`
	Daemon      doctorDaemon    `json:"daemon"`
	Connector   doctorConnector `json:"connector"`
	Protocol    doctorProtocol  `json:"protocol"`
	Host        doctorHost      `json:"host"`
	Legacy      doctorLegacy    `json:"legacy"`
	Checks      []healthCheck   `json:"checks"`
	NextSteps   []string        `json:"nextSteps,omitempty"`
}

type doctorRuntime struct {
	Name        string `json:"name"`
	Version     string `json:"version"`
	Executable  string `json:"executable"`
	SHA256      string `json:"sha256,omitempty"`
	VCSRevision string `json:"vcsRevision,omitempty"`
	VCSTime     string `json:"vcsTime,omitempty"`
	VCSModified bool   `json:"vcsModified,omitempty"`
	GoVersion   string `json:"goVersion,omitempty"`
	OnDisk      bool   `json:"onDisk"`
}

type doctorSkillInstall struct {
	Client  string `json:"client"`
	Dir     string `json:"dir"`
	Present bool   `json:"present"`
	Version string `json:"version,omitempty"`
}

type doctorSkill struct {
	Name      string               `json:"name"`
	Status    string               `json:"status"` // installed | missing | unknown
	Installed []doctorSkillInstall `json:"installed"`
}

type doctorDaemon struct {
	Status     string `json:"status"` // running | stopped
	PID        int    `json:"pid,omitempty"`
	Port       int    `json:"port,omitempty"`
	Version    string `json:"version,omitempty"`
	StateDir   string `json:"stateDir,omitempty"`
	LogPath    string `json:"logPath,omitempty"`
	PIDFile    string `json:"pidFile,omitempty"`
	PIDFilePID int    `json:"pidFilePid,omitempty"`
	// PIDFilePID and PID disagree when a stale pid file survives a crashed
	// daemon; the running instance is authoritative and the mismatch is
	// reported instead of hidden.
	PIDFileMatches bool `json:"pidFileMatches"`
}

type doctorWindow struct {
	WindowID           string   `json:"windowId"`
	ConnectorVersion   string   `json:"connectorVersion"`
	EasyEDAVersion     string   `json:"easyedaVersion"`
	Capabilities       []string `json:"capabilities,omitempty"`
	HostKind           string   `json:"hostKind,omitempty"`
	ProjectUUID        string   `json:"projectUuid,omitempty"`
	ProjectName        string   `json:"projectName,omitempty"`
	DocumentUUID       string   `json:"documentUuid,omitempty"`
	DocumentType       string   `json:"documentType,omitempty"`
	PageVisibility     string   `json:"pageVisibility,omitempty"`
	ConnectedAt        string   `json:"connectedAt,omitempty"`
	ConnectorVersionOK *bool    `json:"connectorVersionOk,omitempty"`
}

type doctorConnector struct {
	Status         string         `json:"status"` // connected | disconnected
	Count          int            `json:"count"`
	ExpectedName   string         `json:"expectedName"`
	ExpectedVer    string         `json:"expectedVersion"`
	VersionMatches []string       `json:"versionMismatch,omitempty"`
	Windows        []doctorWindow `json:"windows,omitempty"`
}

type doctorProtocol struct {
	Service         string `json:"service"`
	WireVersion     string `json:"wireVersion"`
	Handshake       string `json:"handshake"`
	EnvelopeVersion string `json:"envelopeVersion"`
}

type doctorHost struct {
	EasyEDAVersion string `json:"easyedaVersion,omitempty"`
	HostKind       string `json:"hostKind,omitempty"`
	Compatibility  string `json:"compatibility,omitempty"`
	CompatibilityN string `json:"compatibilityNotes,omitempty"`
}

type doctorLegacy struct {
	Ports    string `json:"ports"`
	Detected bool   `json:"detected"`
	Service  string `json:"service,omitempty"`
	Port     int    `json:"port,omitempty"`
	Used     bool   `json:"used"`
	Note     string `json:"note"`
}

// ── command ──────────────────────────────────────────────────────────────

func newDoctorCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Diagnose the integrated toolchain (skill, runtime, daemon, connector, protocol)",
		Long: "Report the installed skill version, the runtime build identity, the actually " +
			"running daemon, the connector loaded in each EasyEDA window, the wire protocol " +
			"version both sides speak, and any legacy easyeda-agent process (detected, never " +
			"used). Disk state and running state are reported separately. Exit code is non-zero " +
			"when the toolchain cannot reach the host.",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			rep := collectDoctorReport(cfg)
			enc := json.NewEncoder(stdout)
			enc.SetIndent("", "  ")
			if err := enc.Encode(rep); err != nil {
				return fmt.Errorf("encode doctor: %w", err)
			}
			printDoctorSummary(stderr, rep)
			if rep.Verdict == "blocked" {
				return errActionFailed
			}
			return nil
		},
	}
}

// collectDoctorReport performs read-only probes. It never mutates host state and
// never starts a daemon.
func collectDoctorReport(cfg *appConfig) doctorReport {
	now := time.Now().UTC().Format(time.RFC3339)
	rep := doctorReport{
		Schema:      "easycirq-doctor/v1",
		GeneratedAt: now,
		Runtime:     runtimeIdentity(),
		Protocol: doctorProtocol{
			Service:         protocol.ServiceName,
			WireVersion:     protocol.WireVersion,
			Handshake:       "daemon→connector {type:handshake,service,version}",
			EnvelopeVersion: protocol.WireVersion,
		},
	}
	rep.Skill = scanSkillInstalls()

	portStart, portEnd, err := cfg.portRange()
	if err == nil {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		result := scanHealth(ctx, hostPortOptions{host: cfg.host, portStart: portStart, portEnd: portEnd})
		cancel()
		rep.Daemon = daemonIdentity(result, cfg.host)
		rep.Connector, rep.Host = connectorIdentity(result)
		rep.Checks = append(rep.Checks, healthChecks(result)...)
	} else {
		rep.Daemon = doctorDaemon{Status: "stopped"}
		rep.Connector = doctorConnector{Status: "disconnected", ExpectedName: expectedConnectorName, ExpectedVer: expectedConnectorVersion}
	}

	legacyCtx, legacyCancel := context.WithTimeout(context.Background(), 2*time.Second)
	rep.Legacy = probeLegacy(legacyCtx, cfg.host)
	legacyCancel()

	rep.Checks = append(rep.Checks, doctorSkillCheck(rep.Skill), doctorLegacyCheck(rep.Legacy))
	rep.Verdict, rep.NextSteps = doctorVerdict(rep)
	return rep
}

func runtimeIdentity() doctorRuntime {
	rt := doctorRuntime{Name: version.Name, Version: version.Version}
	if exe, err := os.Executable(); err == nil {
		rt.Executable = exe
		if data, err := os.ReadFile(exe); err == nil {
			sum := sha256.Sum256(data)
			rt.SHA256 = hex.EncodeToString(sum[:])
			rt.OnDisk = true
		} else {
			rt.OnDisk = false
		}
	}
	if info, ok := debug.ReadBuildInfo(); ok {
		rt.GoVersion = info.GoVersion
		for _, s := range info.Settings {
			switch s.Key {
			case "vcs.revision":
				rt.VCSRevision = s.Value
			case "vcs.time":
				rt.VCSTime = s.Value
			case "vcs.modified":
				rt.VCSModified = s.Value == "true"
			}
		}
	}
	return rt
}

func stateDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".easycirq")
}

func daemonIdentity(result healthResult, host string) doctorDaemon {
	d := doctorDaemon{Status: "stopped", StateDir: stateDir()}
	if result.Found != nil {
		var raw struct {
			PID     int    `json:"pid"`
			Version string `json:"version"`
		}
		_ = json.Unmarshal(result.Found.Raw, &raw)
		d.Status = "running"
		d.Port = result.Found.Port
		d.PID = raw.PID
		d.Version = raw.Version
	}
	if dir := d.StateDir; dir != "" {
		d.LogPath = filepath.Join(dir, "daemon.log")
		d.PIDFile = filepath.Join(dir, "daemon.pid")
		if data, err := os.ReadFile(d.PIDFile); err == nil {
			var pid int
			if _, err := fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &pid); err == nil {
				d.PIDFilePID = pid
				d.PIDFileMatches = pid == d.PID && pid != 0
			}
		}
	}
	return d
}

func connectorIdentity(result healthResult) (doctorConnector, doctorHost) {
	c := doctorConnector{
		Status:       "disconnected",
		ExpectedName: expectedConnectorName,
		ExpectedVer:  expectedConnectorVersion,
	}
	h := doctorHost{}
	if result.Found == nil {
		return c, h
	}
	var raw struct {
		Windows []doctorWindow `json:"windows"`
	}
	if err := json.Unmarshal(result.Found.Raw, &raw); err != nil {
		return c, h
	}
	c.Windows = raw.Windows
	c.Count = len(raw.Windows)
	if c.Count > 0 {
		c.Status = "connected"
	}
	eda := map[string]bool{}
	kinds := map[string]bool{}
	for _, w := range raw.Windows {
		if w.EasyEDAVersion != "" {
			eda[w.EasyEDAVersion] = true
		}
		if w.HostKind != "" {
			kinds[w.HostKind] = true
		}
		if w.ConnectorVersion != expectedConnectorVersion {
			c.VersionMatches = append(c.VersionMatches,
				fmt.Sprintf("window %s runs connector %s, expected %s",
					shortID(w.WindowID), display(w.ConnectorVersion), expectedConnectorVersion))
		}
	}
	h.EasyEDAVersion = joinSorted(eda)
	h.HostKind = joinSorted(kinds)
	if result.HostCompatibility != nil {
		h.Compatibility = result.HostCompatibility.Verdict
		h.CompatibilityN = hostCompatibilitySummary(*result.HostCompatibility)
	}
	return c, h
}

// probeLegacy checks whether the upstream easyeda-agent daemon is still running
// on its historical port range. Finding it is informational: the EasyCirq runtime
// never dials it and never proxies through it.
func probeLegacy(ctx context.Context, host string) doctorLegacy {
	leg := doctorLegacy{
		Ports: fmt.Sprintf("%d-%d", legacyPortStart, legacyPortEnd),
		Used:  false,
		Note:  "legacy upstream easyeda-agent daemon; detected only, never used by this runtime",
	}
	client := http.Client{Timeout: 500 * time.Millisecond}
	for port := legacyPortStart; port <= legacyPortEnd; port++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			fmt.Sprintf("http://%s:%d/health", host, port), nil)
		if err != nil {
			continue
		}
		resp, err := client.Do(req)
		if err != nil {
			continue
		}
		body, readErr := readBoundedResponse(resp.Body, healthResponseBodyLimit)
		_ = resp.Body.Close()
		if readErr != nil || resp.StatusCode < 200 || resp.StatusCode >= 300 {
			continue
		}
		if svc := serviceName(body); svc == legacyServiceName {
			leg.Detected = true
			leg.Service = svc
			leg.Port = port
			return leg
		}
	}
	return leg
}

// skillCandidates lists the client skill directories the integrated installer
// manages. A repo-local skill directory is reported as "repo" so a developer can
// see that the checked-out skill is the one the runtime ships with.
func skillCandidates() []doctorSkillInstall {
	home, err := os.UserHomeDir()
	if err != nil {
		home = ""
	}
	defs := []struct{ client, rel string }{
		{"codex", filepath.Join(".codex", "skills", "easycirq")},
		{"claude", filepath.Join(".claude", "skills", "easycirq")},
		{"agents", filepath.Join(".agents", "skills", "easycirq")},
	}
	out := make([]doctorSkillInstall, 0, len(defs)+2)
	for _, d := range defs {
		dir := ""
		if home != "" {
			dir = filepath.Join(home, d.rel)
		}
		out = append(out, doctorSkillInstall{Client: d.client, Dir: dir})
	}
	if wd, err := os.Getwd(); err == nil {
		out = append(out, doctorSkillInstall{Client: "repo", Dir: filepath.Join(wd, "easycirq")})
	}
	for _, extra := range strings.Split(os.Getenv("EASYCIRQ_SKILL_DIRS"), ",") {
		extra = strings.TrimSpace(extra)
		if extra == "" {
			continue
		}
		out = append(out, doctorSkillInstall{Client: "custom", Dir: extra})
	}
	return out
}

func scanSkillInstalls() doctorSkill {
	sk := doctorSkill{Name: "easycirq", Status: "missing"}
	cands := skillCandidates()
	installs := make([]doctorSkillInstall, 0, len(cands))
	for _, c := range cands {
		if c.Dir == "" {
			continue
		}
		if st, err := os.Stat(c.Dir); err != nil || !st.IsDir() {
			installs = append(installs, c)
			continue
		}
		c.Present = true
		if data, err := os.ReadFile(filepath.Join(c.Dir, ".version")); err == nil {
			c.Version = strings.TrimSpace(string(data))
		}
		if data, err := os.ReadFile(filepath.Join(c.Dir, "SKILL.md")); err == nil {
			if v := skillFrontMatterValue(string(data), "version"); v != "" && c.Version == "" {
				c.Version = v
			}
		}
		installs = append(installs, c)
	}
	sk.Installed = installs
	for _, c := range installs {
		if c.Present {
			sk.Status = "installed"
			break
		}
	}
	return sk
}

// skillFrontMatterValue reads a `key: value` pair from YAML front matter.
func skillFrontMatterValue(text, key string) string {
	if !strings.HasPrefix(text, "---") {
		return ""
	}
	rest := text[3:]
	if idx := strings.Index(rest, "\n---"); idx >= 0 {
		rest = rest[:idx]
	}
	for _, line := range strings.Split(rest, "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) == 2 && strings.TrimSpace(parts[0]) == key {
			return strings.TrimSpace(parts[1])
		}
	}
	return ""
}

func doctorSkillCheck(sk doctorSkill) healthCheck {
	if sk.Status == "installed" {
		var owners []string
		for _, c := range sk.Installed {
			if c.Present {
				label := c.Client
				if c.Version != "" {
					label += " " + c.Version
				}
				owners = append(owners, label)
			}
		}
		return healthCheck{Name: "skill", Status: "ok",
			Detail: fmt.Sprintf("easycirq 已安装（%s）", strings.Join(owners, ", "))}
	}
	return healthCheck{Name: "skill", Status: "warn",
		Detail: "没有找到已安装的 design-hardware Skill",
		Fix:    "运行 `distribution/Manage-Skill.ps1 install`（或附带的安装包）安装 Skill；单独运行 easycirq 不会安装它"}
}

func doctorLegacyCheck(leg doctorLegacy) healthCheck {
	if leg.Detected {
		return healthCheck{Name: "legacy", Status: "ok",
			Detail: fmt.Sprintf("检测到旧 easyeda-agent daemon（%s:%d），本工具链不使用它（端口/服务名/配置目录均已隔离）", "127.0.0.1", leg.Port)}
	}
	return healthCheck{Name: "legacy", Status: "ok",
		Detail: "未检测到旧 easyeda-agent daemon（或已停止）"}
}

func doctorVerdict(rep doctorReport) (string, []string) {
	verdict := "ok"
	var steps []string

	if rep.Daemon.Status != "running" {
		verdict = "blocked"
		steps = append(steps, "启动自有 daemon：`easycirq daemon start`（端口 23111，状态目录 ~/.easycirq）")
	}
	if rep.Connector.Count == 0 {
		if verdict == "ok" {
			verdict = "degraded"
		}
		steps = append(steps,
			"在 EasyEDA Pro 导入自有连接器 "+expectedConnectorName+" v"+expectedConnectorVersion+
				"（`easycirq connector path` 可打印 .eext 路径），然后在扩展设置中允许外部交互，并重启 EasyEDA 使其加载")
	}
	if len(rep.Connector.VersionMatches) > 0 && verdict == "ok" {
		verdict = "degraded"
		steps = append(steps, "连接器版本与运行时不一致：重新导入与本运行时配套的 .eext，再重启 EasyEDA")
	}
	if rep.Skill.Status != "installed" && verdict == "ok" {
		verdict = "degraded"
	}
	if rep.Daemon.Status == "running" && rep.Daemon.PIDFilePID != 0 && !rep.Daemon.PIDFileMatches {
		if verdict == "ok" {
			verdict = "degraded"
		}
		steps = append(steps, fmt.Sprintf("pid 文件（%d）与运行实例（%d）不一致：daemon 可能非正常退出过，可用 `easycirq daemon restart` 清理",
			rep.Daemon.PIDFilePID, rep.Daemon.PID))
	}
	return verdict, steps
}

func printDoctorSummary(w io.Writer, rep doctorReport) {
	fmt.Fprintf(w, "easycirq doctor — verdict: %s\n", rep.Verdict)
	fmt.Fprintf(w, "  runtime   %s %s  (%s)\n", rep.Runtime.Name, rep.Runtime.Version, rep.Runtime.Executable)
	fmt.Fprintf(w, "  skill     %s\n", rep.Skill.Status)
	if rep.Daemon.Status == "running" {
		fmt.Fprintf(w, "  daemon    running pid=%d port=%d %s\n", rep.Daemon.PID, rep.Daemon.Port, display(rep.Daemon.Version))
	} else {
		fmt.Fprintln(w, "  daemon    stopped")
	}
	fmt.Fprintf(w, "  connector %s (%d window(s), expected %s v%s)\n",
		rep.Connector.Status, rep.Connector.Count, rep.Connector.ExpectedName, rep.Connector.ExpectedVer)
	if rep.Host.EasyEDAVersion != "" {
		fmt.Fprintf(w, "  host      EasyEDA Pro %s (%s)\n", rep.Host.EasyEDAVersion, rep.Host.HostKind)
	}
	fmt.Fprintf(w, "  protocol  %s wire %s\n", rep.Protocol.Service, rep.Protocol.WireVersion)
	for _, c := range rep.Checks {
		mark := "✓"
		switch c.Status {
		case "warn":
			mark = "⚠"
		case "fail":
			mark = "✗"
		}
		fmt.Fprintf(w, "  %s %-10s %s\n", mark, c.Name, c.Detail)
		if c.Fix != "" {
			fmt.Fprintf(w, "      → %s\n", c.Fix)
		}
	}
	for _, s := range rep.NextSteps {
		fmt.Fprintf(w, "  next: %s\n", s)
	}
}

func shortID(id string) string {
	if len(id) <= 8 {
		return id
	}
	return id[:8]
}

func joinSorted(set map[string]bool) string {
	if len(set) == 0 {
		return ""
	}
	items := make([]string, 0, len(set))
	for k := range set {
		items = append(items, k)
	}
	sort.Strings(items)
	return strings.Join(items, ", ")
}
