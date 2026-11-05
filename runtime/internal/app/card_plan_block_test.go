package app

import "testing"

// #40 的另一半：**能起点火，还要有烟雾报警**。
//
// 上一轮只做了"落块前拦住"。如果 card 不认回执，`--unplanned` 绕过的板子
// 仍然可能拿到 `✅ 可以打样` —— 那机制就漏了一半。
func TestCardBlocksWhenNoPlanReceipt(t *testing.T) {
	res := cardResult{State: "ready", Headline: "✅ 原理图可以打样（板子还没检查）",
		Counts: map[string]int{"pass": 10}, Blockers: []cardEntry{}}
	applyPlanGateToCard(&res, "__no-such-project-for-test__")

	if res.State != "blocked" {
		t.Fatalf("没有离线规划回执时必须是 blocked，得到 %q", res.State)
	}
	if len(res.Blockers) == 0 {
		t.Fatal("必须给出一条阻塞项，否则读者不知道为什么不放行")
	}
	first := res.Blockers[0]
	if first.KPI != "offline-plan" {
		t.Fatalf("流程阻塞要能一眼认出，KPI 字段应为 offline-plan，得到 %q", first.KPI)
	}
	if first.Advice == "" {
		t.Fatal("阻塞项必须给补救动作")
	}
	// 必须排在**最前面**：流程没走完时，KPI 细节不是读者该先关心的
	if res.Headline == "" || res.Next == "" {
		t.Fatal("结论与下一步都要重写，不能留着原来的『可以打样』")
	}
}

func TestCardBlocksWhenBypassed(t *testing.T) {
	project := "__card-unplanned-test__"
	_ = savePlanReceipt(planReceipt{Project: project, Unplanned: true, PlannedAt: "2026-11-05T08:00:00Z"})

	res := cardResult{State: "ready", Counts: map[string]int{"pass": 10}, Blockers: []cardEntry{}}
	applyPlanGateToCard(&res, project)

	if res.State != "blocked" {
		t.Fatalf("--unplanned 落图的板子不许拿绿卡，得到 %q", res.State)
	}
	if len(res.Blockers) == 0 || res.Blockers[0].KPI != "offline-plan" {
		t.Fatal("必须标出流程阻塞项")
	}
}

// 证据齐全的板子**不许**被误伤 —— 否则这道门会变成"所有板都红"的噪声。
func TestCardDoesNotBlockWhenPlanEvidenceComplete(t *testing.T) {
	project := "__card-planned-test__"
	_ = savePlanReceipt(planReceipt{
		Project: project, StylePlanOK: true, ApplyAllowed: true,
		PlannedAt: "2026-11-05T08:00:00Z",
	})
	res := cardResult{State: "ready", Counts: map[string]int{"pass": 10}, Blockers: []cardEntry{}}
	applyPlanGateToCard(&res, project)

	if res.State != "ready" {
		t.Fatalf("证据齐全时不该被流程门压成 %q", res.State)
	}
	if len(res.Blockers) != 0 {
		t.Fatalf("证据齐全时不该加阻塞项：%+v", res.Blockers)
	}
}
