package app

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/zsx3896926/EasyCirq/runtime/internal/protocol"
)

// The capabilities command is the negotiation entry point required by the
// integrated toolchain: every capability is reported per item as
// supported / unsupported / unknown WITH a reason, and never inferred from an
// EDA version number alone. "supported" here means "the typed action exists in
// this runtime build AND a connector is connected to this daemon"; whether the
// host actually honours a given call is still decided per call and proven by
// readback evidence.
//
// The reporting shape also carries the axes the skill needs to plan a write:
// whether the call is synchronous or long-running, whether it returns values,
// whether a readback verification action exists, and whether it can touch the
// whole board.

type capabilityItem struct {
	ID             string   `json:"id"`
	Status         string   `json:"status"` // supported | unsupported | unknown
	Reason         string   `json:"reason"`
	Mode           string   `json:"mode"`   // sync | sync-long
	ReturnsResult  bool     `json:"returnsResult"`
	Readback       bool     `json:"readback"`
	WholeBoard     bool     `json:"wholeBoardImpact"`
	ActionCount    int      `json:"actionCount"`
	SampleActions  []string `json:"sampleActions,omitempty"`
	Caveat         []string `json:"caveats,omitempty"`
}

type capabilitiesReport struct {
	Schema      string                 `json:"schema"`
	GeneratedAt string                 `json:"generatedAt"`
	Protocol    doctorProtocol         `json:"protocol"`
	Connector   capabilitiesConnector  `json:"connector"`
	Host        doctorHost             `json:"host"`
	Summary     map[string]int         `json:"summary"`
	Items       []capabilityItem       `json:"items"`
	// Deliverables answers the task-start question "what can this toolchain
	// actually deliver for THIS job" with five honest states, never by reading
	// the EDA version number: measured / api_untested / gui_only /
	// needs_development / unsupported.
	Deliverables []deliverableItem    `json:"deliverables"`
	Notes        []string             `json:"notes"`
}

// deliverableItem is one deliverable a design task needs (schematic, PCB sync,
// stackup, routing, DRC, 3D, BOM, Gerber, drill, CPL).
type deliverableItem struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Reason string `json:"reason"`
	// Actions lists the typed actions that back this deliverable (empty when
	// the toolchain has none, i.e. gui_only / unsupported).
	Actions []string `json:"actions,omitempty"`
	// HostPath says whether the official EasyEDA GUI can produce it even if the
	// toolchain has no typed action (manual export + human evidence).
	HostPath bool   `json:"hostGuiPath"`
	Evidence string `json:"evidence"`
}

type capabilitiesConnector struct {
	Status   string   `json:"status"` // connected | disconnected
	Count    int      `json:"count"`
	Reported []string `json:"reported,omitempty"`
}

type capabilityDef struct {
	id      string
	note    []string
	needsProbe bool
	match   func(protocol.ActionSpec) bool
}

