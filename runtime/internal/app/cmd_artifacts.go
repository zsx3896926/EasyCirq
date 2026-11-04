package app

// cmd_artifacts.go — 列出这块板产出过的**证据文件**（P4「历史与产物」）。
//
// 目的很具体：交付保证的最后一环是"证据在哪"。用户跑完门、出完卡之后，
// 需要知道该把哪几个文件交出去、它们是什么时候生成的、有多大。
//
// 面板不判断任何事，所以这份清单由 CLI 产出、面板原样渲染。
//
// 扫描范围刻意收窄到**已知位置 + 已知文件名**，不去递归整个工程目录：
// 一个"把你机器上的 json 都列出来"的命令既慢又危险（会列出不该交出去的东西）。

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// artifactEntry 是一条产物记录。
type artifactEntry struct {
	Kind     string `json:"kind"`
	Path     string `json:"path"`
	Bytes    int64  `json:"bytes"`
	Modified string `json:"modified"`
	Note     string `json:"note,omitempty"`
}

// artifactReport 是 `artifacts --json` 的返回体。
type artifactReport struct {
	Roots     []string        `json:"roots"`
	Artifacts []artifactEntry `json:"artifacts"`
	// Total 是**扫到的总数**，可能大于 len(Artifacts)（被 --limit 截断）。
	// 交付保证的清单不能"看起来就是全部"而其实是前 20 条。
	Total int    `json:"total"`
	Note  string `json:"note,omitempty"`
}

// artifactKinds 把文件名映射到"它是什么"。只认这几类 —— 它们是交付时要用的。
var artifactKinds = map[string]string{
	"kpi-report.json":            "离线检查结论（交付卡读它）",
	"kpi-history.jsonl":          "历次检查的 KPI 轨迹",
	"kpi-report.md":              "同一份结论的可读版",
	"design-validity-check.json": "设计有效性检查",
	"connectivity-check.json":    "连通性检查",
	"erc-check.json":             "ERC 检查",
	"power-net-check.json":       "电源网检查",
	"readability-check.json":     "可读性检查",
	"drc.json":                   "DRC 原始结果",
}

// collectArtifacts 扫描给定根目录下的已知产物。
//
// 只走两级（root/ 与 root/*/），不递归整个仓库：产物都在 reports/<批次>/ 下，
// 更深的递归只会把测试夹具也列进来。
func collectArtifacts(roots []string) artifactReport {
	rep := artifactReport{Roots: roots, Artifacts: []artifactEntry{}}
	seen := map[string]bool{}
	for _, root := range roots {
		if st, err := os.Stat(root); err != nil || !st.IsDir() {
			continue
		}
		// 第一层：root 本身
		scanDir(root, seen, &rep)
		// 第二层：root/*/
		entries, err := os.ReadDir(root)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() {
				scanDir(filepath.Join(root, e.Name()), seen, &rep)
			}
		}
	}
	sort.Slice(rep.Artifacts, func(i, j int) bool {
		return rep.Artifacts[i].Modified > rep.Artifacts[j].Modified
	})
	if len(rep.Artifacts) == 0 {
		rep.Note = "这个工程还没有产出任何证据文件 —— 先跑一次 `easycirq sch kpi` 或离线全检。"
	}
	return rep
}

func scanDir(dir string, seen map[string]bool, rep *artifactReport) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		kind, ok := artifactKinds[e.Name()]
		if !ok {
			continue
		}
		path := filepath.Join(dir, e.Name())
		if seen[path] {
			continue
		}
		seen[path] = true
		info, err := e.Info()
		if err != nil {
			continue
		}
		rep.Artifacts = append(rep.Artifacts, artifactEntry{
			Kind:     kind,
			Path:     filepath.ToSlash(path),
			Bytes:    info.Size(),
			Modified: info.ModTime().Format(time.RFC3339),
		})
	}
}

func newArtifactsCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var (
		roots  []string
		asJSON bool
		limit  int
	)
	c := &cobra.Command{
		Use:   "artifacts",
		Short: "List the evidence files this board has produced (delivery card, KPI report, checks)",
		Long: `列出这块板产出过的**证据文件**：交付卡读的 kpi-report.json、历次检查的 KPI 轨迹、
各项离线检查结果。

只扫已知位置里的已知文件名（默认 reports 与 .easycirq），**不递归整个工程** ——
一个"把你机器上的 json 全列出来"的命令既慢又会列出不该交出去的东西。`,
		Example: `  easycirq artifacts
  easycirq artifacts --json
  easycirq artifacts --root reports/hard-board`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(roots) == 0 {
				roots = []string{"reports", ".easycirq"}
			}
			rep := collectArtifacts(roots)
			rep.Total = len(rep.Artifacts)
			if limit > 0 && len(rep.Artifacts) > limit {
				rep.Artifacts = rep.Artifacts[:limit]
				rep.Note = fmt.Sprintf("只显示最近 %d 个（共 %d 个）；用 --limit 0 看全部，或 --root <目录> 缩小范围",
					limit, rep.Total)
			}
			if asJSON {
				enc := json.NewEncoder(stdout)
				enc.SetIndent("", "  ")
				enc.SetEscapeHTML(false)
				return enc.Encode(rep)
			}
			if len(rep.Artifacts) == 0 {
				fmt.Fprintln(stdout, rep.Note)
				return nil
			}
			fmt.Fprintf(stdout, "产物 %d 个（按修改时间从新到旧）\n", rep.Total)
			for _, a := range rep.Artifacts {
				fmt.Fprintf(stdout, "  %-28s %8d B  %s  %s\n",
					a.Kind, a.Bytes, strings.TrimSuffix(a.Modified, "Z"), a.Path)
			}
			if rep.Note != "" {
				fmt.Fprintf(stdout, "  %s\n", rep.Note)
			}
			return nil
		},
	}
	c.Flags().IntVar(&limit, "limit", 20, "最多显示多少条（0 = 全部）")
	c.Flags().StringArrayVar(&roots, "root", nil, "扫描根目录（可重复；默认 reports 与 .easycirq）")
	c.Flags().BoolVar(&asJSON, "json", false, "以 JSON 输出")
	return c
}
