package app

// cmd_panel_run.go — 面板的"操作"端点（P3）。
//
// 产品目标 P3 的硬要求：**面板操作与 CLI 逐字节一致**。
//
// 做法上只有一种方式能满足它：**重执行 CLI 本身**，把它的 stdout/stderr 原样
// 交给前端。面板不拼命令、不改写输出、不解释结论 —— 它只是把命令行原样搬到
// 网页上。这样"面板跑出来的门"和"人敲出来的门"是同一份字节，不可能漂移。
//
// 安全边界：
//   • 面板只监听 127.0.0.1（见 listenLoopback），这层本来就不对外
//   • 命令**白名单**，键到参数由服务端固定映射：前端传的是 `gate` 这样的键，
//     **不接受**任意命令行字符串，因此不存在注入面
//   • 只接受 POST：GET 会被页面里的链接/预取顺带触发，写操作不能那样发生

import (
	"context"
	"fmt"
	"os/exec"
	"time"
)

// panelRunRequest 是 /api/run 的请求体。
type panelRunRequest struct {
	// Cmd 是**白名单键**，不是命令行。服务端查表得到实际参数。
	Cmd     string `json:"cmd"`
	Project string `json:"project"`
}

// panelRunResult 是 /api/run 的返回体。
//
// 每个字段都是命令的**原样输出**。面板不做判定，`exitCode` 也只是"命令怎么结束的"，
// 不代表"这块板行不行" —— 后者由 card/gate 自己的 JSON 说。
type panelRunResult struct {
	Cmd      string   `json:"cmd"`
	Args     []string `json:"args"` // 便于人核对"面板到底跑了什么"
	ExitCode int      `json:"exitCode"`
	Stdout   string   `json:"stdout"`
	Stderr   string   `json:"stderr"`
	Duration string   `json:"duration"`
	// Cancelled 让前端区分"跑完了"和"被停了"。被停的那半截输出**不能**
	// 冒充一次完整结论 —— 所以这个字段必须单独存在，而不是靠退出码去猜。
	Cancelled bool   `json:"cancelled,omitempty"`
	Error     string `json:"error,omitempty"`
}

// panelRunCommands 是允许面板触发的操作白名单。
//
// 只收"能推进这块板"的几条。故意**不含**任何删除/清空类命令：
// 面板是给人看进度的，不该成为一把能毁掉画布的按钮。
var panelRunCommands = map[string][]string{
	"gate":          {"sch", "gate"},
	"phase-advance": {"phase", "advance"},
	"phase-run-s5":  {"phase", "run", "S5"},
	"card":          {"card"},
}

// panelRunArgs 把白名单键翻成完整参数。
func panelRunArgs(key, project string) ([]string, bool) {
	base, ok := panelRunCommands[key]
	if !ok {
		return nil, false
	}
	args := append([]string(nil), base...)
	// 只有需要工程上下文的命令才加 --project；`card` 读的是离线报告，不认这个参数。
	if project != "" && key != "card" {
		args = append(args, "--project", project)
	}
	return args, true
}

// runPanelCommand 重执行 CLI 并返回原样输出。纯函数化的入口便于单测。
func runPanelCommand(self, key, project string, timeout time.Duration) panelRunResult {
	args, ok := panelRunArgs(key, project)
	if !ok {
		return panelRunResult{Cmd: key, Error: fmt.Sprintf("unknown command %q (allowed: gate, phase-advance, phase-run-s5, card)", key)}
	}
	res := panelRunResult{Cmd: key, Args: args}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// 同一时刻只跑一个：两个 gate 并行只会互相抢连接器，而且按钮看起来"没反应"。
	slot, busy := panelAcquireRun(key, args, cancel)
	if slot == nil {
		res.Error = fmt.Sprintf("已经有操作在跑（%s）—— 先等它结束，或点「停止」", busy.Cmd)
		res.Stderr = res.Error
		return res
	}
	defer panelFinishRun(slot)

	start := time.Now()
	cmd := exec.CommandContext(ctx, self, args...)
	var out, errb stringsBuilder
	cmd.Stdout = &out
	cmd.Stderr = &errb
	err := cmd.Run()
	res.Duration = time.Since(start).Round(time.Millisecond).String()
	res.Stdout = out.String()
	res.Stderr = errb.String()
	if cmd.ProcessState != nil {
		res.ExitCode = cmd.ProcessState.ExitCode()
	}
	if ctx.Err() == context.Canceled {
		res.Cancelled = true
	}
	if cmd.ProcessState != nil && cmd.ProcessState.ExitCode() < 0 {
		// 被信号杀掉（包括我们 cancel 的）
		res.Cancelled = true
	}
	// **非零退出不是"面板出错"**：card exit 2 = 还没检查过，gate exit 1 = 门没过，
	// 都是**正常结论**。所以这里只在命令真的没跑起来时填 Error。
	if err != nil && cmd.ProcessState == nil {
		res.Error = err.Error()
	}
	if res.Cancelled {
		res.Error = "已被停止 —— 下面的输出不完整，不能当结论"
	}
	return res
}

// stringsBuilder 是个最小的 strings.Builder 别名，避免在这个文件里再多一个 import。
type stringsBuilder struct {
	b []byte
}

func (s *stringsBuilder) Write(p []byte) (int, error) {
	s.b = append(s.b, p...)
	return len(p), nil
}

func (s *stringsBuilder) String() string { return string(s.b) }
