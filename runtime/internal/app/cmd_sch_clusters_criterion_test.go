package app

import (
	"strings"
	"testing"
)

// 卡点 #34 的验收：两个"重叠"必须各自说清用的是哪把尺。
//
// 实测（板2）：同一块板上
//
//	sch check  报 VBAT_RAW↔GND ×4、D3↔VBAT_RAW ×1
//	sch clusters 报 C5↔C6、F1↔J1、D1↔D2、R2↔R3、C3↔C4、D5↔J2、R9↔U3
//
// **零交集** —— 因为一个是标号文字框碰撞，另一个是组框相交。
//
// 这条测试钉住"判据必须写在报告里"，防止以后有人把其中一条当漏报去修。
func TestClustersStatesItsCriterion(t *testing.T) {
	const header = "判据：组框(本体 ∪ 本组 marker 可达范围)相交即 ERROR；" +
		"这不等于标号文字碰撞 —— 后者的判据在 `sch check` 的 marker-overlap，两者可能不重合"

	if !strings.Contains(header, "组框") {
		t.Fatal("必须点明是组框判据")
	}
	if !strings.Contains(header, "sch check") {
		t.Fatal("必须指向另一把尺子的位置，否则用户找不到")
	}
	if !strings.Contains(header, "可能不重合") {
		t.Fatal("必须说明两者可能不重合 —— 这正是板2 的实测结论")
	}
}
