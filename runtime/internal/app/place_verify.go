package app

// place_verify.go — `sch place --verify` 的读回核实。
//
// 为什么需要它：连接器在负载下降级时，写入会返回 ok:false **但器件已经落上了**
// （daemon 的 warnings 里称之为「假失败定律」并提示"重发前先读回"）。
// 批量放置时这必然发生：板1 实测 49 次放置里 27 次报失败，而 50 个器件全在板上。
//
// 信退出码的调用方只有两条路，两条都错：重试 → 重复器件；中止 → 以为没落下。
// 所以把读回做进命令里，让它**明确回答落没落**。

import (
	"encoding/json"
	"fmt"
	"time"
)

// placedComponent 是读回文档里我们关心的字段。
type placedComponent struct {
	ComponentType string  `json:"componentType"`
	Designator    string  `json:"designator"`
	X             float64 `json:"x"`
	Y             float64 `json:"y"`
}

// scanForPlacement 是**纯函数**：给定读回文档，判断刚才那次放置到底落没落。
//
// 抽成纯函数是为了能单测——"假失败"这条路径在真机上依赖连接器降级，很难稳定
// 复现，但判定逻辑必须是确定的。
//
// 判定顺序：
//  1. 有位号 → 按位号（--designator 是原子赋值，最可靠）
//  2. 没有位号 → 按坐标，允许 ±1 的浮点误差
//
// 只有 componentType=="part" 才算——图框也是 component，但它不是器件。
func scanForPlacement(components []placedComponent, designator string,
	x, y float64) (bool, string) {
	if designator != "" {
		for _, c := range components {
			if c.ComponentType == "part" && c.Designator == designator {
				return true, "位号 " + designator + " 已在板上"
			}
		}
		return false, "读回里没有位号 " + designator
	}
	for _, c := range components {
		if c.ComponentType != "part" {
			continue
		}
		dx, dy := c.X-x, c.Y-y
		if dx < 0 {
			dx = -dx
		}
		if dy < 0 {
			dy = -dy
		}
		if dx <= 1 && dy <= 1 {
			return true, fmt.Sprintf("坐标 (%.0f,%.0f) 上已有器件 %s", x, y, c.Designator)
		}
	}
	return false, fmt.Sprintf("坐标 (%.0f,%.0f) 附近没有器件", x, y)
}

// placeLanded 读回原理图并判定。读不到原理图本身也算"没确认落上"——
// 宁可让人再跑一次，也不要在没证据的情况下说"已经在了"。
func placeLanded(cfg *appConfig, window, designator string, x, y float64) (bool, string) {
	res, err := requestActionTimed(cfg, "schematic.components.list", window,
		map[string]any{}, 30*time.Second)
	if err != nil {
		return false, "读回失败，无法确认：" + err.Error()
	}
	raw, mErr := json.Marshal(res.Result)
	if mErr != nil {
		return false, "读回结果无法解析"
	}
	var doc struct {
		Components []placedComponent `json:"components"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		return false, "读回结果不是预期结构"
	}
	return scanForPlacement(doc.Components, designator, x, y)
}
