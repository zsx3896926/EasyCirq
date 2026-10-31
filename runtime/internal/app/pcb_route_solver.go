package app

import (
	"context"
	"fmt"
	"math"
	"strings"

	"github.com/zsx3896926/EasyCirq/runtime/pkg/pcbrouting"
)

// PCB identities and units belong to the host adapter, not the search package.
type pcbRouteRequest struct {
	SchemaVersion int     `json:"schemaVersion"`
	Units         string  `json:"units"`
	Net           string  `json:"net"`
	Layer         int     `json:"layer"`
	WidthMil      float64 `json:"widthMil"`
	From          string  `json:"from"`
	To            string  `json:"to"`
	StepMil       float64 `json:"stepMil"`
	MaxDetourMil  float64 `json:"maxDetourMil"`
	MaxStates     int     `json:"maxStates"`
	// PoursDynamic marks copper pours as rebuildable copper instead of solid
	// obstacles. Real workflows route first and re-pour afterwards, and the
	// pour rebuild clears around new tracks; treating a pour as static copper
	// makes every net unroutable on a poured board (the pour covers the layer).
	PoursDynamic bool `json:"poursDynamic,omitempty"`
	// ViaEscape lets an SMD endpoint (top-layer pad) start/stop a track on the
	// requested layer through a via at the pad centre: solder-side pads are the
	// norm, so without this every bottom-layer request is refused as "endpoint
	// needs an unsupported layer transition". The caller must place the via.
	ViaEscape bool `json:"viaEscape,omitempty"`
}

type pcbRouteCandidate struct {
	Net      string       `json:"net"`
	Layer    int          `json:"layer"`
	WidthMil float64      `json:"widthMil"`
	Points   [][2]float64 `json:"points"`
	// ViasRequired lists endpoint pads that need a via to join this track to
	// the pad's own layer (only set when the request used viaEscape).
	ViasRequired []string `json:"viasRequired,omitempty"`
}

type pcbRouteReport struct {
	SchemaVersion int                `json:"schemaVersion"`
	Status        string             `json:"status"`
	BoardSHA256   string             `json:"boardSha256"`
	RequestSHA256 string             `json:"requestSha256"`
	PlanSHA256    string             `json:"planSha256,omitempty"`
	Preview       string             `json:"preview"`
	Candidate     *pcbRouteCandidate `json:"candidate,omitempty"`
	Search        *pcbrouting.Result `json:"search,omitempty"`
	LengthMil     float64            `json:"lengthMil"`
	Bends         int                `json:"bends"`
	// Diagnostics explains an opaque search failure in terms of the copper that
	// actually caused it (e.g. which pads hem in a blocked endpoint).
	Diagnostics []string `json:"diagnostics,omitempty"`
	Reasons       []string           `json:"reasons,omitempty"`
	Limitations   []string           `json:"limitations"`
}

func newPCBRouteReport(board, request []byte) pcbRouteReport {
	return pcbRouteReport{SchemaVersion: 1, Status: "incomplete", BoardSHA256: sha256String(board), RequestSHA256: sha256String(request), Limitations: []string{
		"offline single-layer endpoint-pair proof only; no editor writes or saved-state evidence",
		"no global optimality, whole-board routing, differential-pair, impedance or return-path proof",
	}}
}

