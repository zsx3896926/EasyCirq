package app

import "testing"

// #40 的验收：把「未过 S2 不得进器件」从一句文档变成一道门。
//
// 实测背景：板1/板2 前几十轮跳过 S1–S4 直接落图，之后一直在补几何。
// 文档管不住人，闸门才管得住 —— 这三条钉住闸门的三个状态。
func TestPlanGateRefusesWithoutReceipt(t *testing.T) {
	// 用一个不存在的工程名，保证读不到任何回执
	g := planGate("__no-such-project-for-test__", "", false)
	if g.Allow {
		t.Fatal("没有规划回执时必须拒绝落块 —— 这是机制，不是建议")
	}
	if len(g.HowTo) == 0 {
		t.Fatal("拒绝时必须给出凑齐证据的确切步骤，否则用户只知道被拦、不知道怎么办")
	}
	// 步骤里必须包含"绕过要留痕"这条出口，否则用户会去改代码
	found := false
	for _, h := range g.HowTo {
		if contains(h, "unplanned") {
			found = true
		}
	}
	if !found {
		t.Fatal("必须说明确实要先落图时可以用 --unplanned（并留痕）")
	}
}

func TestPlanGateAllowsExplicitUnplannedButRecordsIt(t *testing.T) {
	g := planGate("__no-such-project-for-test__", "P1", true)
	if !g.Allow {
		t.Fatal("--unplanned 应当放行")
	}
	if !g.Receipt.Unplanned {
		t.Fatal("放行之后必须在回执里留痕 —— 绕过流程可以，但会被记下来")
	}
	if g.Receipt.Note == "" {
		t.Fatal("留痕要带一句人能看懂的理由")
	}
}

// 回执存在但证据不全（比如只跑了 S2 没跑 S4）时，仍然要拦。
func TestPlanGateRefusesIncompleteEvidence(t *testing.T) {
	project := "__plan-gate-incomplete-test__"
	_ = savePlanReceipt(planReceipt{
		Project: project, StylePlanOK: true, ApplyAllowed: false,
	})
	g := planGate(project, "", false)
	if g.Allow {
		t.Fatal("只有 S2 没有 S4 时必须继续拦 —— 「跑了一半」不等于「跑过了」")
	}
	if len(g.HowTo) == 0 {
		t.Fatal("要被拦，也要给下一步")
	}
}