func buildCapabilityDefs() []capabilityDef {
	name := func(s protocol.ActionSpec) string { return s.Name }
	hasAny := func(s protocol.ActionSpec, subs ...string) bool {
		for _, sub := range subs {
			if strings.Contains(name(s), sub) {
				return true
			}
		}
		return false
	}
	return []capabilityDef{
		{id: "schematic.read", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainSchematic && !s.Mutates
		}},
		{id: "schematic.write", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainSchematic && s.Mutates
		}},
		{id: "schematic.check", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainSchematic && hasAny(s, "check", "drc")
		}},
		{id: "schematic.export", match: func(s protocol.ActionSpec) bool {
			return strings.HasPrefix(name(s), "schematic.export")
		}},
		{id: "pcb.read", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainPcb && !s.Mutates
		}},
		{id: "pcb.write", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainPcb && s.Mutates
		}},
		{id: "pcb.route", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainPcb && hasAny(s, "route", "autoroute")
		}, note: []string{
			"typed 布线动作是受控原语/求解器入口；官方自动布线器是否存在需真机探测",
		}, needsProbe: true},
		{id: "pcb.pour", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainPcb && hasAny(s, "pour")
		}},
		{id: "pcb.drc", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainPcb && hasAny(s, "drc")
		}},
		{id: "bom.export", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "bom")
		}},
		{id: "image.export", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "export.image", "snapshot")
		}},
		{id: "project.read", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainProject && !s.Mutates
		}},
		{id: "project.export", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "project.export")
		}},
		{id: "library.read", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainLibrary && !s.Mutates
		}},
		{id: "library.write", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainLibrary && s.Mutates
		}},
		{id: "board.binding", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainBoard
		}},
		{id: "document.control", match: func(s protocol.ActionSpec) bool {
			return s.Domain == protocol.DomainDocument
		}},
		{id: "save.reload", match: func(s protocol.ActionSpec) bool {
			return s.Name == "schematic.save" || s.Name == "pcb.save" || s.Name == "system.page_reload"
		}, note: []string{
			"save 返回成功不等于已持久化；必须 save → 重新打开 → 新鲜回读",
		}},
		{id: "gerber.export", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "gerber")
		}, note: []string{
			"官方 @beta pcb_ManufactureData.getGerberFile 已封装为 pcb.manufacture.gerber；默认=编辑器一键导出（含钻孔层），产物作为 artifact 回读校验；2026-10-28 真机验证 9 层 Gerber zip",
		}},
		{id: "drill.export", match: func(s protocol.ActionSpec) bool {
			// No standalone drill action exists; the drill files are produced by the
			// Gerber export when drilling options are enabled.
			return hasAny(s, "drill") || s.Name == "pcb.manufacture.gerber"
		}, note: []string{
			"钻孔文件随 pcb.manufacture.gerber 产出（drill=true）：含孔板已验证 Drill_PTH_Through.DRL / Drill_PTH_Through_Via.DRL；0 过孔板不产生 drill 文件，按 not_applicable 记录",
		}},
		{id: "cpl.export", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "cpl", "pick_and_place", "pick-place", "placement")
		}, note: []string{
			"官方 @beta pcb_ManufactureData.getPickAndPlaceFile 已封装为 pcb.manufacture.cpl；2026-10-28 真机验证 9 行（UTF-16 TSV，与 BOM 器件数一致）",
		}},
		{id: "archive.backup", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "backup", "archive")
		}, note: []string{
			"原生归档/恢复演练需要宿主工程级导出；目录里没有 backup 动作时按 NOT RUN 记录",
		}},
		{id: "diffpair.routing", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "diffpair", "diff_pair", "differential")
		}, note: []string{
			"官方差分对接口是否存在需真机探测；不存在时只能做离线建议，不得宣称已布线",
		}, needsProbe: true},
		{id: "length.tuning", match: func(s protocol.ActionSpec) bool {
			return hasAny(s, "tuning", "length_match", "meander", "delay_match")
		}, note: []string{
			"等长/调长接口同上：探测不到就明确边界",
		}, needsProbe: true},
	}
}

// buildCapabilities is pure: it maps the typed action catalog + live connector
// state onto the negotiation report, so it is unit-testable without a host.
func buildCapabilities(actions []protocol.ActionSpec, connectorCount int, reported []string) []capabilityItem {
	defs := buildCapabilityDefs()
	items := make([]capabilityItem, 0, len(defs))
	for _, def := range defs {
		var matched []string
		readback := false
		longRunning := false
		wholeBoard := false
		for _, a := range actions {
			if !def.match(a) {
				continue
			}
			matched = append(matched, a.Name)
			if len(a.VerifyWith) > 0 {
				readback = true
			}
			if strings.Contains(a.Name, "drc") || strings.Contains(a.Name, "check") ||
				strings.Contains(a.Name, "route") || strings.Contains(a.Name, "autolayout") ||
				strings.Contains(a.Name, "pour.rebuild") || strings.Contains(a.Name, "auto") {
				longRunning = true
			}
			if strings.Contains(a.Name, "all") || strings.Contains(a.Name, "rebuild") ||
				strings.Contains(a.Name, "autoroute") || strings.Contains(a.Name, "global") ||
				strings.Contains(a.Name, "auto.") {
				wholeBoard = true
			}
		}
		sort.Strings(matched)
		item := capabilityItem{
			ID:            def.id,
			Mode:          "sync",
			ReturnsResult: len(matched) > 0,
			Readback:      readback,
			WholeBoard:    wholeBoard,
			ActionCount:   len(matched),
			Caveat:        def.note,
		}
		if longRunning {
			item.Mode = "sync-long"
		}
		if len(matched) > 6 {
			item.SampleActions = matched[:6]
		} else {
			item.SampleActions = matched
		}
		switch {
		case len(matched) == 0:
			item.Status = "unsupported"
			item.Reason = "运行时 typed action 目录中没有对应动作：该能力在本工具链里没有实现，必须记为 unsupported，不能用宿主版本号推断为可用"
		case connectorCount == 0:
			item.Status = "unknown"
			item.Reason = fmt.Sprintf("动作目录里有 %d 个 typed action，但当前没有连接器连接，无法与宿主协商", len(matched))
		case def.needsProbe:
			item.Status = "unknown"
			item.Reason = fmt.Sprintf("动作目录里有 %d 个受控动作；是否等价于宿主官方能力（自动布线/差分/调长）必须在真机探测后判定", len(matched))
		default:
			item.Status = "supported"
			item.Reason = fmt.Sprintf("动作目录里有 %d 个 typed action 且连接器已连接（%d 个窗口）；单次调用仍以新鲜回读为准", len(matched), connectorCount)
		}
		items = append(items, item)
	}
	return items
}

