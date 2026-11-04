package app

// emitFilteredLibResults 把搜索结果过滤后输出，并在全被筛掉时说清楚。

import (
	"encoding/json"
	"fmt"
	"io"
)

// emitFilteredLibResults 输出筛选后的搜索结果。
//
// 关键行为：**一条都不剩时，明确说"没有匹配"**，而不是输出一个空列表让人
// 以为是"库里没有"——两者对用户的下一步是不一样的：
//
//	· 空列表 → 换关键词
//	· 全被筛掉 → 关键词里可能有个词库里根本不这么叫，换说法或放宽
func emitFilteredLibResults(res *actionResult, query string, want int,
	stdout, stderr io.Writer) error {

	raw, err := json.Marshal(res.Result)
	if err != nil {
		return fmt.Errorf("搜索结果无法序列化：%w", err)
	}
	var doc struct {
		Components []map[string]any `json:"components"`
		Count      int              `json:"count"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		// 结构不是预期时原样吐出，不吞掉信息
		_, werr := stdout.Write(raw)
		return werr
	}

	kept, dropped := filterLibResults(query, doc.Components)
	total := len(kept)
	// 连接器是按相关度排的，筛完只给用户他要的条数。
	if want > 0 && len(kept) > want {
		kept = kept[:want]
	}

	out := map[string]any{
		"components": kept,
		"count":      len(kept),
		"matched":    total,
		"query":      query,
	}
	if dropped > 0 {
		out["filteredOut"] = dropped
		out["note"] = fmt.Sprintf(
			"丢弃了 %d 条与查询无关的结果（模糊匹配会把不相关的器件排进前几名）。"+
				"想要原始排序结果加 --allow-fuzzy。", dropped)
	}
	if len(kept) == 0 && dropped > 0 {
		out["note"] = fmt.Sprintf(
			"没有器件真的匹配 %q（%d 条模糊结果全部与查询无关，已丢弃）。"+
				"换一个更接近库里叫法的关键词，或加 --allow-fuzzy 看原始结果。",
			query, dropped)
		fmt.Fprintf(stderr, "lib search: 没有匹配 %q 的器件（已丢弃 %d 条无关结果）\n",
			query, dropped)
	}

	enc := json.NewEncoder(stdout)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}