func preparePCBRouteRequest(in pcbRouteRequest, snap *boardSnapshot) (pcbrouting.Request, pcbrouting.SegmentClear, string, error) {
	r := pcbrouting.Request{Step: in.StepMil, MaxDetour: in.MaxDetourMil, MaxStates: in.MaxStates}
	fail := func(status, reason string) (pcbrouting.Request, pcbrouting.SegmentClear, string, error) {
		return r, nil, status, fmt.Errorf("%s", reason)
	}
	if in.SchemaVersion != 1 || in.Units != "mil" || strings.TrimSpace(in.Net) == "" || in.From == "" || in.To == "" || in.From == in.To || !allFinite(in.WidthMil) || in.WidthMil <= 0 {
		return fail("fail", "route request requires schemaVersion 1, units mil, net, distinct from/to pads and finite positive widthMil")
	}
	if err := r.Validate(); err != nil {
		return fail("fail", err.Error())
	}
	if in.Layer != 1 && in.Layer != 2 {
		return fail("incomplete", "route solver currently supports TOP/BOTTOM only")
	}
	if snap == nil || len(snap.Partial) > 0 || snap.Components == nil || snap.CopperLayers < 1 || in.Layer == 2 && snap.CopperLayers < 2 {
		return fail("incomplete", "route solver needs a complete measured snapshot and stackup")
	}
	if in.PoursDynamic && snap.Copper != nil {
		// Pours are rebuilt after routing, so their current materialized copper
		// must not take part in the obstacle proof. Strip them before geometry
		// prep as well: a curved pour outline (ARC thermal spokes) otherwise
		// aborts the whole solve even though the pour is about to be rebuilt.
		cp := *snap
		cc := *snap.Copper
		cc.Poured = []any{}
		cp.Copper = &cc
		snap = &cp
	}
	g, status, err := preparePCBRouteGeometry(snap)
	if err != nil {
		return fail(status, err.Error())
	}
	if in.PoursDynamic {
		// Drop rebuildable pour copper from the obstacle set; static fills and
		// keep-out regions stay. ctx.clear reads ctx.areas lazily, so mutating
		// the slice here is enough for both the escape and solver paths.
		kept := g.areas[:0]
		for _, area := range g.areas {
			if area.Kind == "poured copper" {
				continue
			}
			kept = append(kept, area)
		}
		g.areas = kept
	}
	if err := validateCrystalFenceContour(snap.Outline.Points); err != nil {
		return fail("incomplete", "invalid board outline: "+err.Error())
	}
	if len(g.arcs) != 0 {
		return fail("incomplete", "exact arc-track clearance is unsupported by route solve/check")
	}
	if in.WidthMil < snap.Rules.TrackWidthMinMil {
		return fail("fail", "requested widthMil is below the measured minimum")
	}
	a, aok := g.pads[in.From]
	z, zok := g.pads[in.To]
	if !aok || !zok || g.ambiguous[in.From] || g.ambiguous[in.To] {
		return fail("incomplete", "route endpoints require unique measured designator.pad identities")
	}
	if a.Net != in.Net || z.Net != in.Net {
		return fail("fail", "route endpoint net differs from the independent request")
	}
	if !in.ViaEscape && (!padLayerMatches(a.Layer, in.Layer) || !padLayerMatches(z.Layer, in.Layer)) {
		return fail("incomplete", "endpoint needs an unsupported layer transition (set viaEscape to route from a via at the pad centre)")
	}
	r.From, r.To = [2]float64{a.X, a.Y}, [2]float64{z.X, z.Y}
	// Calibrate the search step for the kernel's fixed cell budget. The kernel
	// rejects oversized grids with a bare "grid-limit", which users cannot act
	// on; callers routinely pass a fine step (5-10 mil) together with a large
	// detour on a large board and get that opaque failure. Raising the step here
	// keeps the request honest (same detour, coarser lattice) and always yields
	// either a path or a bounded-search reason the caller can understand.
	if r.Step > 0 && r.MaxDetour >= 0 {
		spanX := math.Abs(r.To[0]-r.From[0]) + 2*r.MaxDetour
		spanY := math.Abs(r.To[1]-r.From[1]) + 2*r.MaxDetour
		for i := 0; i < 16; i++ {
			cells := (math.Floor(spanX/r.Step) + 1) * (math.Floor(spanY/r.Step) + 1)
			if cells <= 240000 {
				break
			}
			r.Step *= 1.5
		}
	}
	if err := r.Validate(); err != nil {
		return fail("fail", err.Error())
	}
	// These stricter capability checks are local to the new command. Existing
	// planners retain their own contracts. In particular, never turn arc chords,
	// thermal-spoke strokes or missing cutout geometry into free space.
	var slots []pcbCopperArea
	type strokedArea struct {
		area  pcbCopperArea
		width float64
	}
	var strokes []strokedArea
	for _, raw := range snap.Copper.Fills {
		m := raw.(map[string]any) // checked by preparePCBRouteGeometry
		layer := int(asFloat(m["layer"]))
		if !netPathCopperLayer(layer) && layer != pcbLayerMulti {
			continue
		}
		if m["geometryAvailable"] != true {
			return fail("incomplete", "fill/cutout geometry is unknown")
		}
		stroke, ok := asFloatOK(m["lineWidth"])
		if !ok || !allFinite(stroke) || stroke < 0 || m["fillMode"] != "solid" {
			return fail("incomplete", "fill/cutout needs known solid fill mode and nonnegative stroke width")
		}
		contours, err := pcbRouteExactContours(m["source"])
		if err != nil {
			return fail("incomplete", err.Error())
		}
		if layer == pcbLayerMulti {
			if stroke != 0 {
				return fail("incomplete", "stroked cutout boundary is unsupported")
			}
			slots = append(slots, pcbCopperArea{Contours: contours})
		} else {
			strokes = append(strokes, strokedArea{area: pcbCopperArea{Net: asString(m["net"]), Layer: layer, Contours: contours}, width: stroke})
		}
	}
	for _, raw := range snap.Copper.Poured {
		m := raw.(map[string]any)
		for _, rawFill := range m["fills"].([]any) {
			fill := rawFill.(map[string]any)
			if fill["fill"] != true {
				return fail("incomplete", "poured fill/stroke semantics unknown or unsupported")
			}
			width, ok := asFloatOK(fill["lineWidth"])
			if !ok || !allFinite(width) || width < 0 {
				return fail("incomplete", "poured polygon stroke width unknown or unsupported")
			}
			contours, err := pcbRouteExactContours(fill["source"])
			if err != nil {
				return fail("incomplete", err.Error())
			}
			strokes = append(strokes, strokedArea{area: pcbCopperArea{Net: asString(m["net"]), Layer: int(asFloat(m["layer"])), Contours: contours}, width: width})
		}
	}
	for _, raw := range snap.Copper.Regions {
		m := raw.(map[string]any)
		for _, rule := range m["ruleType"].([]any) {
			if asFloat(rule) == 5 {
				layer := int(asFloat(m["layer"]))
				if layer != pcbLayerMulti && !netPathCopperLayer(layer) {
					return fail("incomplete", "no-wires region layer is unsupported")
				}
				if _, err := pcbRouteExactContours(m["source"]); err != nil {
					return fail("incomplete", err.Error())
				}
			}
		}
	}
	clear, err := g.clear(pcbEscapeDemand{Net: in.Net, Layer: in.Layer, WidthMil: in.WidthMil}, nil)
	if err != nil {
		return fail("incomplete", err.Error())
	}
	return r, func(a, z [2]float64) bool {
		if !clear(a, z) {
			return false
		}
		for _, slot := range slots {
			if copperAreaSegmentDistance(slot, a, z) < in.WidthMil/2+math.Max(8, math.Max(snap.Rules.ClearanceMil, snap.Rules.CopperToEdgeMil))-netPathGeomEps {
				return false
			}
		}
		for _, stroke := range strokes {
			if stroke.area.Net != in.Net && stroke.area.Layer == in.Layer && copperAreaSegmentDistance(stroke.area, a, z) < in.WidthMil/2+stroke.width/2+snap.Rules.ClearanceMil-netPathGeomEps {
				return false
			}
		}
		return true
	}, "", nil
}

