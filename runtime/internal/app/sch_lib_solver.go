package app

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/zsx3896926/EasyCirq/runtime/internal/connectivity"
)

// The electrical graph and measured poses are immutable. Only translations,
// routes and naming markers are searched, on a bounded five-raw grid.
// libLayoutRetryable 判断这次失败是否值得"换个搜索起点"重摆。
//
// 只对**摆完了却过不了校验**重试（信号网被拆成多岛 / 外设没有通向 core 的
// 非地导线）。候选预算耗尽是"没搜到"，换顺序确实可能有用，但代价是再烧几十万
// 候选，交给调用方决定，不在这里硬试。
func libLayoutRetryable(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	for _, k := range []string{"peripheral-direct-missing", "peripheral-label-incomplete"} {
		if strings.Contains(msg, k) {
			return true
		}
	}
	return false
}

// libLayoutReorder 返回把各模块外设按指定方式重排后的输入。
//
// `mode`：1=按 componentId 排序，2=按位号排序，3=反序。
//
// 为什么是"排序"而不是"轮换"：实测把一张倒序表轮换 1..5 位，永远到不了那个
// 能排出来的顺序；而排序给出的是**另一类**顺序，才可能跨过去。
func libLayoutReorder(input libLayoutSource, mode int) libLayoutSource {
	refOf := map[string]string{}
	for _, c := range input.Connectivity.Components {
		refOf[c.ID] = c.Ref
	}
	mods := make([]connectivity.Module, len(input.Connectivity.Modules))
	copy(mods, input.Connectivity.Modules)
	changed := false
	for i := range mods {
		per := append([]string(nil), mods[i].PeripheralComponents...)
		if len(per) < 2 {
			continue
		}
		switch mode {
		case 1:
			sort.SliceStable(per, func(a, b int) bool { return per[a] < per[b] })
		case 2:
			sort.SliceStable(per, func(a, b int) bool {
				ra, rb := refOf[per[a]], refOf[per[b]]
				if ra != rb {
					return ra < rb
				}
				return per[a] < per[b]
			})
		case 3:
			for a, b := 0, len(per)-1; a < b; a, b = a+1, b-1 {
				per[a], per[b] = per[b], per[a]
			}
		}
		if !libSameOrder(per, mods[i].PeripheralComponents) {
			changed = true
		}
		mods[i].PeripheralComponents = per
	}
	if !changed {
		return input
	}
	out := input
	out.Connectivity.Modules = mods
	return out
}

