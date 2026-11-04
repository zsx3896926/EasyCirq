package app

import (
	"testing"
	"time"
)

// 卡点 #4 的验收：**能等就等，等不到如实报 blocked**。
// 关键是别把不相干的故障也拖进去白等 15 秒，更别把"没连上"说成通过。
func TestGateBlockedByDisconnect(t *testing.T) {
	cases := []struct {
		name string
		rep  *gateReport
		want bool
	}{
		{"连接器没连上 → 认", &gateReport{Verdict: "blocked",
			Blockers: []string{"layout-lint 没能跑起来: no connected window for project x"}}, true},
		{"connector 版本说没连 → 认", &gateReport{Verdict: "blocked",
			Blockers: []string{"no connected connector"}}, true},
		{"别的 blocked 原因 → 不认", &gateReport{Verdict: "blocked",
			Blockers: []string{"check stage 崩了: panic: nil map"}}, false},
		{"fail 不认", &gateReport{Verdict: "fail",
			Blockers: []string{"1 overlap"}}, false},
		{"pass 不认", &gateReport{Verdict: "pass"}, false},
		{"nil 不认", nil, false},
	}
	for _, c := range cases {
		if got := gateBlockedByDisconnect(c.rep); got != c.want {
			t.Errorf("%s: got %v want %v", c.name, got, c.want)
		}
	}
}

// 第一次 blocked 之后重跑成功 → 返回 pass，并且标记"等过"。
func TestRetryGateAfterReconnectRecovers(t *testing.T) {
	blocked := &gateReport{Verdict: "blocked",
		Blockers: []string{"no connected window for project x"}}
	pass := &gateReport{Verdict: "pass"}

	calls := 0
	got, waited := retryGateAfterReconnect(blocked, func() (*gateReport, error) {
		calls++
		if calls < 3 {
			return blocked, nil
		}
		return pass, nil
	}, func(time.Duration) {})

	if !waited {
		t.Fatal("应当标记为等过")
	}
	if got.Verdict != "pass" {
		t.Fatalf("重连后应当拿到 pass，实际 %s", got.Verdict)
	}
	if calls != 3 {
		t.Fatalf("应当重试到第 3 次才成功，实际 %d 次", calls)
	}
}

// 一直连不上 → 最终仍然如实报 blocked，**绝不变成 pass 或 fail**。
func TestRetryGateAfterReconnectGivesUpHonestly(t *testing.T) {
	blocked := &gateReport{Verdict: "blocked",
		Blockers: []string{"no connected window for project x"}}

	got, waited := retryGateAfterReconnect(blocked, func() (*gateReport, error) {
		return blocked, nil
	}, func(time.Duration) {})

	if !waited {
		t.Fatal("应当尝试过")
	}
	if got.Verdict != "blocked" {
		t.Fatalf("等不到连接器时必须仍然是 blocked，实际 %s —— 把没连上说成通过是绝对不能的", got.Verdict)
	}
}

// 不是掉线导致的 blocked → 不重试、不等待，避免为一个不相干的故障白等。
func TestRetryGateDoesNotWaitForUnrelatedBlocked(t *testing.T) {
	other := &gateReport{Verdict: "blocked", Blockers: []string{"某个 stage 崩了"}}
	calls := 0
	got, waited := retryGateAfterReconnect(other, func() (*gateReport, error) {
		calls++
		return other, nil
	}, func(time.Duration) {})

	if waited || calls != 0 {
		t.Fatalf("不相干的 blocked 不该重试：waited=%v calls=%d", waited, calls)
	}
	if got.Verdict != "blocked" {
		t.Fatalf("verdict 不该被改，实际 %s", got.Verdict)
	}
}
