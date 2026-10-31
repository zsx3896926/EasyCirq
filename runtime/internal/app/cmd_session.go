package app

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"time"

	"github.com/spf13/cobra"
)

// sessionSchema stamps the bound-window file so a stale file from another
// version is rejected instead of silently used.
const sessionSchema = "easycirq-session/v1"

// bindRebindWindow is set ONLY while the `session bind` subcommand executes (see
// withBindRebindWindow). bind routes through project.open, which is a mutating
// action, so the window guard used to reject bind itself whenever the window had
// changed — and the only way to clear a degraded channel is to restart EasyEDA,
// which ALWAYS changes the windowId. That made the recovery path a deadlock: the
// one command that could repair the binding was refused by the binding guard, and
// operators had to delete .easycirq/session.json by hand.
//
// It is deliberately narrow: process-local, never env- or default-driven, and only
// the window-mismatch leg of enforceSession is skipped. Every ordinary mutating
// action still gets the full guard.
var bindRebindWindow atomic.Bool

// withBindRebindWindow marks this process as "session bind is rebinding the
// window" for the duration of fn, then clears the mark no matter how fn exits.
func withBindRebindWindow(fn func() error) error {
	bindRebindWindow.Store(true)
	defer bindRebindWindow.Store(false)
	return fn()
}

// sessionRecord is the single source of truth for "which window are we writing
// to". It exists because of the 2026-10-30 incident: `health` reported one
// window as healthy while writes were routed to a second, degraded window, and
// 109 connects were refused with no way to tell which window they hit.
type sessionRecord struct {
	Schema       string `json:"schema"`
	WindowID     string `json:"windowId"`
	ProjectUUID  string `json:"projectUuid"`
	ProjectName  string `json:"projectName,omitempty"`
	DocumentUUID string `json:"documentUuid,omitempty"`
	DocumentType string `json:"documentType,omitempty"`
	BoundAt      string `json:"boundAt"`
	Path         string `json:"path,omitempty"`
}

func sessionFilePath() string {
	if custom := strings.TrimSpace(os.Getenv("EASYCIRQ_SESSION_FILE")); custom != "" {
		return custom
	}
	return filepath.Join(".easycirq", "session.json")
}

func readSessionRecord() (sessionRecord, error) {
	var record sessionRecord
	path := sessionFilePath()
	raw, err := os.ReadFile(path)
	if err != nil {
		return record, fmt.Errorf("no session bound (%s): run `easycirq session bind --window <id> --project-uuid <uuid> --allow-discard-unsaved`", path)
	}
	if err := json.Unmarshal(raw, &record); err != nil {
		return record, fmt.Errorf("session file %s is unreadable: %w", path, err)
	}
	if record.Schema != sessionSchema {
		return record, fmt.Errorf("session file %s has schema %q; expected %q (re-bind)", path, record.Schema, sessionSchema)
	}
	record.Path = path
	return record, nil
}

func writeSessionRecord(record sessionRecord) error {
	path := sessionFilePath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	record.Schema = sessionSchema
	record.BoundAt = time.Now().Format(time.RFC3339)
	encoded, err := json.MarshalIndent(record, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(encoded, '\n'), 0o644)
}

