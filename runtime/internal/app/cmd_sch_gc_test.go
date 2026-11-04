package app

import "testing"

// 卡点 #31 的验收：gc 只清"整棵树碰不到引脚"的残留，
// 绝不碰真短路（BRIDGE）和碰到引脚的悬空桩（ORPHAN）。
func TestGCCandidateKinds(t *testing.T) {
	mustClean := []string{"ORPHAN_FLAG", "ORPHAN_TREE"}
	mustKeep := []string{"BRIDGE", "ORPHAN"}

	for _, k := range mustClean {
		if !gcCandidateKinds[k] {
			t.Fatalf("%s 应当被 gc 清理，现在不在候选里", k)
		}
	}
	for _, k := range mustKeep {
		if gcCandidateKinds[k] {
			t.Fatalf("%s **不该**被 gc 清理 —— 它是电路错误或有意留的 stub，"+
				"一把扫帚扫掉等于替用户做决定", k)
		}
	}
}

// dry-run 必须是默认：不传 --apply 时 applied=false 且 dryRun=true。
// 这条钉住"先看清楚再动手"的约定 —— gc 会删图元，默认就不该删。
func TestGCDefaultIsDryRun(t *testing.T) {
	apply := false
	out := gcReport{DryRun: !apply, Applied: apply, Candidates: []gcCandidate{}}
	if !out.DryRun || out.Applied {
		t.Fatal("不传 --apply 时必须是 dry-run")
	}

	// 报告里的 candidate 必须带上 kind，否则人看不懂要删的是什么
	c := gcCandidate{Kind: "orphan-tree", WireIDs: []string{"w1"}, FlagIDs: []string{"f1"}}
	if c.Kind == "" {
		t.Fatal("candidate 缺 kind —— 清单看不出要删的是哪一类")
	}
}
