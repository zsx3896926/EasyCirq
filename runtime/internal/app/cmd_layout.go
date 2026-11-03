package app

// cmd_layout.go — 把 hds-verifier 的离线布局/布线工具链接进 easycirq。
//
// # 为什么它在这里
//
// 那套工具链（50 个 Python 脚本、11,826 行）是一批**已验证**的能力：
// 离线布一块板、给出 11 项 KPI、在门禁红时拒绝上机、能出制造文件并回读。
// 它原本在另一个仓库里，靠手敲 `python tools/layout/xxx.py` 使用。
//
// 接进来的意义是：**能力不丢、用法统一、纪律可继承**。
// 脚本整体搬到 `easycirq/scripts/layout/`，这里只做薄封装。
//
// # 它不做什么
//
//   · 不改算法，不动参数 —— 那套东西被 R1–R8 纪律约束着，冻结了
//   · 不替人判断板子能不能交付 —— 它的结论是"物理上做不到，要换连接器"
//
// # 已知边界（照抄 WRAP-UP，不美化）
//
//   · 只能让 self-test 板变绿；RetroCam-02 做不到（J3 19.7 mil vs U5 50 mil）
//   · Gerber 语法有效且回读通过，但**没有过 CAM 验证**
//   · 阻抗/电流/热都是基于**标注假设**的算术
//   · 从未写入真实板；门禁红时 emit_apply 拒绝且不留痕迹

import (
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/spf13/cobra"
)

// layoutScript 是一个可调用的工具链脚本。
type layoutScript struct {
	name string
	file string
	help string
}

var layoutScripts = []layoutScript{
	{"verify", "verify.py", "健康检查：14 项，全 PASS 才算这套工具链是好的"},
	{"feasibility", "feasibility.py", "先算边界：等长下界、走廊冲突、板子自身问题（R1）"},
	{"pipeline", "pipeline.py", "全链路：改板 → 修复 → 配方案 → 布线 → lint → 验收"},
	{"gaps_check", "gaps_check.py", "一条命令看缺口：验收矩阵 + 板级发现 + 待决项"},
	{"bench", "bench.py", "基准：时间与 KPI 指纹（--compare 与基线比，指纹必须一致）"},
	{"sweep", "sweep.py", "并行 + 缓存 + 校准的批量评估（--calibrate 才允许用来排序）"},
	{"regress", "regress.py", "回归：重测候选并与记录值逐项比对，撤回项拒跑"},
	{"whatif", "whatif.py", "假设分析：改一个参数看 KPI 怎么动"},
	{"dfm", "dfm.py", "可制造性：铜到板边 / 阻焊桥 / 线宽"},
	{"footprints", "footprints.py", "封装核验：焊盘数、行内/列内节距、最大焊盘、最小铜隙"},
	{"fabrication", "fabrication.py", "制造清单：板尺寸/层数/焊盘与网络普查/未导出项"},
	{"impedance", "impedance.py", "阻抗：反推线宽、核对实际 plan、s/h 间距比"},
	{"current", "current.py", "载流：IPC-2221 线宽/温升核算"},
	{"thermal", "thermal.py", "热：一阶结温 + 铜效应 + 审查清单"},
	{"gerber", "gerber.py", "Gerber/钻孔输出（语法有效并回读验证，未过 CAM）"},
	{"acceptance", "acceptance.py", "验收矩阵：门禁 + KPI + 契约"},
	{"selftest", "selftest.py", "self-test 板：证明整条链路**能**变绿"},
}

// layoutDir 找工具链目录。走和 enterprise 脚本同一套 skillAsset 机制，
// 免得出现第二种"脚本在哪"的答案。
//
// **注意**：skillAsset 只解析**文件**（它用 os.Stat + !IsDir 判定），
// 所以这里解析标志性文件 verify.py，再取它的父目录。
func layoutDir() (string, error) {
	asset := skillAsset{
		name: "verify.py",
		rels: []string{
			"easycirq/scripts/layout/verify.py",
			"easycirq-agent/scripts/layout/verify.py",
		},
		searchPath: false,
		flagHint:   "EASYCIRQ_SKILLS_DIR",
	}
	file, err := asset.resolve("")
	if err != nil {
		return "", err
	}
	return filepath.Dir(file), nil
}

// runLayoutScript 用当前解释器跑一个 layout 脚本，工作目录设在工具链目录
// （脚本之间用平级 import，且相对查找 fixtures/ 与 .bench/）。
func runLayoutScript(sc layoutScript, args []string, stdout, stderr io.Writer) error {
	dir, err := layoutDir()
	if err != nil {
		return err
	}
	path := dir + string(os.PathSeparator) + sc.file
	if _, statErr := os.Stat(path); statErr != nil {
		return fmt.Errorf("找不到 %s：%w\n工具链应在 %s", sc.file, statErr, dir)
	}
	py, err := pythonCommand(path, args...)
	if err != nil {
		return err
	}
	// 工具链的脚本互相平级 import，并相对自己找 fixtures/，
	// 所以工作目录必须是工具链目录。
	py.Dir = dir
	py.Stdin = os.Stdin
	py.Stdout = stdout
	py.Stderr = stderr
	if err := py.Run(); err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			return errActionFailed
		}
		return fmt.Errorf("%s: %w", sc.file, err)
	}
	return nil
}

func newLayoutCmd(stdout, stderr io.Writer) *cobra.Command {
	c := &cobra.Command{
		Use:   "layout",
		Short: "离线布局/布线：算边界、布线、出 KPI、出制造文件",
		Long: "把一块**捕获下来的**板子离线布通并给出量化结论。\n\n" +
			"它吃的是 dump + 放置文件，不碰在线编辑器；门禁红时拒绝上机。\n\n" +
			"工作顺序（纪律 R1–R8 的第一条）：\n" +
			"  1. easycirq layout feasibility   先算边界，超目标就别搜\n" +
			"  2. easycirq layout pipeline      够了再跑全链路\n" +
			"  3. easycirq layout gaps_check    看缺口与待决项\n" +
			"  4. easycirq layout verify        改了工具链就跑这个\n\n" +
			"板子数据位置：默认用随包夹具，可用 EASYCIRQ_LAYOUT_BOARD 指向别处。\n\n" +
			"**这套东西不能替你做那个决定**：RetroCam-02 的 J3 是 19.7 mil 节距、\n" +
			"U5 是 50 mil 焊盘，8 针跨度差 212 mil ⇒ 等长下界 53–67 mil ⇒ 不换连接器\n" +
			"做不到 <50 mil。工具能证明这一点，不能改变它。",
	}
	for _, sc := range layoutScripts {
		sc := sc
		sub := &cobra.Command{
			Use:                sc.name,
			Short:              sc.help,
			DisableFlagParsing: true,
			RunE: func(_ *cobra.Command, args []string) error {
				return runLayoutScript(sc, args, stdout, stderr)
			},
		}
		c.AddCommand(sub)
	}
	return c
}
