package app

import (
	"encoding/json"
	"testing"
)

// P5 兼容矩阵的接线测试。
//
// 为什么单独立这条：`evaluateHostVersion` / `hostCompatibilityFromHealth` 早就有测试，
// 但**测不出"doctor 忘了调用它们"**。实测就是这样漏的 —— `doctor` 的宿主导出里
// 根本没有 compatibility 字段，而 `daemon health` 里一直有。
// 所以这里测的是**接线**：给一份真实形状的 health 响应，doctor 必须把矩阵挂上去。
func TestDoctorAppliesHostCompatibility(t *testing.T) {
	hr := healthResult{Found: &daemonHealth{
		Port: 23111,
		Raw:  json.RawMessage(`{"windows":[{"windowId":"w1","easyedaVersion":"4.1.78"}]}`),
	}}
	doctorApplyHostCompatibility(&hr)

	if hr.HostCompatibility == nil {
		t.Fatal("doctor 没有把宿主兼容矩阵挂到结果上 —— 这正是实测漏掉的那一步")
	}
	if hr.HostCompatibility.Verdict == "" {
		t.Fatal("矩阵挂上了但没给结论")
	}
	if hr.HostCompatibility.Baseline != hostBaselineVersion {
		t.Fatalf("基线没带出来：%q", hr.HostCompatibility.Baseline)
	}
	if len(hr.HostCompatibility.Findings) != 1 {
		t.Fatalf("应当为这一个窗口给出一条判定，得到 %d", len(hr.HostCompatibility.Findings))
	}
	// 4.1.78 在 V4 主线内且高于推荐版本 → ok
	if hr.HostCompatibility.Verdict != versionSevOK {
		t.Fatalf("4.1.78 应判 ok，得到 %q（%s）", hr.HostCompatibility.Verdict,
			hr.HostCompatibility.Findings[0].Reason)
	}
}

// 没有窗口时不许 panic，也不许凭空造一个"ok"。
func TestDoctorHostCompatibilityNoWindows(t *testing.T) {
	var hr healthResult
	doctorApplyHostCompatibility(&hr) // Found == nil
	if hr.HostCompatibility != nil {
		t.Fatal("没有 health 结果时不该挂矩阵")
	}
	doctorApplyHostCompatibility(nil) // 不 panic 即可
}
