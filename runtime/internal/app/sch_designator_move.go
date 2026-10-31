package app

import (
	"fmt"
	"math"
	"strings"
)

// designatorMovePayload builds the attribute-move payload for a reference text
// from live geometry, so callers do not have to hand-assemble the complete
// 17-field native attribute record (the platform silently repels incomplete
// snapshots, and the raw formula Value must be preserved verbatim).
//
// anchor selects where the text lands relative to the part bbox:
// below|above|left|right, optionally nudged by dx/dy.
func designatorMovePayload(cfg *appConfig, window, designator, anchor string, dx, dy float64) (map[string]any, error) {
	designator = strings.TrimSpace(designator)
	if designator == "" {
		return nil, fmt.Errorf("--designator is required")
	}
	cur, err := requestAction(cfg, "document.current", window, nil)
	if err != nil {
		return nil, err
	}
	if cur.Context == nil || strings.TrimSpace(cur.Context.ProjectUUID) == "" || strings.TrimSpace(cur.Context.DocumentUUID) == "" {
		return nil, fmt.Errorf("could not resolve the live project/document identity")
	}
	res, err := requestAction(cfg, "schematic.components.list", window, map[string]any{"includePagePrimitives": true})
	if err != nil {
		return nil, err
	}
	comps, perr := parseLayoutComps(res.Result)
	if perr != nil {
		return nil, perr
	}
	wantID := ""
	for _, c := range comps {
		if strings.EqualFold(strings.TrimSpace(c.Designator), designator) {
			wantID = c.ID
			break
		}
	}
	if wantID == "" {
		return nil, fmt.Errorf("no component with designator %q on this page", designator)
	}

	rawComps, _ := res.Result["components"].([]any)
	var bbox map[string]any
	for _, item := range rawComps {
		m, ok := item.(map[string]any)
		if !ok || strField(m, "primitiveId") != wantID {
			continue
		}
		if b, ok := m["bbox"].(map[string]any); ok {
			bbox = b
		}
	}

	page, _ := res.Result["pagePrimitives"].(map[string]any)
	attrs, _ := page["attributes"].([]any)
	var record map[string]any
	for _, item := range attrs {
		m, ok := item.(map[string]any)
		if !ok || strField(m, "Key") != "Designator" || strField(m, "ParentPrimitiveId") != wantID {
			continue
		}
		record = m
		break
	}
	if record == nil {
		return nil, fmt.Errorf("component %s has no Designator attribute on this page", designator)
	}

	minX, minY, maxX, maxY := 0.0, 0.0, 0.0, 0.0
	if bbox != nil {
		minX = numField(bbox, "minX")
		minY = numField(bbox, "minY")
		maxX = numField(bbox, "maxX")
		maxY = numField(bbox, "maxY")
	}
	x, y := minX+2, minY-22 // default: below the body
	switch strings.ToLower(strings.TrimSpace(anchor)) {
	case "", "below":
	case "above":
		x, y = minX+2, maxY+14
	case "left":
		x, y = minX-62, (minY+maxY)/2
	case "right":
		x, y = maxX+10, (minY+maxY)/2
	default:
		return nil, fmt.Errorf("--anchor must be below|above|left|right")
	}
	x += dx
	y += dy
	return map[string]any{
		"projectUuid":  cur.Context.ProjectUUID,
		"documentUuid": cur.Context.DocumentUUID,
		"primitiveId":  strField(record, "primitiveId"),
		"expected":     record,
		"x":            x,
		"y":            y,
	}, nil
}

func numField(m map[string]any, key string) float64 {
	switch v := m[key].(type) {
	case float64:
		return v
	case int:
		return float64(v)
	}
	return 0
}

var _ = math.Abs