func libSameOrder(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func planLibLayout(input libLayoutSource) (*schCompositionSource, error) {
	computed, err := computeLibLayout(input, "", false)
	if err == nil {
		return computed.composition, nil
	}
	if !libLayoutRetryable(err) {
		return nil, err
	}
	// 摆出来了但校验不过 —— **换一种外设顺序重摆**。
	// 校验标准一次都没降，只是给搜索另一个起点。
	firstErr := err
	for mode := 1; mode <= 3; mode++ {
		alt := libLayoutReorder(input, mode)
		if libSameOrder(alt.Connectivity.Modules[0].PeripheralComponents,
			input.Connectivity.Modules[0].PeripheralComponents) && mode == 1 {
			continue
		}
		computed, e2 := computeLibLayout(alt, "", false)
		if e2 == nil {
			return computed.composition, nil
		}
		if !libLayoutRetryable(e2) {
			return nil, e2
		}
	}
	return nil, firstErr
}

// The canonical adapter is shared by legacy composition and local-only layout.
// Local output never invents a larger measured sheet to fit expanded geometry.
type libLayoutComputation struct {
	composition *schCompositionSource
	zones       *SchematicZonesResult
}

func planLibLayoutZones(input libLayoutSource, mode string) (*SchematicZonesResult, error) {
	computed, err := computeLibLayout(input, mode, true)
	if err != nil {
		return nil, err
	}
	return computed.zones, nil
}

func computeLibLayout(input libLayoutSource, mode string, localOnly bool) (*libLayoutComputation, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, err
	}
	var src libLayoutSource
	if err = json.Unmarshal(raw, &src); err != nil {
		return nil, err
	}
	fail := func(format string, args ...any) (*libLayoutComputation, error) {
		return nil, fmt.Errorf("unresolved: "+format, args...)
	}
	if src.SchemaVersion != 1 || src.Connectivity.ProjectID == "" || src.Connectivity.DocumentID == "" || !plBoxValid(src.Sheet) {
		return fail("schemaVersion:1, target project/page and measured sheet are required")
	}
	if _, _, err := schCompositionUsableBounds(src.Sheet, src.SheetBorder); err != nil {
		return fail("%v", err)
	}
	budget := src.MaxCandidates
	if budget == 0 {
		budget = 20000
	}
	if budget < 1 || budget > 1000000 {
		return fail("maxCandidates must be 1..1000000 (default 20000)")
	}
	for _, k := range src.Keepouts {
		if !plBoxValid(k) || !boxInside(k, src.Sheet) {
			return fail("invalid keepout")
		}
	}
	d := src.Connectivity
	if err = d.Validate(); err != nil {
		return fail("%v", err)
	}
	byID, byRef := map[string]connectivity.Component{}, map[string]connectivity.Component{}
	netNames, names := map[string]string{}, map[string]bool{}
	pinNet := map[string]map[string]string{}
	for _, n := range d.Nets {
		if strings.TrimSpace(n.Name) == "" || names[n.Name] {
			return fail("net %s needs a unique nonempty name", n.ID)
		}
		netNames[n.ID], names[n.Name] = n.Name, true
	}
	for _, c := range d.Components {
		if c.Device.LibraryUUID == "" || !isDeviceLibraryUUID(c.Device.UUID) || len(c.Pins) == 0 {
			return fail("%s needs library identity and complete physical pins", c.Ref)
		}
		byID[c.ID], byRef[c.Ref], pinNet[c.ID] = c, c, map[string]string{}
	}
	for _, edge := range d.Connections {
		pinNet[edge.ComponentID][edge.PinNumber] = edge.NetID
	}
	for _, c := range d.Components {
		for _, q := range c.Pins {
			states := 0
			if pinNet[c.ID][q.Number] != "" {
				states++
			}
			if q.NoConnected {
				states++
			}
			if q.ConnectionState == "unconnected" {
				states++
			}
			if states != 1 {
				return fail("%s.%s must have exactly one net or explicit NC or unconnected intent", c.Ref, q.Number)
			}
		}
	}
	measured := map[string]powerLayoutPlacement{}
	for _, m := range src.Measurements {
		c, ok := byRef[m.Designator]
		if !ok || measured[c.ID].Designator != "" {
			return fail("unknown/duplicate measurement %s", m.Designator)
		}
		if !plBoxValid(m.BBox) || !plGrid(m.X) || !plGrid(m.Y) || !plFinite(m.Rotation) || math.Mod(m.Rotation, 90) != 0 || len(m.Pins) != len(c.Pins) {
			return fail("%s incomplete measured geometry", c.Ref)
		}
		pins := map[string]connectivity.Pin{}
		for _, q := range c.Pins {
			pins[q.Number] = q
		}
		seen := map[string]bool{}
		for _, q := range m.Pins {
			cp, exists := pins[q.Number]
			if !exists || seen[q.Number] || cp.Name != q.Name || !plGrid(q.X) || !plGrid(q.Y) || q.Net != netNames[pinNet[c.ID][q.Number]] {
				return fail("%s.%s measured pin differs from canonical IR", c.Ref, q.Number)
			}
			if _, err := libPinSide(q, m.BBox); err != nil {
				return fail("%s: %v", c.Ref, err)
			}
			seen[q.Number] = true
		}
		measured[c.ID] = m
	}
	if len(measured) != len(d.Components) {
		return fail("measurements must cover every component")
	}
	modules, owners := map[string]connectivity.Module{}, map[string]string{}
	for _, m := range d.Modules {
		if m.ID == "" || modules[m.ID].ID != "" {
			return fail("unknown/duplicate canonical module %s", m.ID)
		}
		for _, id := range append(append([]string{}, m.CoreComponents...), m.PeripheralComponents...) {
			if byID[id].ID == "" || owners[id] != "" {
				return fail("unknown/repeated module member %s", id)
			}
			owners[id] = m.ID
		}
		modules[m.ID] = m
	}
	if len(owners) != len(d.Components) {
		return fail("every component must belong to one module")
	}
	result := &schCompositionSource{SchemaVersion: 1, Connectivity: d, Sheet: src.Sheet, SheetBorder: src.SheetBorder, Keepouts: src.Keepouts}
	zones := &SchematicZonesResult{SchemaVersion: 1}
	seenModules := map[string]bool{}
	for _, intent := range src.LayoutModules {
		cm, ok := modules[intent.ID]
		if !ok || seenModules[intent.ID] {
			return fail("unknown/duplicate layout module %s", intent.ID)
		}
		seenModules[intent.ID] = true
		rootOK := false
		for _, id := range cm.CoreComponents {
			rootOK = rootOK || id == intent.CoreComponentID
		}
		if !rootOK {
			return fail("module %s coreComponentId must name a canonical core", intent.ID)
		}
		members := append(append([]string{}, cm.CoreComponents...), cm.PeripheralComponents...)
		netPolicies := map[string]string{}
		usedNets := map[string]bool{}
		for _, id := range members {
			for _, n := range pinNet[id] {
				usedNets[n] = true
			}
		}
		for n := range usedNets {
			switch intent.NetPolicies[n] {
			case "direct", "local_power", "local_ground", "module_port":
				netPolicies[netNames[n]] = intent.NetPolicies[n]
			default:
				return fail("module %s net %s needs an explicit supported policy", intent.ID, n)
			}
		}
		for n := range intent.NetPolicies {
			if !usedNets[n] {
				return fail("module %s unknown/unused policy %s", intent.ID, n)
			}
		}
		hints := map[string]libLayoutPeripheral{}
		for _, h := range intent.Peripherals {
			if owners[h.ComponentID] != intent.ID || h.ComponentID == intent.CoreComponentID || hints[h.ComponentID].ComponentID != "" {
				return fail("invalid/duplicate peripheral hint %s", h.ComponentID)
			}
			if h.AttachTo != nil && (owners[h.AttachTo.ComponentID] != intent.ID || h.AttachTo.ComponentID == h.ComponentID) {
				return fail("%s attachment target must be another module member", h.ComponentID)
			}
			hints[h.ComponentID] = h
		}
		input := SchematicLayoutInput{SchemaVersion: 1, LayoutMode: mode, CoreComponentID: intent.CoreComponentID, NetPolicies: netPolicies, Attachments: intent.Peripherals}
		for _, id := range members {
			states := map[string]string{}
			for _, pin := range byID[id].Pins {
				if pin.NoConnected {
					states[pin.Number] = "nc"
				} else if pin.ConnectionState == "unconnected" {
					states[pin.Number] = "unconnected"
				}
			}
			input.Components = append(input.Components, SchematicLayoutComponent{ID: id, Measurement: measured[id], PinStates: states})
		}
		local, e := planSchematicLayoutWithBudget(input, &budget)
		if e != nil {
			return nil, fmt.Errorf("unresolved: module %s: %w", intent.ID, e)
		}
		if localOnly {
			setSchematicMarkerAnchorZone(local, intent.ID)
			zone := SchematicZone{ID: intent.ID, Title: intent.Title, CoreComponentID: intent.CoreComponentID, ComponentIDs: members}
			measured, err := measureSchematicZoneVariant(zone, "", local, nil)
			if err != nil {
				return nil, err
			}
			zones.Zones = append(zones.Zones, SchematicZoneResult{ID: zone.ID, Title: zone.Title, CoreComponentID: zone.CoreComponentID,
				ContentBounds: measured.ContentBounds, Frame: measured.Frame, Layout: measured.Layout})
			zones.CandidatesUsed += local.CandidatesUsed
		}
		p := powerLayoutPlan{Placements: local.Placements, Wires: local.Wires, Flags: local.Flags}
		result.Modules = append(result.Modules, schCompositionModule{ID: intent.ID, Title: intent.Title, Placements: p.Placements, Wires: p.Wires, Flags: p.Flags})
	}
	if len(seenModules) != len(modules) {
		return fail("layoutModules must cover every canonical module")
	}
	if !localOnly {
		if _, err = planSchComposition(*result); err != nil {
			return fail("composition validation: %v", err)
		}
	}
	return &libLayoutComputation{composition: result, zones: zones}, nil
}