// buildDeliverables maps the typed action catalog onto the deliverables a
// hardware task needs at kickoff. "api_untested" is the honest default for any
// deliverable whose actions exist but which has not been proven on a live host
// yet: an existing API is not a verified capability.
func buildDeliverables(actions []protocol.ActionSpec, connectorCount int, measured map[string]bool) []deliverableItem {
	names := make([]string, 0, len(actions))
	for _, a := range actions {
		names = append(names, a.Name)
	}
	has := func(sub string) bool {
		for _, n := range names {
			if strings.Contains(n, sub) {
				return true
			}
		}
		return false
	}
	matching := func(subs ...string) []string {
		var out []string
		for _, n := range names {
			for _, sub := range subs {
				if strings.Contains(n, sub) {
					out = append(out, n)
					break
				}
			}
		}
		sort.Strings(out)
		return out
	}
	defs := []struct {
		id       string
		subs     []string
		hostPath bool
		note     string
	}{
		{"schematic.capture", []string{"schematic.component", "schematic.wire", "schematic.netflag", "schematic.export.netlist"}, true,
			"原理图放置/连线/网表导出走 typed action；图面可读性仍需官方导图人工核对"},
		{"pcb.sync", []string{"board.", "pcb.import_changes"}, true,
			"原理图→PCB 同步依赖 board 绑定与变更导入动作；同步结果必须回读核对"},
		{"pcb.stackup", []string{"pcb.stackup"}, true,
			"层叠读写有动作，但尚未在本版本真机验证；层数/铜厚结论必须来自回读"},
		{"pcb.routing", []string{"pcb.route", "pcb.track", "pcb.via"}, true,
			"布线原语存在；不等同于官方自动布线器可用，自动布线能力需真机探测"},
		{"pcb.drc", []string{"pcb.drc", "pcb.check"}, true,
			"DRC 必须绑定当前工程/文档+快照，旧 DRC 不能证明新修改"},
		{"export.3d", []string{"pcb.export.3d", "library.model3d"}, true,
			"3D 导出已真机验证：OBJ 209 KB / STEP 5.0 MB（ISO-10303-21），但模型纳入范围仍需独立检查"},
		{"export.bom", []string{"schematic.export.bom"}, true,
			"BOM 导出后仍需 C 号/型号/封装核对与内容检查"},
		{"export.gerber", []string{"gerber"}, true,
			"已封装 @beta getGerberFile；真机产物为 9 层 Gerber zip（含板框/阻焊/钢网/丝印/文档层），需人工核对层与单位"},
		{"export.drill", []string{"drill", "pcb.manufacture.gerber"}, true,
			"钻孔文件随 pcb.manufacture.gerber 产出（drill=true）：含孔板已验证 PTH/Via drill；0 过孔板按不适用记录"},
		{"export.cpl", []string{"cpl", "pick_and_place", "pick-place"}, true,
			"已封装 @beta getPickAndPlaceFile；真机产物 9 行与 BOM 一致，旋转/单位仍需人工核对"},
	}
	items := make([]deliverableItem, 0, len(defs))
	for _, d := range defs {
		matched := matching(d.subs...)
		item := deliverableItem{ID: d.id, Actions: matched, HostPath: d.hostPath}
		switch {
		case len(matched) == 0:
			item.Status = "unsupported"
			item.Reason = "本运行时没有对应 typed action；该系统没有这条交付能力（GUI 人工导出属于另一条路径）"
			if d.hostPath {
				item.Status = "gui_only"
				item.Reason = "本运行时没有 typed action，只能走官方 GUI 导出 + 人工证据"
			}
		case measured[d.id]:
			item.Status = "measured"
			item.Reason = "本版本已在真机验证并留有证据"
		default:
			item.Status = "api_untested"
			item.Reason = "typed action 存在，但本版本尚未真机验证；接口存在不等于能力已验证"
			if connectorCount == 0 {
				item.Reason += "（当前也没有连接器在线）"
			}
		}
		item.Evidence = "docs/toolchain-integration/evidence/"
		_ = has
		_ = d.note
		items = append(items, item)
	}
	return items
}

func newCapabilitiesCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "capabilities",
		Short: "Negotiate capabilities item by item (supported/unsupported/unknown + reason)",
		Long: "Report each capability separately with a reason, never derived from the EDA version " +
			"number alone. Items whose actions exist but whose official host support must be probed " +
			"are reported as unknown rather than supported.",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			rep := collectCapabilities(cfg)
			enc := json.NewEncoder(stdout)
			enc.SetIndent("", "  ")
			if err := enc.Encode(rep); err != nil {
				return fmt.Errorf("encode capabilities: %w", err)
			}
			fmt.Fprintf(stderr, "easycirq capabilities — %d supported / %d unknown / %d unsupported\n",
				rep.Summary["supported"], rep.Summary["unknown"], rep.Summary["unsupported"])
			for _, it := range rep.Items {
				if it.Status != "supported" {
					fmt.Fprintf(stderr, "  - %-20s %-11s %s\n", it.ID, it.Status, it.Reason)
				}
			}
			fmt.Fprintln(stderr, "deliverables (task-start check):")
			for _, d := range rep.Deliverables {
				fmt.Fprintf(stderr, "  %-18s %-12s %s\n", d.ID, d.Status, d.Reason)
			}
			return nil
		},
	}
}

func collectCapabilities(cfg *appConfig) capabilitiesReport {
	rep := capabilitiesReport{
		Schema:      "easycirq-capabilities/v1",
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
		Protocol: doctorProtocol{
			Service:         protocol.ServiceName,
			WireVersion:     protocol.WireVersion,
			Handshake:       "daemon→connector {type:handshake,service,version}",
			EnvelopeVersion: protocol.WireVersion,
		},
		Summary: map[string]int{},
		Notes: []string{
			"supported = typed action 存在且连接器已连接；不等于该动作在当前宿主上必然成功。",
			"每次写入仍必须：目标一致 → 基线新鲜 → 写入 → 回读 → 保存 → 重开验证。",
			"unsupported 不会被自动降级成“暂不可用”：它表示本工具链没有该能力。",
		},
	}
	connectorCount := 0
	reported := map[string]bool{}
	if portStart, portEnd, err := cfg.portRange(); err == nil {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		result := scanHealth(ctx, hostPortOptions{host: cfg.host, portStart: portStart, portEnd: portEnd})
		cancel()
		if result.Found != nil {
			var raw struct {
				Windows []doctorWindow `json:"windows"`
			}
			if err := json.Unmarshal(result.Found.Raw, &raw); err == nil {
				connectorCount = len(raw.Windows)
				for _, w := range raw.Windows {
					for _, c := range w.Capabilities {
						reported[c] = true
					}
				}
			}
		}
		rep.Host = doctorHost{}
		if conn, host := connectorIdentity(result); true {
			rep.Connector = capabilitiesConnector{Status: conn.Status, Count: conn.Count}
			rep.Host = host
		}
	}
	if connectorCount == 0 {
		rep.Connector.Status = "disconnected"
	}
	for c := range reported {
		rep.Connector.Reported = append(rep.Connector.Reported, c)
	}
	sort.Strings(rep.Connector.Reported)

	actions := protocol.AllActions()
	rep.Items = buildCapabilities(actions, connectorCount, rep.Connector.Reported)
	for _, it := range rep.Items {
		rep.Summary[it.Status]++
	}
	// "measured" is driven by a small evidence-backed list (capability_measured.go),
	// never by the mere existence of an action. export.drill stays unmeasured while
	// the with-vias path has no real-host evidence.
	rep.Deliverables = buildDeliverables(actions, connectorCount, measuredDeliverables())
	return rep
}
