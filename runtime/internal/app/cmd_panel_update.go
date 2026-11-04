package app

// cmd_panel_update.go — 面板上的"检查更新"（P5 自更新面板）。
//
// 两个约束决定它的形状：
//
//  1. **A15 默认抓包零外连** —— 面板加载时**不许**联网。所以检查更新只能是
//     用户点一下的显式动作，绝不能放进 /api/snapshot 的自动轮询里。
//  2. 面板**不做判定** —— 它只把 `easycirq update --check --json` 的原样结果
//     显示出来。"该不该升级"由那份 JSON 说，不由面板说。
//
// 另外：**面板不执行安装**。安装要替换正在运行的二进制、可能要 sudo、
// 还会重启 daemon —— 那是一个需要在终端里看着输出的动作，不该变成一个
// 一按就好的网页按钮。

import (
	"os/exec"
)

// panelUpdateCheckKey 是白名单键。它**故意**不在 /api/run 的通用白名单里，
// 而是单独一条路径，因为它有网络副作用，必须显式、可解释。
const panelUpdateCheckKey = "update-check"

// panelUpdateArgs 是 `update --check --json` 的参数。
func panelUpdateArgs() []string {
	return []string{"update", "--check", "--json"}
}

// runPanelUpdateCheck 只做检查，不安装。复用 runPanelCommand 的执行器，
// 但**不占用操作槽位** —— 它几秒就回来，而且不该和正在跑的门抢位置。
func runPanelUpdateCheck(self string) panelRunResult {
	args := panelUpdateArgs()
	res := panelRunResult{Cmd: panelUpdateCheckKey, Args: args}
	cmd := exec.Command(self, args...)
	var out, errb stringsBuilder
	cmd.Stdout = &out
	cmd.Stderr = &errb
	err := cmd.Run()
	res.Stdout = out.String()
	res.Stderr = errb.String()
	if cmd.ProcessState != nil {
		res.ExitCode = cmd.ProcessState.ExitCode()
	}
	if err != nil && cmd.ProcessState == nil {
		res.Error = err.Error()
	}
	// 检查失败（多半是没有网络/没有发布）不是面板出错，是**这条信息拿不到**。
	// 说清楚，别让用户以为整个面板坏了。
	if res.ExitCode != 0 && res.Error == "" {
		res.Error = "检查更新没拿到结果（多半是这台机器现在上不了 GitHub）—— 这不影响交付判定"
	}
	return res
}
