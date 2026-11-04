package app

// cmd_run.go — harness 的循环。
//
// 相位与证据的判定在 scripts/phase.py；这里只是入口。
// 循环本身在 scripts/run.py：它按相位放行动作，越界直接拒；
// 门没过就推进不了；NOT RUN / blocked 都不算通过。
//
// 为什么循环在 Python 而不是 Go：它要复用 phase.py 的判定
// （同一套状态机），在 Go 里重写一遍就意味着两份可能不一致的规则。

import (
	"io"

	"github.com/spf13/cobra"
)

func newRunCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "run",
		Short: "跑 harness 循环：按相位调门、拒绝跳步、NOT RUN 当阻塞",
		Long: "harness 的循环。它把「按顺序调门、拒绝跳步、NOT RUN 阻塞」三条自动执行。\n\n" +
			"  easycirq run --goal \"给板子加个 LDO\" --project <uuid> \\\n" +
			"      --endpoint https://api.deepseek.com/v1 --model deepseek-chat\n\n" +
			"没有 API key 时可以用剧本验证编排（不需要任何外部服务）：\n" +
			"  easycirq run --goal x --project y --fake script.json\n\n" +
			"**动作白名单在循环这一层**：模型只能调当前相位允许的动作，越界直接拒绝。\n" +
			"（daemon 级强制留到有真实任务数据之后再谈——分错会卡住正常工作流。）",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			return runEnterpriseScript(enterpriseScript{
				name: "run.py",
			}, args, stdout, stderr)
		},
	}
}
