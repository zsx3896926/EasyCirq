package app

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestBoardSnapshotSemanticHashIgnoresCaptureMetadataOnly(t *testing.T) {
	s := lpSnapshot(lpComp("u1", "U1", 100, 100, 0, lpBBox(90, 90, 110, 110)))
	s.CapturedAt = "2026-09-22T01:00:00Z"
	s.SemanticSHA256 = "old-self-hash"
	h1, err := boardSnapshotSemanticSHA256(s)
	if err != nil {
		t.Fatal(err)
	}
	s.CapturedAt = "2026-09-22T02:00:00Z"
	s.Project = "renamed-capture-label"
	s.SemanticSHA256 = "another-self-hash"
	h2, err := boardSnapshotSemanticSHA256(s)
	if err != nil {
		t.Fatal(err)
	}
	if h1 != h2 {
		t.Fatalf("capture metadata changed semantic hash: %s != %s", h1, h2)
	}
	s.Components[0].X++
	h3, err := boardSnapshotSemanticSHA256(s)
	if err != nil {
		t.Fatal(err)
	}
	if h3 == h2 {
		t.Fatal("component geometry/identity change did not change semantic hash")
	}
}

func TestBoardSnapshotSemanticHashSurvivesDumpRoundTripWithProjectLabel(t *testing.T) {
	s := lpSnapshot(lpComp("u1", "U1", 100, 100, 0, lpBBox(90, 90, 110, 110)))
	h, err := boardSnapshotSemanticSHA256(s)
	if err != nil {
		t.Fatal(err)
	}
	// cmd_pcb_dump attaches this provenance label after the geometry fetch.
	s.Project = "ceshi"
	s.SemanticSHA256 = h
	raw, err := json.Marshal(s)
	if err != nil {
		t.Fatal(err)
	}
	loaded, err := loadBoardSnapshotFile(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	got, err := boardSnapshotSemanticSHA256(loaded)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.SemanticSHA256 != got {
		t.Fatalf("dump invalidated its own semantic hash: stored=%s recomputed=%s", loaded.SemanticSHA256, got)
	}
}

func TestCopperSnapshotAvailabilityDistinguishesKnownEmptyFromUnknown(t *testing.T) {
	knownEmpty := &boardSnapshot{Copper: &boardCopperSnapshot{
		Availability: map[string]string{"routing": "available", "vias": "available", "pours": "available", "poured": "available", "regions": "available", "fills": "available"},
		Lines:        []any{}, Arcs: []any{}, Vias: []any{}, Pours: []any{}, Poured: []any{}, Regions: []any{}, Fills: []any{},
	}}
	available := true
	knownEmpty.Copper.ArcsAvailable = &available
	if got := knownEmpty.Copper.Availability["poured"]; got != "available" || knownEmpty.Copper.Poured == nil {
		t.Fatalf("known-empty materialized copper lost: availability=%q list=%#v", got, knownEmpty.Copper.Poured)
	}
	unknown := &boardSnapshot{Copper: &boardCopperSnapshot{Availability: map[string]string{"poured": "unknown"}}}
	if unknown.Copper.Availability["poured"] != "unknown" {
		t.Fatalf("unknown availability=%q", unknown.Copper.Availability["poured"])
	}
}

func TestBoardSnapshotPreservesExactPadShapeAndSpecialPad(t *testing.T) {
	shape := []any{"RECT", 20.0, 12.0, 2.0}
	special := []any{"L", 1.0, 2.0}
	components := parseBoardComponents(componentsResult(map[string]any{
		"primitiveId": "u1", "designator": "U1", "layer": 1.0,
		"pads": []any{map[string]any{
			"primitiveId": "p1", "padNumber": "1", "net": "GND", "layer": 1.0,
			"x": 10.0, "y": 20.0, "width": 20.0, "height": 12.0,
			"shape": shape, "specialPad": special,
		}},
	}))
	if len(components) != 1 || len(components[0].Pads) != 1 {
		t.Fatalf("components=%+v", components)
	}
	pad := components[0].Pads[0]
	if canonicalJSON(pad.Shape) != canonicalJSON(shape) || canonicalJSON(pad.SpecialPad) != canonicalJSON(special) {
		t.Fatalf("pad geometry was dropped: shape=%#v special=%#v", pad.Shape, pad.SpecialPad)
	}
}

func TestBoardSnapshotSemanticHashIgnoresFloatJitter(t *testing.T) {
	// Live 2026-10-13: save → reload returned the same board with getter noise
	// (-200.30700000000001 vs -200.307) and the semantic hash changed anyway.
	a := lpSnapshot(lpComp("c1", "C1", -200.30700000000001, -761.4249999999998, 0, lpBBox(-200.3070000000001, -843.5749999999998, -39.69300000000004, -761.4)))
	b := lpSnapshot(lpComp("c1", "C1", -200.307, -761.425, 0, lpBBox(-200.307, -843.575, -39.692999999999984, -761.4)))
	ha, err := boardSnapshotSemanticSHA256(a)
	if err != nil {
		t.Fatal(err)
	}
	hb, err := boardSnapshotSemanticSHA256(b)
	if err != nil {
		t.Fatal(err)
	}
	if ha != hb {
		t.Fatalf("float jitter changed the semantic hash: %s != %s", ha, hb)
	}
	b.Components[0].X += 0.01
	if hc, _ := boardSnapshotSemanticSHA256(b); hc == hb {
		t.Fatal("a real 0.01 mil move must change the semantic hash")
	}
}

// 不加 --include-copper 时，快照里**根本没有走线**；这一条必须在 Partial 里说出来。
//
// 2026-11-02 实测：pcb dump 默认输出只有 components，没有任何走线字段，
// 而"没有这个字段"和"板子没布线"在读的人看来一模一样。我据此两次判定
// "板子一条线都没布"，还重跑了 auto-place/autortoute —— 实际板上 109 段铜线、
// 8 个网络全布完了。默认输出里一个提示都没有，所以这个误判看起来像事实。
func TestBoardSnapshotNotesWhenCopperWasNotCaptured(t *testing.T) {
	// 复刻 withCopper=false 的那条 else 分支所做的事，验证说明本身：
	// 必须点明"没抓"、必须点明"没有 ≠ 空"、必须给出补救命令。
	s := &boardSnapshot{}
	s.note("capture provenance: copper NOT captured (no --include-copper) — " +
		"routed traces, vias and pours are ABSENT from this snapshot; an absent " +
		"list here is not an empty board. Re-run with --include-copper to read routing")

	if len(s.Partial) != 1 {
		t.Fatalf("want exactly one note, got %d: %v", len(s.Partial), s.Partial)
	}
	note := s.Partial[0]
	for _, want := range []string{"NOT captured", "--include-copper", "not an empty board"} {
		if !strings.Contains(note, want) {
			t.Errorf("note must contain %q, got: %s", want, note)
		}
	}
}

// 这条说明属于"抓到了什么"，不是板子语义 —— 必须被排除在 semanticSha256 之外，
// 否则既有的冻结基准会因为加了一句提示而全部失效。
func TestBoardSnapshotCopperOmittedNoteDoesNotChangeSemanticHash(t *testing.T) {
	base := lpSnapshot(lpComp("u1", "U1", 100, 100, 0, lpBBox(90, 90, 110, 110)))
	before, err := boardSnapshotSemanticSHA256(base)
	if err != nil {
		t.Fatal(err)
	}
	base.note("capture provenance: copper NOT captured (no --include-copper) — " +
		"routed traces, vias and pours are ABSENT from this snapshot")
	after, err := boardSnapshotSemanticSHA256(base)
	if err != nil {
		t.Fatal(err)
	}
	if before != after {
		t.Fatalf("provenance note must not perturb the semantic hash: %s != %s",
			before, after)
	}
}
