package app

// card_plan_block.go — 让交付卡认「离线规划」这一关（补上闸门的另一半）。
//
// 上一轮只做了"落块前拦住"。如果只是那样，`--unplanned` 绕过的板子仍然可能
// 拿到 `✅ 可以打样` —— 机制就漏了一半：**能起点火，却没有烟雾报警**。
//
// 所以这里把两件事接进 card：
//   1. 回执缺失 → 流程根本没走完 → 不能是绿卡
//   2. 回执 `unplanned: true` → 绕过流程的板子 → 同样不能是绿卡
//
// 两条都归到 `blocked`（不是 `incomplete`）：`incomplete` 读起来像"再补点资料"，
// 而这两条是"流程没走完"，补救动作完全不同（要回去做 S1–S4），必须分开。

import "fmt"

// planCardBlocker 根据回执决定是否给出一条"流程"级阻塞。
func planCardBlocker(project string) (entry cardEntry, blocked bool) {
	r, ok := loadPlanReceipt(project)
	if !ok {
		return cardEntry{
			KPI:    "offline-plan",
			Plain:  "离线规划：没有回执",
			Advice: "先跑 S1 规格 → S2 style-plan（未过不得进器件）→ S3/S4 KPI 连续 2 轮 → sch plan-ack",
			Reason: "这块板没有离线规划回执，说明 S1–S4 没走完就开始落图了",
		}, true
	}
	if r.Unplanned {
		return cardEntry{
			KPI:    "offline-plan",
			Plain:  "离线规划：绕过了",
			Advice: "补 S1–S4 后重新落图，或至少补齐 style-plan + KPI 再 plan-ack",
			Reason: fmt.Sprintf("这块板是用 --unplanned 落图的（%s）——流程没走完，与电路对错无关", r.PlannedAt),
		}, true
	}
	if !r.StylePlanOK || !r.ApplyAllowed {
		return cardEntry{
			KPI:    "offline-plan",
			Plain:  "离线规划：证据不全",
			Advice: "补齐 S2 的风格门（verdict=pass）与 S4 的 KPI 门（apply_allowed=true），再 plan-ack",
			Reason: fmt.Sprintf("回执存在但 stylePlanChecked=%v applyAllowed=%v", r.StylePlanOK, r.ApplyAllowed),
		}, true
	}
	return cardEntry{}, false
}

// applyPlanGateToCard 把流程阻塞插到最前面，并把结论压成 blocked。
//
// 为什么插到最前：**流程没走完时，KPI 的那些细节不是读者该先关心的事**。
// 先告诉他"流程没走完"，再谈具体缺陷。
func applyPlanGateToCard(result *cardResult, project string) {
	entry, blocked := planCardBlocker(project)
	if !blocked {
		return
	}
	result.Blockers = append([]cardEntry{entry}, result.Blockers...)
	result.Counts["fail"]++
	result.State = "blocked"
	result.Headline = "❌ 还不能打样"
	result.Next = "这块板没走完离线规划（S1–S4）—— 先补齐流程，KPI 的细节在那之后才有意义"
}
