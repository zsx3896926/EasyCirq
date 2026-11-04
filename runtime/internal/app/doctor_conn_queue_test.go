package app

import (
	"strings"
	"testing"
)

// 卡点 #36 的验收：`doctor` 必须把"动作队列 wedge"当成**一等状态**报出来。
//
// 实测代价：板2 的 req_683/687/738/742 从第 22 轮起就在每次响应里出现，
// 一直到第 37 轮 place 超时才第一次被读出来 —— 中间十几轮的所有几何/电气判断
// 都建立在状态未知的画布上。
func TestDoctorConnQueueWedged(t *testing.T) {
	q := doctorConnQueueOf(schSeqCounters{
		Known:        true,
		SeqAbandoned: 7,
		AbandonedIDs: []string{"req_683", "req_687"},
	})
	if q.Verdict != "wedged" {
		t.Fatalf("7 个被放弃的动作应当判 wedged，得到 %q", q.Verdict)
	}
	if q.Abandoned != 7 {
		t.Fatalf("条数要如实带出，得到 %d", q.Abandoned)
	}
	// 处置必须是那句**唯一有效**的话：完全退出重启，不是刷新。
	if !strings.Contains(q.Advice, "完全退出") {
		t.Fatalf("必须说明要完全退出重开，实际：%q", q.Advice)
	}
	// 而且必须提醒在此之前别把落块失败当归档的产品缺陷修。
	if !strings.Contains(q.Advice, "别把") {
		t.Fatalf("必须提醒不要把落块失败当产品缺陷，实际：%q", q.Advice)
	}
}

// 干净的队列不能说成有问题（否则每次 doctor 都在喊狼来了）。
func TestDoctorConnQueueClean(t *testing.T) {
	q := doctorConnQueueOf(schSeqCounters{Known: true, SeqAbandoned: 0})
	if q.Verdict != "clean" {
		t.Fatalf("0 个被放弃应当判 clean，得到 %q", q.Verdict)
	}
	if q.Advice != "" {
		t.Fatalf("干净时不该给建议，实际：%q", q.Advice)
	}
}

// 老连接器不带计数器 → 必须是 unknown，**不能**当成 clean。
// 「没数据」不等于「没问题」—— 这条是 schSeqCounters.Known 存在的全部理由。
func TestDoctorConnQueueUnknownIsNotClean(t *testing.T) {
	q := doctorConnQueueOf(schSeqCounters{Known: false})
	if q.Verdict == "clean" {
		t.Fatal("老连接器没带计数器时不许判 clean —— 那是凭空造证据")
	}
	if q.Verdict != "unknown" {
		t.Fatalf("应当是 unknown，得到 %q", q.Verdict)
	}
	if !strings.Contains(q.Advice, "升级连接器") {
		t.Fatalf("unknown 也要给下一步，实际：%q", q.Advice)
	}
}