// documentContext reads the live project/document identity from the connector.
func documentContext(cfg *appConfig, window string) (map[string]any, error) {
	body, err := postAction(cfg, "document.current", window, nil, defaultActionTimeout)
	if err != nil {
		return nil, err
	}
	var envelope struct {
		OK     bool           `json:"ok"`
		Result map[string]any `json:"result"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, fmt.Errorf("document.current returned unreadable JSON: %w", err)
	}
	if !envelope.OK {
		return nil, fmt.Errorf("document.current was refused: %s", strings.TrimSpace(string(body)))
	}
	return envelope.Result, nil
}

// channelDegraded reports the write-health flag of the daemon holding `window`.
// A missing window or an unreachable daemon is reported as an error so the gate
// fails closed instead of writing blind.
func channelDegraded(cfg *appConfig, window string) (bool, error) {
	portStart, portEnd, err := cfg.portRange()
	if err != nil {
		return false, err
	}
	client := &http.Client{Timeout: 3 * time.Second}
	for port := portStart; port <= portEnd; port++ {
		url := fmt.Sprintf("http://%s/health", net.JoinHostPort(cfg.host, fmt.Sprint(port)))
		resp, err := client.Get(url)
		if err != nil {
			continue
		}
		body, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		if readErr != nil {
			continue
		}
		var health map[string]any
		if err := json.Unmarshal(body, &health); err != nil {
			continue
		}
		if !healthHasWindow(health, window) {
			continue
		}
		return healthWindowDegraded(health, window), nil
	}
	return false, fmt.Errorf("no daemon reports window %q; start EasyEDA and check `easycirq health`", window)
}

// healthHasWindow walks the health payload for a window entry with the given id.
func healthHasWindow(health map[string]any, window string) bool {
	for _, entry := range collectJSONMaps(health, "windows") {
		if id, _ := entry["windowId"].(string); id == window {
			return true
		}
	}
	return false
}

// healthWindowDegraded reads writeHealth[window].degraded (missing => false).
func healthWindowDegraded(health map[string]any, window string) bool {
	found, _ := health["found"].(map[string]any)
	if found == nil {
		return false
	}
	raw, _ := found["raw"].(map[string]any)
	if raw == nil {
		return false
	}
	table, _ := raw["writeHealth"].(map[string]any)
	if table == nil {
		return false
	}
	entry, _ := table[window].(map[string]any)
	if entry == nil {
		return false
	}
	degraded, _ := entry["degraded"].(bool)
	return degraded
}

// collectJSONMaps gathers every []any stored under `key` anywhere in the tree.
func collectJSONMaps(node map[string]any, key string) []map[string]any {
	var out []map[string]any
	var walk func(value any)
	walk = func(value any) {
		switch typed := value.(type) {
		case map[string]any:
			if list, ok := typed[key].([]any); ok {
				for _, item := range list {
					if entry, ok := item.(map[string]any); ok {
						out = append(out, entry)
					}
				}
			}
			for _, child := range typed {
				walk(child)
			}
		case []any:
			for _, child := range typed {
				walk(child)
			}
		}
	}
	walk(node)
	return out
}

func newSessionCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var window string
	session := &cobra.Command{
		Use:   "session",
		Short: "Bind one window+project+document and gate writes on it (prevents wrong-window writes)",
	}

	bind := &cobra.Command{
		Use:   "bind",
		Short: "Open the project and record the bound window/project/document in .easycirq/session.json",
		Args:  cobra.NoArgs,
		Example: `  easycirq session bind --window <id> --project-uuid <uuid> --allow-discard-unsaved
  easycirq session bind --window <id> --project-uuid <uuid> --page-uuid <page> --allow-discard-unsaved`,
		RunE: func(cmd *cobra.Command, args []string) error {
			var projectUUID, pageUUID string
			var discard bool
			projectUUID, _ = cmd.Flags().GetString("project-uuid")
			pageUUID, _ = cmd.Flags().GetString("page-uuid")
			discard, _ = cmd.Flags().GetBool("allow-discard-unsaved")
			if strings.TrimSpace(window) == "" || strings.TrimSpace(projectUUID) == "" {
				return fmt.Errorf("session bind requires explicit --window and --project-uuid (never implicit)")
			}
			if !discard {
				return fmt.Errorf("session bind opens the project, which may discard unsaved data; save first, then pass --allow-discard-unsaved")
			}
			if cfg.project != "" || cfg.doc != "" {
				return fmt.Errorf("session bind pins the window explicitly; omit global --project/--doc routing")
			}
			return withBindRebindWindow(func() error {
				return bindSession(cfg, stdout, window, projectUUID, pageUUID)
			})
		},
	}
	bind.Flags().StringVar(&window, "window", "", "EasyEDA window ID to bind (required)")
	bind.Flags().String("project-uuid", "", "project UUID to open and bind (required)")
	bind.Flags().String("page-uuid", "", "optional schematic page UUID")
	bind.Flags().Bool("allow-discard-unsaved", false, "acknowledge openProject may discard unsaved data")

	status := &cobra.Command{
		Use:   "status",
		Short: "Show the bound session and whether it still matches the live window/document",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			record, err := readSessionRecord()
			if err != nil {
				return err
			}
			report := map[string]any{"session": record, "live": nil, "matches": false}
			context, err := documentContext(cfg, record.WindowID)
			if err == nil {
				report["live"] = context
				report["matches"] = contextProjectUUID(context) == record.ProjectUUID &&
					(record.DocumentUUID == "" || contextDocumentUUID(context) == record.DocumentUUID)
			} else {
				report["liveError"] = err.Error()
			}
			if degraded, degradedErr := channelDegraded(cfg, record.WindowID); degradedErr == nil {
				report["degraded"] = degraded
			} else {
				report["degradedError"] = degradedErr.Error()
			}
			return writeJSON(stdout, report)
		},
	}

	gate := &cobra.Command{
		Use:   "gate",
		Short: "Exit non-zero unless the bound window still matches the project and the channel is healthy",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			record, err := readSessionRecord()
			if err != nil {
				return err
			}
			context, err := documentContext(cfg, record.WindowID)
			if err != nil {
				return err
			}
			if contextProjectUUID(context) != record.ProjectUUID {
				return fmt.Errorf("session stale: window %s reports project %s, bound %s", record.WindowID,
					contextProjectUUID(context), record.ProjectUUID)
			}
			if record.DocumentUUID != "" && contextDocumentUUID(context) != record.DocumentUUID {
				return fmt.Errorf("session stale: window %s reports document %s, bound %s", record.WindowID,
					contextDocumentUUID(context), record.DocumentUUID)
			}
			degraded, err := channelDegraded(cfg, record.WindowID)
			if err != nil {
				return err
			}
			if degraded {
				return fmt.Errorf("channel for window %s is degraded; restart EasyEDA before writing", record.WindowID)
			}
			return writeJSON(stdout, map[string]any{"ok": true, "windowId": record.WindowID,
				"projectUuid": record.ProjectUUID})
		},
	}

	session.AddCommand(bind, status, gate)
	return session
}

// bindSession is the body of `session bind` once the CLI argument checks passed:
// open the project, confirm the live identity, refuse a degraded channel, then
// OVERWRITE .easycirq/session.json with the new window/project/document.
//
// It MUST run inside withBindRebindWindow: the project.open it dispatches is a
// mutating action, and the recorded window is exactly what a restart invalidates.
func bindSession(cfg *appConfig, stdout io.Writer, window, projectUUID, pageUUID string) error {
	if _, _, err := projectTransferRequest(cfg, window, "open", projectUUID, pageUUID); err != nil {
		return err
	}
	context, err := documentContext(cfg, window)
	if err != nil {
		return err
	}
	bound := contextProjectUUID(context)
	if bound != "" && !strings.EqualFold(bound, projectUUID) {
		return fmt.Errorf("bound window %s reports project %s, expected %s — refusing to record a mismatched session", window, bound, projectUUID)
	}
	degraded, err := channelDegraded(cfg, window)
	if err != nil {
		return err
	}
	if degraded {
		return fmt.Errorf("window %s is degraded; recover the channel (restart EasyEDA) before binding", window)
	}
	record := sessionRecord{
		WindowID:     window,
		ProjectUUID:  projectUUID,
		ProjectName:  stringOrEmpty(context["projectName"]),
		DocumentUUID: contextDocumentUUID(context),
		DocumentType: contextDocumentType(context),
	}
	if record.DocumentUUID == "" {
		record.DocumentUUID = pageUUID
	}
	// writeSessionRecord truncates, so a stale binding is replaced rather than
	// merged — that is what makes this the repair path after window churn.
	if err := writeSessionRecord(record); err != nil {
		return err
	}
	written, err := readSessionRecord()
	if err != nil {
		return err
	}
	return writeJSON(stdout, written)
}

// document.current reports the official EasyEDA identity keys: `uuid`,
// `parentProjectUuid` and `documentTypeCode`. These accessors map them to the
// session vocabulary so bind/status/gate agree on one spelling.
func contextProjectUUID(context map[string]any) string {
	if value := stringOrEmpty(context["parentProjectUuid"]); value != "" {
		return value
	}
	return stringOrEmpty(context["projectUuid"])
}

func contextDocumentUUID(context map[string]any) string {
	if value := stringOrEmpty(context["uuid"]); value != "" {
		return value
	}
	return stringOrEmpty(context["documentUuid"])
}

func contextDocumentType(context map[string]any) string {
	if value := stringOrEmpty(context["documentType"]); value != "" {
		return value
	}
	if code, ok := context["documentTypeCode"].(float64); ok && code == 1 {
		return "schematic"
	}
	return ""
}

func stringOrEmpty(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

// enforceSession is the write-path gate: once a session is bound, every
// mutating action must target the bound window. Unbound workspaces keep the
// legacy behaviour (no file -> no gate), so existing scripts and tests are not
// broken; binding is the opt-in that makes wrong-window writes impossible.
//
// The only exception is `session bind` itself (bindRebindWindow): a restart
// changes windowId, and that command exists precisely to repair the binding.
//
// Set EASYCIRQ_SESSION_ENFORCE=off to bypass (diagnostics only).
func enforceSession(cfg *appConfig, action, window string) error {
	if !actionMutates(action) {
		return nil
	}
	if strings.EqualFold(strings.TrimSpace(os.Getenv("EASYCIRQ_SESSION_ENFORCE")), "off") {
		return nil
	}
	record, err := readSessionRecord()
	if err != nil {
		return nil // no bound session -> legacy behaviour
	}
	if strings.TrimSpace(window) == "" {
		if cfg.project != "" && strings.EqualFold(cfg.project, record.ProjectUUID) {
			return nil // project routing resolves to the bound project
		}
		return fmt.Errorf("no --window on a mutating action while a session is bound to %s (%s); pass --window %s or --project %s",
			record.WindowID, record.Path, record.WindowID, record.ProjectUUID)
	}
	// Rebinding the window is the ONE action allowed to name a different window:
	// a restart changes windowId, and the binding must be repairable from inside
	// the CLI (see bindRebindWindow). The project leg is still checked, so a bind
	// cannot silently retarget writes to another project's window.
	if bindRebindWindow.Load() {
		if cfg.project != "" && !strings.EqualFold(cfg.project, record.ProjectUUID) {
			return fmt.Errorf("session bind routes project %s but the bound session records project %s (%s); re-bind with the recorded project or drop --project",
				cfg.project, record.ProjectUUID, record.Path)
		}
		return nil
	}
	if !strings.EqualFold(window, record.WindowID) {
		return fmt.Errorf("session mismatch: action targets window %s but the bound window is %s (%s); re-bind or use the bound window",
			window, record.WindowID, record.Path)
	}
	return nil
}