// No curved contours are approximated for this proof. The broader host parser
// can flatten ARC for other consumers; here only exact polygonal edges qualify.
func pcbRouteExactContours(raw any) ([][][2]float64, error) {
	var checkTokens func(any) error
	checkTokens = func(v any) error {
		switch x := v.(type) {
		case []any:
			for _, child := range x {
				if err := checkTokens(child); err != nil {
					return err
				}
			}
		case string:
			if x != "L" {
				return fmt.Errorf("route solver requires exact polygonal contours; %s is unsupported", x)
			}
		}
		return nil
	}
	if err := checkTokens(raw); err != nil {
		return nil, err
	}
	contours, err := polygonSourceContours(raw)
	if err != nil {
		return nil, err
	}
	for _, contour := range contours {
		if err := validateCrystalFenceContour(contour); err != nil {
			return nil, err
		}
	}
	return contours, nil
}

func solvePCBRoute(ctx context.Context, in pcbRouteRequest, snap *boardSnapshot, report *pcbRouteReport) error {
	r, clear, status, err := preparePCBRouteRequest(in, snap)
	if err != nil {
		report.Status = status
		report.Reasons = []string{err.Error()}
		return err
	}
	result, err := pcbrouting.Solve(ctx, r, clear)
	report.Search = &result
	if err != nil {
		report.Reasons = []string{err.Error()}
		return err
	}
	if result.Status != pcbrouting.Found {
		report.Reasons = []string{result.Reason}
		if result.Reason == "endpoint-blocked" {
			// A bare "endpoint-blocked" is not actionable: on dense connectors a
			// mechanical/no-net pad (or a foreign-net pad at fine pitch) is
			// usually what hems the endpoint in. Name the nearest copper.
			report.Diagnostics = append(report.Diagnostics, diagnoseEndpointBlocked(snap, in)...)
		}
		return fmt.Errorf("route search incomplete: %s", result.Reason)
	}
	report.Status = "pass"
	report.Candidate = &pcbRouteCandidate{Net: in.Net, Layer: in.Layer, WidthMil: in.WidthMil, Points: result.Points}
	if in.ViaEscape {
		report.Candidate.ViasRequired = []string{in.From, in.To}
		report.Limitations = append(report.Limitations,
			"viaEscape: place a via at each endpoint pad centre before using this path")
	}
	report.LengthMil, report.Bends = result.Length, result.Bends
	return nil
}

