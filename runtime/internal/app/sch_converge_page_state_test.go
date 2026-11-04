package app

import "testing"

// 卡点 #25 的验收：台账里"这块在这页放不下"的测量**必须随页面内容变化而失效**。
//
// 板1b 实测：把页面清空之后，它仍然拿上一轮的 545×716 拦我，而同一时刻
// --dry-run（不走台账）当场就能规划成功。证据过期了却仍被当作证据。
func TestConvergeKeyInvalidatesOnPageStateChange(t *testing.T) {
	base := schConvergeKey{Op: "block-apply", Page: "P1", Target: "block.x"}

	empty := base
	empty.PageState = "0"
	busy := base
	busy.PageState = "13"

	if empty.id() == busy.id() {
		t.Fatal("页面从 0 个图元变成 13 个，台账 key 却相同 —— 旧测量会被继续当成证据")
	}

	// 同一页、同一状态 → 同一个 key（否则连续失败计数永远归零，收敛门失效）
	a := base
	a.PageState = "13"
	b := base
	b.PageState = "13"
	if a.id() != b.id() {
		t.Fatal("页面状态相同却没有命中同一条台账 —— 连续失败计数会失效")
	}
}

// 老台账没有 PageState 这一维，必须保持向后兼容（空串时不拼进去）。
func TestConvergeKeyWithoutPageStateStaysCompatible(t *testing.T) {
	k := schConvergeKey{Op: "block-apply", Page: "P1", Target: "block.x"}
	want := "block-apply|P1|block.x"
	if got := k.id(); got != want {
		t.Fatalf("老 key 形式变了：got %q want %q", got, want)
	}
}
