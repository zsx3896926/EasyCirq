package app

import "testing"

// 「读路径不认 --page」这一族的机制修复（#24 / #39 / 板2 清空脚本）。
//
// 三次都指向同一件事：**切页之后页面没就绪，读到的 0 被当成"空页"**。
// 于是"删 30 个器件"变成"报告已空、什么也没删"，退出码还是 0。
func TestSettleGateErrorsOnlyWhenItActuallySwitched(t *testing.T) {
	// 切过页 + 没就绪 → 必须报错：这时读到的器件数不可信
	if err := settleGateError(false, true); err == nil {
		t.Fatal("切页后没就绪必须报错 —— 否则 0 个器件会被当成空页")
	} else {
		msg := err.Error()
		if !contains(msg, "不可信") {
			t.Fatalf("要说清数据不可信，而不是含糊报错：%q", msg)
		}
		if !contains(msg, "不要当成空页") {
			t.Fatalf("要点名这个具体误判：%q", msg)
		}
	}

	// 就绪 → 不报错
	if err := settleGateError(true, true); err != nil {
		t.Fatalf("就绪时不该报错：%v", err)
	}

	// 没切页 → 不报错。本来就在这一页，探针稳不稳不影响"这一页此刻就是这样"
	if err := settleGateError(false, false); err != nil {
		t.Fatalf("没切页时不该报错：%v", err)
	}

	// 没切页且就绪 → 不报错
	if err := settleGateError(true, false); err != nil {
		t.Fatalf("不该报错：%v", err)
	}
}
