package app

// cmd_panel_cancel.go — 面板上"停止正在跑的操作"（P2）。
//
// 为什么需要它：`sch gate` 在真实板子上要跑几十秒，`phase advance` 也可能在等连接器。
// 一个没有停止键的操作面板，在"跑不动"的时候只能干等或刷新页面 —— 而刷新页面
// **不会**终止已经开始的那次 CLI 调用，它只是不再看它了。
//
// 实现要点：
//   • 同一时刻只允许一个操作在跑。两个 gate 并行没有意义，还会互相抢连接器。
//   • 停止是**取消 context**（exec.CommandContext 会杀掉子进程），不是设个标志 ——
//     exec 出来的 CLI 不会检查我们的标志。
//   • 结果里如实标注 `cancelled`，让前端区分"跑完了"和"被停了"。
//   • 这里**不做判定**：停下来的那半截输出原样保留，结论仍由 gate/card 自己说。

import (
	"context"
	"fmt"
	"sync"
	"time"
)

var (
	panelRunMu      sync.Mutex
	panelRunCurrent *panelRunning
)

// panelRunning 是一次正在执行的面板操作。
type panelRunning struct {
	Cmd    string
	Args   []string
	Start  time.Time
	cancel context.CancelFunc
}

// panelRunBusy 是"已有操作在跑"的返回体。
type panelRunBusy struct {
	Busy bool     `json:"busy"`
	Cmd  string   `json:"cmd,omitempty"`
	Args []string `json:"args,omitempty"`
	Note string   `json:"note,omitempty"`
}

// panelCancelResult 是 /api/cancel 的返回体。
type panelCancelResult struct {
	Cancelled bool   `json:"cancelled"`
	Cmd       string `json:"cmd,omitempty"`
	Note      string `json:"note,omitempty"`
}

// panelAcquireRun 占用"正在跑"的位置。已有在跑时返回它，让调用方如实报冲突
// —— 静默排队会让用户以为按钮没反应。
func panelAcquireRun(name string, args []string, cancel context.CancelFunc) (*panelRunning, *panelRunning) {
	panelRunMu.Lock()
	defer panelRunMu.Unlock()
	if panelRunCurrent != nil {
		return nil, panelRunCurrent
	}
	r := &panelRunning{Cmd: name, Args: args, Start: time.Now(), cancel: cancel}
	panelRunCurrent = r
	return r, nil
}

// panelFinishRun 释放槽位（只在它仍是当前那个时释放，避免误清后到者）。
func panelFinishRun(r *panelRunning) {
	panelRunMu.Lock()
	defer panelRunMu.Unlock()
	if panelRunCurrent == r {
		panelRunCurrent = nil
	}
}

// panelCancelCurrent 停掉正在跑的那一个。
func panelCancelCurrent() panelCancelResult {
	panelRunMu.Lock()
	r := panelRunCurrent
	panelRunMu.Unlock()
	if r == nil {
		return panelCancelResult{Cancelled: false, Note: "现在没有操作在跑"}
	}
	if r.cancel != nil {
		r.cancel()
	}
	return panelCancelResult{Cancelled: true, Cmd: r.Cmd,
		Note: fmt.Sprintf("%s 已停止；它已经打印的输出仍会原样返回（结论不完整就是「没跑完」）", r.Cmd)}
}
