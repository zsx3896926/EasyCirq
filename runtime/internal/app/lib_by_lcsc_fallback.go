package app

// lib_by_lcsc_fallback.go — 卡点（板1 实测）：批量 `by-lcsc` 静默少返回。
//
// EasyEDA 4.1.78 的 `lib_Device.getByLcscIds` 在数组入参上会把结果**折叠成最后
// 一个元素**：传 5 个不同的 C 号，回 5 份最后一个器件。原样透传的后果很重——
// 「按 C 号恢复整板」时只认出一个料，其余全部落空（板1 因此只剩 6 个器件）。
//
// 连接器侧已加覆盖度补查，但**已装好的连接器不会自动更新**（要手工重新导入）。
// 所以 CLI 这一层也做一遍：不信任批量的覆盖度，缺的逐个补查。
// 两层都做，是因为用户不可能总是立刻升级连接器。

import (
	"encoding/json"
	"fmt"
	"io"
	"time"
)

type byLcscResult struct {
	Components []map[string]any `json:"components"`
	NotFound   []string         `json:"notFound,omitempty"`
	Requested  []string         `json:"requested,omitempty"`
	Count      int              `json:"count"`
}

// resolveByLcscWithFallback 先批量解析，再核对覆盖度，缺的单个补查。
func resolveByLcscWithFallback(cfg *appConfig, window string, ids []string,
	stdout, stderr io.Writer) error {

	batch, err := requestActionTimed(cfg, "schematic.library.get_by_lcsc", window,
		map[string]any{"lcscIds": ids}, 60*time.Second)
	if err != nil {
		return placeDispatchError(err)
	}

	out := byLcscResult{Requested: ids}
	if raw, mErr := json.Marshal(batch.Result); mErr == nil {
		_ = json.Unmarshal(raw, &out)
	}

	// 覆盖度：批量结果里到底出现了哪些请求号。
	covered := map[string]bool{}
	for _, c := range out.Components {
		if id, _ := c["lcsc"].(string); id != "" {
			covered[id] = true
		}
	}

	missing := make([]string, 0, len(ids))
	for _, id := range ids {
		if !covered[id] {
			missing = append(missing, id)
		}
	}

	// 只在"部分覆盖"时补查：
	//   · 全覆盖   → 批量 API 正常，不必补
	//   · 全不覆盖 → 这些号本来就在库里找不到，补查只会白等
	filled := 0
	if len(missing) > 0 && len(missing) < len(ids) {
		for _, id := range missing {
			one, err := requestActionTimed(cfg, "schematic.library.get_by_lcsc", window,
				map[string]any{"lcscIds": []string{id}}, 30*time.Second)
			if err != nil {
				continue
			}
			var single byLcscResult
			if raw, mErr := json.Marshal(one.Result); mErr == nil &&
				json.Unmarshal(raw, &single) == nil {
				for _, c := range single.Components {
					if got, _ := c["lcsc"].(string); got == id {
						out.Components = append(out.Components, c)
						covered[id] = true
						filled++
					}
				}
			}
		}
	}

	// 去重（补查会重复加同一个器件），并保持请求顺序的稳定性
	seen := map[string]bool{}
	deduped := out.Components[:0]
	for _, c := range out.Components {
		id, _ := c["lcsc"].(string)
		if id != "" && seen[id] {
			continue
		}
		if id != "" {
			seen[id] = true
		}
		deduped = append(deduped, c)
	}
	out.Components = deduped
	out.Count = len(out.Components)

	// ── 补齐 footprintName / symbolName（卡点 #17）────────────────────
	//
	// `by-lcsc` 返回的身份**缺封装**：实测同一个 C 号，`lib search` 给出
	// footprintName="C1206"，而 `by-lcsc` 给 None。原样拿去 place，建出来的
	// 器件**没有封装** —— 板子造不出来，而直到 DRC 才报 MISSFOOTPRINT，
	// 离成因很远（板1 一次重放出了 27 个这样的器件）。
	//
	// 所以这里补一步：缺封装的，用 `lib search` 按同一个 C 号查一次，
	// 把 footprintName / symbolName 填上。查不到就如实标记，不假装齐备。
	for _, c := range out.Components {
		if v, _ := c["footprintName"].(string); v != "" {
			continue
		}
		id, _ := c["lcsc"].(string)
		if id == "" {
			continue
		}
		one, err := requestActionTimed(cfg, "schematic.library.search", window,
			map[string]any{"query": id, "limit": 3}, 30*time.Second)
		if err != nil {
			continue
		}
		var sr struct {
			Components []map[string]any `json:"components"`
		}
		raw, mErr := json.Marshal(one.Result)
		if mErr != nil || json.Unmarshal(raw, &sr) != nil {
			continue
		}
		for _, cand := range sr.Components {
			if got, _ := cand["lcsc"].(string); got != id {
				continue
			}
			if fp, _ := cand["footprintName"].(string); fp != "" {
				c["footprintName"] = fp
			}
			if sym, _ := cand["symbolName"].(string); sym != "" {
				c["symbolName"] = sym
			}
			break
		}
		if _, ok := c["footprintName"].(string); !ok {
			c["footprintNameMissing"] = true
		}
	}

	notFound := make([]string, 0, len(ids))
	for _, id := range ids {
		if !seen[id] {
			notFound = append(notFound, id)
		}
	}
	out.NotFound = notFound

	if filled > 0 {
		fmt.Fprintf(stderr,
			"批量查询漏了 %d 个 C 号（EDA 的批量接口在部分版本上会折叠成最后一个），已逐个补查。\n",
			filled)
	}

	enc := json.NewEncoder(stdout)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}
