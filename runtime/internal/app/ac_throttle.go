package app

// ac_throttle.go — 修卡点 #9 / #10（板1 实测）：
//
// #9 一次性 118 条 `connect_pin` 把连接器压到 DEGRADED（失败率 30%），
//    之后每次写入都带着"可能已经落上了"的不确定性。
// #10 在降级状态下反复 `--replace` 会**震荡**：已连引脚数在 76 和 100 之间
//    来回跳 —— 因为它是"删旧+重连"，删除落上而重连没落上（或反之），
//    每一轮都在拆上一轮的成果。**修复动作本身在破坏。**
//
// 前提是 daemon 的 warnings 要能被代码读到（见 dispatch.go 的 Warnings 字段）。
// 有了它，批处理才能做两件事：
//   1. 检测到降级 → **放慢**后续写入，而不是继续一口气打
//   2. 降级 + `--replace` → **直接拒绝**，不在不确定的状态下删改

import (
	"strings"
	"time"
)

// acDegradedWarning 判断这次响应是不是在说"连接器降级了"。
//
// 依赖 daemon 的文案是刻意的：这条告警是本仓库自己发的，改文案要一起改这里。
// 同时认英文与中文两种写法，因为不同版本的 daemon 可能说不同的话。
func acDegradedWarning(res *actionResult) bool {
	if res == nil {
		return false
	}
	for _, w := range res.Warnings {
		low := strings.ToLower(w)
		if strings.Contains(low, "degraded") || strings.Contains(w, "降级") {
			return true
		}
	}
	return false
}

// acThrottle 是批量写入的节流器。
//
// 正常状态下不等待；一旦看到降级告警，就把每次写入的间隔拉长，
// 并且**不自动恢复** —— 降级是"最近的失败率"统计出来的，短时间反复试探
// 只会继续压着它。等这一批跑完，连接器自己会缓过来。
type acThrottle struct {
	base   time.Duration // 正常节奏（0 = 不等待）
	slo    time.Duration // 降级后的节奏
	sleeps int           // 已经因为降级等待过几次（供报告用）
}

func newAcThrottle() *acThrottle {
	return &acThrottle{base: 0, slo: 1500 * time.Millisecond}
}

// observe 看一次响应；降级则睡一会儿。返回是否发生了等待。
func (t *acThrottle) observe(res *actionResult, sleep func(time.Duration)) bool {
	if !acDegradedWarning(res) {
		if t.base > 0 {
			sleep(t.base)
		}
		return false
	}
	t.sleeps++
	sleep(t.slo)
	return true
}

// refuseReason 判断这一批是否**根本不该跑**。
//
// 只有一种情况：`--replace`（破坏性：删旧标号再重连）+ 已经观察到降级。
// 此时继续跑就是在不确定性里删改，正是板1 震荡的原因。
// 返回非空字符串就是拒绝的理由。
func (t *acThrottle) refuseReason(replace bool, degraded bool) string {
	if replace && degraded {
		return "连接器已降级（recent failure rate 偏高），此时 --replace 会删旧标号后重连；" +
			"在降级状态下删除可能落上而重连没落上，反复跑会来回震荡、越修越乱。" +
			"请先等连接器恢复（`easycirq doctor` 看到 connected 且无 degraded 警告），" +
			"或去掉 --replace 只补连缺失的引脚。"
	}
	return ""
}
