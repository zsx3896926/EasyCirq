package app

// gate_reconnect.go — 修卡点 #4（板1 实测）：
//
// daemon 因 CLI 版本升级自动重启后，连接器要几秒才重连上。这期间跑 `sch gate`
// 必然得到 BLOCKED（"no connected window"）。文案已经说清"不是板子的问题"，
// 但仍然要求用户自己数着秒重试 —— 每次升级都会撞一次，很烦。
//
// 这里的原则：**能等就等，等不到再说**。等待是有上限的（15 秒），
// 超时后仍然如实报 BLOCKED，绝不把"没连上"说成"通过"或"失败"。

import (
	"strings"
	"time"
)

const (
	// gateReconnectWait 是愿意为连接器重连等多久。
	// 实测重连约 8–10 秒；给到 15 秒留余量，又不至于让人以为卡死。
	gateReconnectWait = 15 * time.Second
	// gateReconnectPoll 是轮询间隔。
	gateReconnectPoll = time.Second
)

// gateBlockedByDisconnect 判断这次 BLOCKED 是不是"连接器没连上"造成的。
//
// 只认这一类原因：其余 BLOCKED（比如某个 stage 崩了）立刻返回，
// 不要为了一个不相干的故障白等 15 秒。
func gateBlockedByDisconnect(rep *gateReport) bool {
	if rep == nil || rep.Verdict != "blocked" {
		return false
	}
	for _, b := range rep.Blockers {
		low := strings.ToLower(b)
		if strings.Contains(low, "no connected window") ||
			strings.Contains(low, "no connected connector") ||
			strings.Contains(low, "window not found") {
			return true
		}
	}
	return false
}

// retryGateAfterReconnect 在一次 BLOCKED 之后，等连接器回来再重跑。
//
// 返回最终报告，以及"是否真的等过"（用于告诉用户我们在做什么）。
func retryGateAfterReconnect(rep *gateReport,
	rerun func() (*gateReport, error), sleep func(time.Duration)) (*gateReport, bool) {

	if !gateBlockedByDisconnect(rep) {
		return rep, false
	}
	// 按**次数**重试而不是按墙上时间：这样单测可以用 no-op sleep 瞬间跑完，
	// 而生产里的节奏仍是每 gateReconnectPoll 一次、总共 gateReconnectWait 那么久。
	attempts := int(gateReconnectWait / gateReconnectPoll)
	waited := false
	for i := 0; i < attempts; i++ {
		sleep(gateReconnectPoll)
		waited = true
		next, err := rerun()
		if err != nil || next == nil {
			break
		}
		rep = next
		if !gateBlockedByDisconnect(rep) {
			break
		}
	}
	return rep, waited
}
