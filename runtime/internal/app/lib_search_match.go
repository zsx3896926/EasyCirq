package app

// lib_search_match.go — 卡点 #6（板1 实测）：
//
// `lib search` 在**没有任何真正匹配**时会返回一堆不相关的器件：
//
//	query "TVS SMBJ"    → PCA9554DGVR（8 位 I2C 扩展器，16 脚）
//	query "AMS1117 3.3" → DO3314-333MLC / AGM613AP（都不是 LDO）
//
// 这比"查不到"危险得多：查不到会让人换关键词；**查到错的会一路错到打样**。
// 板1 已经这样放了 3 个器件（一个 TVS 变成了 I2C 扩展器，一个 LDO 变成了
// 150V MOSFET），直到编网络表时按引脚数才对出来。
//
// 所以默认加一道闸：**查询词一个都没在器件里出现，就不返回它**。
// 全被筛掉时明确说"没有匹配"，而不是给一句噪声让人误以为找到了。
// `--allow-fuzzy` 保留原来的排序结果（需要模糊探索时用它）。

import (
	"strings"
	"unicode"
)

// libSearchTokens 把查询拆成有意义的词。
//
// 丢掉纯符号与单字符（"3.3" 要保留，"V" 这种单字母留着只会制造误命中）。
func libSearchTokens(query string) []string {
	// **只按空白拆分**，然后剥掉每个词首尾的标点。
	//
	// 不能按标点拆分：`3.3` / `5.0` / `SMBJ5.0A` 里的点是有意义的关键词，
	// 按标点拆会把它们变成单字符 "3" 和 "3"，然后被当成无意义词丢掉 ——
	// 而"AMS1117 3.3"正是最常见的选型写法。
	var out []string
	for _, f := range strings.Fields(query) {
		f = strings.ToLower(f)
		f = strings.TrimFunc(f, func(r rune) bool {
			return unicode.IsPunct(r) || unicode.IsSpace(r)
		})
		if len([]rune(f)) < 2 {
			continue
		}
		out = append(out, f)
	}
	return out
}

// libDeviceMatches 判断一个候选器件是否**真的**和查询有关。
//
// 命中规则：**任意一个**查询词出现在器件的任一可读字段里就算相关。
// 用"任意"而不是"全部"是因为查询常带包装/封装词（"100nF 0402"），
// 而器件的 description 未必逐字包含 "0402"。
//
// 返回 false 的候选会被默认丢弃 —— 见文件头为什么。
func libDeviceMatches(query string, comp map[string]any) bool {
	tokens := libSearchTokens(query)
	if len(tokens) == 0 {
		return true // 查询里没有可判定的词，不做筛选
	}
	var hay strings.Builder
	for _, k := range []string{"name", "value", "description", "manufacturerId",
		"manufacturer", "lcsc", "footprintName", "symbolName"} {
		if v, ok := comp[k]; ok {
			if s, ok := v.(string); ok {
				hay.WriteString(strings.ToLower(s))
				hay.WriteByte(' ')
			}
		}
	}
	blob := hay.String()
	for _, t := range tokens {
		if containsTokenBoundary(blob, t) {
			return true
		}
	}
	return false
}

// containsTokenBoundary 判断 token 是否算命中。
//
// 规则按词长分两档，因为两种误判的代价不一样：
//
//   - **短词（≤3 字符）要求词边界**。三个字母太容易撞上：封装名 "TVSOP-48"
//     里就含 "tvs"，裸 Contains 会让每次 "TVS" 查询都命中 TVSOP 封装的任意
//     器件 —— 板1 就是这样把一颗 16 位锁存器当成了 TVS。
//
//   - **长词（≥4 字符）直接包含**。按型号前缀查器件是最常见的用法
//     （"STM32F030" 要能命中 "STM32F030C8T6"），此时要求词边界反而会把
//     真正想要的器件筛掉 —— 这个坑我在同一次改动里踩了两遍。
//
// 中文按字节处理：UTF-8 多字节首字节 >= 0x80，不算字母数字，天然是边界。
func containsTokenBoundary(hay, tok string) bool {
	if tok == "" {
		return false
	}
	if len([]rune(tok)) >= 4 {
		return strings.Contains(hay, tok)
	}
	idx := 0
	for {
		j := strings.Index(hay[idx:], tok)
		if j < 0 {
			return false
		}
		start := idx + j
		end := start + len(tok)
		beforeOK := start == 0 || !isWordByte(hay[start-1])
		afterOK := end >= len(hay) || !isWordByte(hay[end])
		if beforeOK && afterOK {
			return true
		}
		idx = start + 1
		if idx >= len(hay) {
			return false
		}
	}
}

func isWordByte(b byte) bool {
	return b >= 'a' && b <= 'z' || b >= '0' && b <= '9'
}

// filterLibResults 返回保留的候选与被丢弃的数量。
func filterLibResults(query string, comps []map[string]any) (kept []map[string]any, dropped int) {
	for _, c := range comps {
		if libDeviceMatches(query, c) {
			kept = append(kept, c)
		} else {
			dropped++
		}
	}
	return kept, dropped
}
