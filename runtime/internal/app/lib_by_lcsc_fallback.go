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
