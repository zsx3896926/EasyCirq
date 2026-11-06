package app

import (
	"strings"
	"testing"
)

// 引脚标签去重的回归测试。
//
// 实测（`sch_text_audit --strict`）：M1 报 6 项、M2 报 5 项 text_overlap，
// 全是相邻引脚标签在 5 raw 间距下互压（字号 4.5，字形约 3 raw）。
// 修法是**算标签框、重叠就不画第二个**（宁缺勿叠），位号与值也先占位。
//
// 这条测试用一个"两脚相距 4 raw、标签各 1 字"的合成布局，要求：
//   - 渲染成功
//   - 引脚标签的 <text> 数量少于引脚数（证明去重生效）
//   - 但引脚本身（circle/线）一个不少（证明只少画了标签，没丢几何）
func TestRenderDedupesOverlappingPinLabels(t *testing.T) {
	mk := func(designator string) SchematicPlacement {
		return SchematicPlacement{
			Designator: designator,
			X:          0, Y: 0,
			BBox: SchematicBox{MinX: -10, MinY: -10, MaxX: 10, MaxY: 10},
			Pins: []SchematicPin{
				// 同一侧、相距 4 raw、各带 1 字符标签
				{Number: "1", Name: "A", X: -12, Y: 0, Net: "N1"},
				{Number: "2", Name: "K", X: -12, Y: -4, Net: "N2"},
			},
		}
	}
	in := SchematicRenderInput{
		SchemaVersion: 1,
		Zones: []SchematicRenderZone{{
			ID:    "Z",
			Title: "T",
			Layout: &SchematicLayoutResult{
				ComponentIDs: map[string]string{"D1": "cmp1"},
				PinStates:    map[string]map[string]string{},
				Placements:   []SchematicPlacement{mk("D1")},
				Wires:        nil,
				Flags:        nil,
			},
			SheetPosition: &SchematicSheetPosition{X: 0, Y: 100},
		}},
	}
	svg, err := RenderSchematicLayoutSVG(in)
	if err != nil {
		t.Fatalf("渲染失败: %v", err)
	}
	out := string(svg)

	// 两个引脚必须都画出来（几何不能少）
	if strings.Count(out, `<circle`) < 2 {
		t.Fatalf("引脚圆点被误删：%q", out)
	}
	// 标签 'A' 与 'K' 里有且只有一个被画（另一个重叠被跳过）
	drawn := 0
	for _, label := range []string{">A<", ">K<"} {
		if strings.Contains(out, label) {
			drawn++
		}
	}
	if drawn != 1 {
		t.Fatalf("相邻引脚标签应只画一个（去重），实际画了 %d 个", drawn)
	}
}
