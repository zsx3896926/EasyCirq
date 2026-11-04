package app

// cmd_phase.go — 相位与证据：把方法论做成代码，而不是提示词。
//
// 为什么需要它：`sch status` 能**检测** S1–S6 到哪一步了，但它不**阻止**你从
// S1 直接跑 `sch place`。检测不是强制。这一层补的是强制那一半。
//
// 语义（与 `sch gate` 的三态判词对齐）：
//   · 只有 pass 放行
//   · 有门但没跑 = NOT RUN = 阻塞
//   · 还没接门的相位不阻塞（否则只接一个门时整条流程一步推不动）
//   · 板子变了，旧证据自动作废
//
// 实现在 scripts/phase.py：这一层是纯数据 + 纯判定，不碰 daemon、不碰 EDA，
// 所以能脱离 EDA 单测（见 tests/test_phase_gate.py）。

import (
	"io"

	"github.com/spf13/cobra"
)

func newPhaseCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	run := func(args []string) error {
		return runEnterpriseScript(enterpriseScript{
			name: "phase.py",
		}, args, stdout, stderr)
	}
	c := &cobra.Command{
		Use:   "phase",
		Short: "相位与证据：没有证据就不许往下走（方法论做成代码）",
		Long: "相位与证据链。**只有 pass 放行**：\n\n" +
			"  · 有门但没跑 = NOT RUN = 阻塞\n" +
			"  · 还没接门的相位不阻塞（但会显式标出来）\n" +
			"  · 板子变了，旧证据自动作废（换机器不能假装跑过）\n\n" +
			"  easycirq phase show     --project <uuid>          当前相位 + 各相位证据状态\n" +
			"  easycirq phase run S5   --project <uuid>          跑该相位的门并记证据\n" +
			"  easycirq phase advance  --project <uuid>          推进（前置不是 pass 就拒）\n" +
			"  easycirq phase set S6   --project <uuid>          强制设置（记为 override）\n\n" +
			"当前只接了 S5（原理图校验门）。其余相位显式标「未接门」——\n" +
			"那不代表通过，只代表还没有强制。",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			if len(args) == 0 {
				args = []string{"show"}
			}
			return run(args)
		},
	}
	return c
}
