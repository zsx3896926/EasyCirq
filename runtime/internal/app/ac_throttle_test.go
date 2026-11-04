package app

import (
	"testing"
	"time"
)

// 卡点 #9 / #10 的验收。两条都属于"批量写入"这一类动作的通病，
// 板2 的网络数更多，只会更严重，所以这里必须钉死。

func TestAcDegradedWarning(t *testing.T) {
	cases := []struct {
		name string
		res  *actionResult
		want bool
	}{
		{"英文降级警告", &actionResult{Warnings: []string{
			"connector looks DEGRADED under load (recent failure rate 45%) — this write may have LANDED"}}, true},
		{"中文降级", &actionResult{Warnings: []string{"连接器已降级"}}, true},
		{"无关警告", &actionResult{Warnings: []string{"27 pre-existing geometry findings"}}, false},
		{"没有警告", &actionResult{}, false},
		{"nil", nil, false},
	}
	for _, c := range cases {
		if got := acDegradedWarning(c.res); got != c.want {
			t.Errorf("%s: got %v want %v", c.name, got, c.want)
		}
	}
}

// 降级之后必须**放慢**，而不是继续一口气打。
func TestThrottleSlowsDownAfterDegraded(t *testing.T) {
	th := newAcThrottle()
	var slept []time.Duration
	sleep := func(d time.Duration) { slept = append(slept, d) }

	th.observe(&actionResult{}, sleep) // 正常：不睡
	if len(slept) != 0 {
		t.Fatalf("正常状态不该等待，实际等了 %v", slept)
	}

	degraded := &actionResult{Warnings: []string{"connector looks DEGRADED"}}
	th.observe(degraded, sleep)
	th.observe(degraded, sleep)
	if len(slept) != 2 {
		t.Fatalf("降级后每次都该等待，实际等了 %d 次", len(slept))
	}
	for _, d := range slept {
		if d < time.Second {
			t.Fatalf("降级后的等待太短：%v（继续压着它只会更糟）", d)
		}
	}
}

// `--replace` + 降级 = **必须拒绝**。这是板1 震荡的直接原因：
// 它在"删旧标号后重连"的过程中反复拆掉自己上一轮的成果。
func TestThrottleRefusesReplaceWhenDegraded(t *testing.T) {
	th := newAcThrottle()
	reason := th.refuseReason(true, true)
	if reason == "" {
		t.Fatal("降级状态下 --replace 必须被拒绝 —— 这正是板1 震荡的原因")
	}
	if !contains(reason, "震荡") {
		t.Errorf("拒绝理由要说清会发生什么，实际：%s", reason)
	}
}

func TestThrottleAllowsReplaceWhenHealthy(t *testing.T) {
	th := newAcThrottle()
	if r := th.refuseReason(true, false); r != "" {
		t.Fatalf("健康时不该拒绝 --replace：%s", r)
	}
	// 不带 --replace 时，降级也不该拒绝 —— 补连缺失引脚是安全的
	if r := th.refuseReason(false, true); r != "" {
		t.Fatalf("不带 --replace 时不该拒绝：%s", r)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (func() bool {
		for i := 0; i+len(sub) <= len(s); i++ {
			if s[i:i+len(sub)] == sub {
				return true
			}
		}
		return false
	})()
}
