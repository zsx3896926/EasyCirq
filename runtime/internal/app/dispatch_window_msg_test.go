package app

import (
	"strings"
	"testing"
)

// 板1 实测：daemon 健康、连接器连着，只是那个工程没在编辑器里打开，
// 而旧文案把人指向 `daemon health` —— 白查一圈。
//
// 这条钉住两种情况的措辞必须不同：
//  1. 一个窗口都没有 → 连接器没挂上，查 daemon / 重导连接器
//  2. 有窗口但没开这个工程 → 列出现在开着哪些，并明说"这不是 daemon 问题"
func TestSelectWindowMessageDistinguishesNoProjectFromNoWindow(t *testing.T) {
	proj := "c5443fece5a548ba9e41b35951ee124c"

	// 情况 2：有窗口，但开的是别的工程
	withOther := []healthWindow{{
		WindowID: "w1",
	}}
	withOther[0].Context.ProjectName = "板2-24V隔离控制板"
	withOther[0].Context.ProjectUUID = "23ce6e4eb178464cb0b709920da3b26c"
	_, err := selectWindow(withOther, proj, "")
	if err == nil {
		t.Fatal("工程没开时必须报错")
	}
	msg := err.Error()
	if !strings.Contains(msg, "没有") && !strings.Contains(msg, "no window has project") {
		t.Fatalf("要说清是「没有窗口开着这个工程」，实际：%q", msg)
	}
	if !strings.Contains(msg, "板2") && !strings.Contains(msg, "currently open") {
		t.Fatalf("要把现在开着哪些列出来，否则用户不知道开错了哪个，实际：%q", msg)
	}
	if !strings.Contains(msg, "this is not a daemon problem") && !strings.Contains(msg, "不是 daemon") {
		t.Fatalf("必须点明这不是 daemon 问题 —— 旧文案正是在这里把人带偏，实际：%q", msg)
	}

	// 情况 1：一个窗口都没有 —— 仍然该指向 daemon / 连接器
	_, err2 := selectWindow(nil, proj, "")
	if err2 == nil {
		t.Fatal("没有窗口时必须报错")
	}
	if !strings.Contains(err2.Error(), "daemon health") {
		t.Fatalf("完全没有窗口时才该提 daemon health，实际：%q", err2.Error())
	}
	if strings.Contains(err2.Error(), "currently open") {
		t.Fatalf("没有窗口时不该列出「现在开着哪些」，实际：%q", err2.Error())
	}
}
