package app

import "testing"

// 假失败这条路径在真机上依赖连接器降级，很难稳定复现，但**判定逻辑必须确定**。
// 这几个用例就是"到底落没落"的验收：判错一个方向，调用方要么造重复器件，
// 要么以为没落下而白重试。
func TestScanForPlacement(t *testing.T) {
	comps := []placedComponent{
		{ComponentType: "sheet", Designator: "", X: 0, Y: 0}, // 图框：也是 component，但不是器件
		{ComponentType: "part", Designator: "R1", X: 100, Y: 100},
		{ComponentType: "part", Designator: "C1", X: 200.5, Y: 300},
	}

	t.Run("按位号命中", func(t *testing.T) {
		ok, why := scanForPlacement(comps, "R1", 999, 999)
		if !ok {
			t.Fatalf("应当判定为已落上，实际没落：%s", why)
		}
	})

	t.Run("位号不在就是没落上", func(t *testing.T) {
		ok, why := scanForPlacement(comps, "R9", 100, 100)
		if ok {
			t.Fatalf("位号不存在却判定落上了 —— 会导致误以为成功：%s", why)
		}
	})

	t.Run("图框不算器件", func(t *testing.T) {
		ok, _ := scanForPlacement(comps, "", 0, 0)
		if ok {
			t.Fatal("把图框当成了器件 —— 会让你以为放置成功")
		}
	})

	t.Run("无位号时按坐标命中", func(t *testing.T) {
		ok, why := scanForPlacement(comps, "", 200.8, 299.4)
		if !ok {
			t.Fatalf("坐标误差在 1 以内应当命中：%s", why)
		}
	})

	t.Run("坐标差太远就是没落上", func(t *testing.T) {
		ok, _ := scanForPlacement(comps, "", 500, 500)
		if ok {
			t.Fatal("坐标对不上却判定落上了")
		}
	})

	t.Run("空文档判定没落上", func(t *testing.T) {
		ok, _ := scanForPlacement(nil, "R1", 1, 1)
		if ok {
			t.Fatal("读回是空的却判定落上了 —— 没有证据不能算成功")
		}
	})
}
