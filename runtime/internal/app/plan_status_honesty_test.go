package app

import "testing"

// 我自己的机制踩过的坑：`plan-ack` 把"用户给了个路径"当成"有证据"，
// 于是回执里留下一条指向**不存在文件**的记录，而 `plan-status` 据此显示 ✓。
//
// 实测：`kpi-report.json` 根本不存在，S3「离线度量」却显示已完成 ——
// 那正是这套机制最不该犯的错：把"说了"当成"有了"。
func TestPlanStatusDoesNotTrustUnreadablePaths(t *testing.T) {
	project := "__plan-status-unreadable-test__"
	// 只登记了 S2，KPI 路径**没有**（因为没有读到）
	_ = savePlanReceipt(planReceipt{
		Project: project, StylePlan: "some/style-plan-report.json",
		StylePlanOK: true, KPIReport: "", ApplyAllowed: false,
	})

	rep := buildPlanStatus(project)
	byID := map[string]planStage{}
	for _, st := range rep.Stages {
		byID[st.ID] = st
	}

	if byID["S2"].Status != "done" {
		t.Fatalf("S2 有 pass 证据，应当 done，得到 %q", byID["S2"].Status)
	}
	if byID["S3"].Status == "done" {
		t.Fatal("S3 没有报告路径时必须**不是** done —— 不能把空路径当成有证据")
	}
	if byID["S4"].Status == "done" {
		t.Fatal("S4 apply_allowed 不为 true 时必须是 done 以外")
	}
	if rep.Gate != "closed" {
		t.Fatalf("证据不齐时闸门必须关，得到 %q", rep.Gate)
	}
}

// 读不到的文件必须返回 false，而不是"看起来像给了参数就算通过"。
func TestPlanReadApplyAllowedOnMissingFile(t *testing.T) {
	ok, detail := planReadApplyAllowed("__definitely-not-a-file__.json")
	if ok {
		t.Fatal("文件读不到时不许判 apply_allowed=true")
	}
	if detail == "" {
		t.Fatal("读不到也要说清原因")
	}
}

func TestPlanReadVerdictRequiresExplicitPass(t *testing.T) {
	// 缺文件
	if ok, _ := planReadVerdict("__definitely-not-a-file__.json"); ok {
		t.Fatal("缺文件不许判通过")
	}
}