func checkPCBRoute(ctx context.Context, in pcbRouteRequest, snap *boardSnapshot, plan pcbRouteReport, report *pcbRouteReport) error {
	fail := func(status, reason string) error {
		report.Status = status
		report.Reasons = []string{reason}
		return fmt.Errorf("%s", reason)
	}
	r, clear, status, err := preparePCBRouteRequest(in, snap)
	if err != nil {
		return fail(status, err.Error())
	}
	if plan.SchemaVersion != 1 || plan.BoardSHA256 != report.BoardSHA256 || plan.RequestSHA256 != report.RequestSHA256 {
		return fail("fail", "plan provenance differs from board/request inputs")
	}
	c := plan.Candidate
	if c != nil {
		report.Candidate = &pcbRouteCandidate{Net: c.Net, Layer: c.Layer, WidthMil: c.WidthMil, Points: append([][2]float64(nil), c.Points...)}
	}
	if plan.Status != "pass" || c == nil || c.Net != in.Net || c.Layer != in.Layer || c.WidthMil != in.WidthMil {
		return fail("fail", "plan candidate is missing or differs from requested net/layer/width")
	}
	if err := pcbrouting.Check(ctx, r, c.Points, clear); err != nil {
		return fail("fail", err.Error())
	}
	report.Status = "pass"
	report.LengthMil, report.Bends = pcbrouting.Metrics(c.Points)
	return nil
}

// findSnapshotPad resolves "DESIGNATOR.PAD" against the measured snapshot.
func findSnapshotPad(snap *boardSnapshot, ref string) (string, boardPad, bool) {
	idx := strings.LastIndex(ref, ".")
	if idx <= 0 || idx == len(ref)-1 {
		return "", boardPad{}, false
	}
	des, num := ref[:idx], ref[idx+1:]
	for _, comp := range snap.Components {
		if comp.Designator != des {
			continue
		}
		for _, p := range comp.Pads {
			if p.Number == num {
				return des, p, true
			}
		}
	}
	return "", boardPad{}, false
}

// diagnoseEndpointBlocked lists the nearest foreign copper around each endpoint
// so a "endpoint-blocked" failure names the obstacle instead of just the symptom.
func diagnoseEndpointBlocked(snap *boardSnapshot, in pcbRouteRequest) []string {
	if snap == nil {
		return nil
	}
	type near struct {
		label string
		dist  float64
	}
	var out []string
	for _, ref := range []string{in.From, in.To} {
		des, pad, ok := findSnapshotPad(snap, ref)
		if !ok {
			continue
		}
		var items []near
		for _, comp := range snap.Components {
			for _, p := range comp.Pads {
				if comp.Designator == des && p.Number == pad.Number {
					continue
				}
				d := math.Hypot(p.X-pad.X, p.Y-pad.Y)
				if d > 80 {
					continue
				}
				net := p.Net
				if net == "" {
					net = "netless/mechanical"
				}
				items = append(items, near{fmt.Sprintf("%s.%s (%s) %.1fmil", comp.Designator, p.Number, net, d), d})
			}
		}
		for _, raw := range snap.Copper.Vias {
			m, okMap := raw.(map[string]any)
			if !okMap {
				continue
			}
			vx, okx := asFloatOK(m["x"])
			vy, oky := asFloatOK(m["y"])
			if !okx || !oky {
				continue
			}
			d := math.Hypot(vx-pad.X, vy-pad.Y)
			if d > 80 {
				continue
			}
			net := asString(m["net"])
			if net == "" {
				net = "netless"
			}
			items = append(items, near{fmt.Sprintf("via (%s) %.1fmil", net, d), d})
		}
		if len(items) == 0 {
			out = append(out, fmt.Sprintf("%s at (%.1f,%.1f): no copper within 80mil — the blockage is the pad's own keep-out", ref, pad.X, pad.Y))
			continue
		}
		for i := 0; i < len(items); i++ {
			for j := i + 1; j < len(items); j++ {
				if items[j].dist < items[i].dist {
					items[i], items[j] = items[j], items[i]
				}
			}
		}
		if len(items) > 6 {
			items = items[:6]
		}
		parts := make([]string, 0, len(items))
		for _, it := range items {
			parts = append(parts, it.label)
		}
		out = append(out, fmt.Sprintf("%s at (%.1f,%.1f): hemmed in by %s", ref, pad.X, pad.Y, strings.Join(parts, ", ")))
	}
	return out
}
