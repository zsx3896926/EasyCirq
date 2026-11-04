package app

// cmd_sch_gc.go — 清理"移动器件后留下的孤立标号/导线"（卡点 #31）。
//
// 场景（板1b 实测）：`sch modify --x …` 只改器件坐标，挂在它引脚上的桩线和标号
// 留在原地，变成孤立图元。它们仍然算在**那个器件的组**里，于是 `sch clusters`
// 报"该器件与邻居重叠"——而那个器件早已挪到别处。
//
// 判定不重写：`schematic.bridgeCheck` 已经把这种情况分成两类，注释里写得很明白
// （见 bridgeRuleType）：
//   ORPHAN_FLAG  flag 挂在**没有任何导线**的点上
//   ORPHAN_TREE  一整棵树**碰不到任何引脚** —— 正是"器件移动后留下的残留"
//
// 所以 gc 只做两件事：把这两类树的 wireIds/flagIds 收集起来，确认后删掉。
// 默认 dry-run：先列出来，让人看清要删什么，再加 --apply 才动手。

import (
	"encoding/json"
	"fmt"
	"io"
	"sort"
	"strings"
)

type gcCandidate struct {
	Kind    string   `json:"kind"`
	Level   string   `json:"level"`
	WireIDs []string `json:"wireIds,omitempty"`
	FlagIDs []string `json:"flagIds,omitempty"`
	Nets    []string `json:"nets,omitempty"`
}

type gcReport struct {
	DryRun     bool          `json:"dryRun"`
	Applied    bool          `json:"applied"`
	Candidates []gcCandidate `json:"candidates"`
	Kept       int           `json:"kept"`    // 保留的树（碰到引脚，不是残留）
	Bridges    int           `json:"bridges"` // 真短路：gc 不碰
	Deleted    gcDeleted     `json:"deleted"`
	Note       string        `json:"note,omitempty"`
}

type gcDeleted struct {
	Wires int `json:"wires"`
	Flags int `json:"flags"`
}

// gcCandidateKinds 是 gc **允许**清理的树类型。
//
// BRIDGE（真短路）和 ORPHAN（悬空桩但碰到了引脚）都不在其中：前者是电路错，
// config 改了才该动；后者可能是有意留的 stub。只清"整棵树碰不到任何引脚"的残留。
var gcCandidateKinds = map[string]bool{
	"ORPHAN_FLAG": true,
	"ORPHAN_TREE": true,
}

func runSchGC(cfg *appConfig, window string, apply bool, asJSON bool,
	stdout, stderr io.Writer) error {

	res, err := requestAction(cfg, "schematic.bridgeCheck", window, map[string]any{})
	if err != nil {
		return err
	}
	rep, perr := parseBridgeReport(res.Result)
	if perr != nil {
		return perr
	}

	out := gcReport{DryRun: !apply, Applied: apply, Candidates: []gcCandidate{}}
	var wireIDs, flagIDs []string

	for _, t := range rep.Trees {
		kind := strings.ToUpper(t.Kind)
		if !gcCandidateKinds[kind] {
			out.Kept++
			continue
		}
		c := gcCandidate{Kind: t.Type, Level: t.Level, WireIDs: t.WireIds, FlagIDs: t.FlagIds}
		if c.Kind == "" {
			c.Kind = kind
		}
		for _, n := range t.Nets {
			if n != "" {
				c.Nets = append(c.Nets, n)
			}
		}
		out.Candidates = append(out.Candidates, c)
		wireIDs = append(wireIDs, t.WireIds...)
		flagIDs = append(flagIDs, t.FlagIds...)
	}
	out.Bridges = rep.Summary.Bridges

	if !apply {
		out.Note = "dry-run：上面这些是「器件移动后留下的残留」。确认无误后加 --apply 删除。"
	} else if len(wireIDs) == 0 && len(flagIDs) == 0 {
		out.Note = "没有可清理的残留。"
	} else {
		// 先删导线，再删标号：反过来的话，删标号那一刻树就变了，
		// bridge-check 给的 wireIds 可能已经失效。
		if len(wireIDs) > 0 {
			if err := gcDelete(cfg, window, wireIDs); err != nil {
				out.Note = "删导线失败：" + err.Error() + " —— 画布可能只清了一部分，重跑 dry-run 看现状。"
				return gcEmit(out, res, asJSON, stdout)
			}
			out.Deleted.Wires = len(wireIDs)
		}
		if len(flagIDs) > 0 {
			if err := gcDelete(cfg, window, flagIDs); err != nil {
				out.Note = "删标号失败：" + err.Error() + " —— 画布可能只清了一部分，重跑 dry-run 看现状。"
				return gcEmit(out, res, asJSON, stdout)
			}
			out.Deleted.Flags = len(flagIDs)
		}
		out.Note = "已清理。建议再跑一次 `sch clusters` 与 `sch gate` 确认。"
	}
	return gcEmit(out, res, asJSON, stdout)
}

func gcDelete(cfg *appConfig, window string, ids []string) error {
	// 去重，保持稳定顺序（便于把删了什么写进日志/复盘）
	sort.Strings(ids)
	uniq := ids[:0]
	for i, id := range ids {
		if i == 0 || id != ids[i-1] {
			uniq = append(uniq, id)
		}
	}
	_, err := requestAction(cfg, "schematic.primitives.delete", window,
		map[string]any{"primitiveIds": uniq})
	return err
}

func gcEmit(out gcReport, res *actionResult, asJSON bool, stdout io.Writer) error {
	if asJSON {
		return encodeResultEnvelope(res, out, stdout)
	}
	fmt.Fprintf(stdout, "sch gc: %d 处可清理的残留（%s）\n",
		len(out.Candidates), map[bool]string{true: "dry-run", false: "已应用"}[!out.Applied])
	for _, c := range out.Candidates {
		nets := ""
		if len(c.Nets) > 0 {
			nets = " net=" + strings.Join(c.Nets, ",")
		}
		fmt.Fprintf(stdout, "  %-12s 线 %d 条 / 标号 %d 个%s\n",
			c.Kind, len(c.WireIDs), len(c.FlagIDs), nets)
	}
	if out.Note != "" {
		fmt.Fprintf(stdout, "  %s\n", out.Note)
	}
	if out.Applied {
		fmt.Fprintf(stdout, "  已删：导线 %d 条 / 标号 %d 个\n",
			out.Deleted.Wires, out.Deleted.Flags)
	}
	// gc 不是门：清完也不代表板子能下单，所以不返回错误码。
	// 真正的判定留给 sch gate / card。
	_ = json.Marshal
	return nil
}
