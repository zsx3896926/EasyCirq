package app

import "testing"

// 位号预留区校验的回归测试。
//
// 背景（friction #69）：摆放原本只避让本体，于是两个器件可以贴到"位号压位号"，
// 渲染阶段才报 component label reservation collision。
// 新增 libValidateLabelReservations：
//   · **没有 TextBBoxes 时一条都不查**（默认行为完全不变）
//   · 有 TextBBoxes 时，预留区互撞、或压到**别人**本体，都要拒
func TestLabelReservationsIgnoredWithoutTextBoxes(t *testing.T) {
	p := powerLayoutPlan{Placements: []powerLayoutPlacement{
		{Designator: "U1", BBox: layoutBBox{MinX: 0, MinY: 0, MaxX: 20, MaxY: 20},
			Pins: []powerLayoutPin{{Number: "1", X: -5, Y: 10, Net: "N1"}}},
		{Designator: "U2", BBox: layoutBBox{MinX: 20, MinY: 0, MaxX: 40, MaxY: 20},
			Pins: []powerLayoutPin{{Number: "1", X: 45, Y: 10, Net: "N2"}}},
	}}
	if err := libValidateLabelReservations(&p); err != nil {
		t.Fatalf("没有 TextBBoxes 时不该报错：%v", err)
	}
}

func TestLabelReservationsRejectOverlap(t *testing.T) {
	p := powerLayoutPlan{Placements: []powerLayoutPlacement{
		{Designator: "U1", BBox: layoutBBox{MinX: 0, MinY: 0, MaxX: 20, MaxY: 20},
			TextBBoxes: []layoutBBox{{MinX: 0, MinY: 20, MaxX: 12, MaxY: 30}}},
		{Designator: "U2", BBox: layoutBBox{MinX: 2, MinY: 0, MaxX: 22, MaxY: 20},
			TextBBoxes: []layoutBBox{{MinX: 2, MinY: 20, MaxX: 14, MaxY: 30}}},
	}}
	if err := libValidateLabelReservations(&p); err == nil {
		t.Fatal("预留区互撞却放过了")
	}
}

func TestLabelReservationsRejectLabelOnOtherBody(t *testing.T) {
	p := powerLayoutPlan{Placements: []powerLayoutPlacement{
		{Designator: "U1", BBox: layoutBBox{MinX: 0, MinY: 0, MaxX: 20, MaxY: 20},
			TextBBoxes: []layoutBBox{{MinX: 18, MinY: 18, MaxX: 30, MaxY: 28}}},
		{Designator: "U2", BBox: layoutBBox{MinX: 22, MinY: 20, MaxX: 40, MaxY: 40}},
	}}
	if err := libValidateLabelReservations(&p); err == nil {
		t.Fatal("预留区压在别人本体上却放过了")
	}
}
