package app

import "testing"

// 「导线不许穿过文字预留区」必须进**最终几何校验**的回归测试。
//
// 实锤（读源码）：validateLibGeometry 原来只有 foreign-stem / marker-stem /
// pin-exit-foreign-wire / pin-exit-marker，**没有 wire-vs-text**。
// 逐边走线时会拒，但最终导线可能来自 join / maze 重建那条通路，约束就漏了。
//
// 两条断言：
//   · 带 TextBBoxes 且导线穿过 → 必须报错
//   · 不带 TextBBoxes → 一条都不查（默认行为不变）
func TestWireTextClearanceInertWithoutTextBoxes(t *testing.T) {
	w := powerLayoutWire{Net: "N1", Points: [][2]float64{{-50, 5}, {50, 5}}}
	p := powerLayoutPlan{
		Placements: []powerLayoutPlacement{{
			Designator: "U1",
			X:          0, Y: 0,
			BBox: layoutBBox{MinX: 0, MinY: 0, MaxX: 20, MaxY: 20},
			Pins: []powerLayoutPin{{Number: "1", X: -5, Y: 10, Net: "N1"}},
		}},
		Wires: []powerLayoutWire{w},
	}
	if err := libValidateWireTextClearance(&p); err != nil {
		t.Fatalf("没有 TextBBoxes 时不该报错：%v", err)
	}
}

func TestWireTextClearanceRejectsCrossing(t *testing.T) {
	w := powerLayoutWire{Net: "N1", Points: [][2]float64{{-50, 25}, {50, 25}}}
	p := powerLayoutPlan{
		Placements: []powerLayoutPlacement{{
			Designator: "U1",
			X:          0, Y: 0,
			BBox:       layoutBBox{MinX: 0, MinY: 0, MaxX: 20, MaxY: 20},
			TextBBoxes: []layoutBBox{{MinX: 0, MinY: 20, MaxX: 12, MaxY: 30}},
			Pins:       []powerLayoutPin{{Number: "1", X: -5, Y: 10, Net: "N1"}},
		}},
		Wires: []powerLayoutWire{w},
	}
	if err := libValidateWireTextClearance(&p); err == nil {
		t.Fatal("导线穿过文字预留区却放过了")
	}
}

func TestWireTextClearanceAllowsClearRoute(t *testing.T) {
	w := powerLayoutWire{Net: "N1", Points: [][2]float64{{-50, -30}, {50, -30}}}
	p := powerLayoutPlan{
		Placements: []powerLayoutPlacement{{
			Designator: "U1",
			X:          0, Y: 0,
			BBox:       layoutBBox{MinX: 0, MinY: 0, MaxX: 20, MaxY: 20},
			TextBBoxes: []layoutBBox{{MinX: 0, MinY: 20, MaxX: 12, MaxY: 30}},
			Pins:       []powerLayoutPin{{Number: "1", X: -5, Y: 10, Net: "N1"}},
		}},
		Wires: []powerLayoutWire{w},
	}
	if err := libValidateWireTextClearance(&p); err != nil {
		t.Fatalf("干净路线被误判：%v", err)
	}
}
