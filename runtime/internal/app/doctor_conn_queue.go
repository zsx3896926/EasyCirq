package app

// doctor_conn_queue.go — 让 `easycirq doctor` 常驻显示连接器动作队列是否 wedge（卡点 #36）。
//
// 背景（板2 实测）：连接器把每个窗口的动作串成 FIFO 链，并在每条响应上带
// `seqAbandoned` / `abandonedIds`。一旦有动作被放弃，**被放弃的 handler 可能仍在跑**，
// 于是"某个 place 到底落没落地"变得无法判断 —— 此后所有回读都不能当证据。
//
// 问题的严重性不在这个状态本身，而在于**它出现得很安静**：
// 板2 的 `req_683/687/738/742` 从第 22 轮起就在每次响应里出现，
// 直到第 37 轮 `place L4` 超时、`block-apply` 打印四步处置，才第一次被读出来。
// 期间十几轮的所有几何/电气判断，都建立在一个状态未知的画布上。
//
// 所以这条要在 `doctor` 里常驻、字段化、并**给出唯一有效的处置**：完全退出并重启 EDA。

import "fmt"

// doctorConnQueue 是动作队列的健康状况。
type doctorConnQueue struct {
	Known     bool     `json:"known"`     // 连接器有没有带顺序计数器（老版本不带）
	Abandoned int      `json:"abandoned"` // seqAbandoned
	IDs       []string `json:"ids,omitempty"`
	Verdict   string   `json:"verdict"` // clean | wedged | unknown
	Advice    string   `json:"advice,omitempty"`
}

// doctorConnQueueOf 把最近一次观测到的计数器翻成可读结论。
func doctorConnQueueOf(c schSeqCounters) doctorConnQueue {
	q := doctorConnQueue{Known: c.Known, Abandoned: c.SeqAbandoned, IDs: c.AbandonedIDs}
	switch {
	case !c.Known:
		q.Verdict = "unknown"
		q.Advice = "连接器没带顺序计数器（多为旧版本）—— 无法判断动作队列是否 wedge；升级连接器后再看"
	case c.SeqAbandoned == 0:
		q.Verdict = "clean"
	default:
		q.Verdict = "wedged"
		q.Advice = fmt.Sprintf(
			"连接器放弃了 %d 个动作：被放弃的 handler 可能仍在跑，"+
				"所以「某个写入到底落没落地」无法判断，此后所有回读都不能当证据。"+
				"唯一有效处置：完全退出 EasyEDA 并重新打开（不是刷新页面）。"+
				"在此之前别把落块/place 失败当产品缺陷修。",
			c.SeqAbandoned)
	}
	return q
}

// doctorConnQueueFor 取该窗口最近的计数器并转成结论。
func doctorConnQueueFor(window, project string) doctorConnQueue {
	return doctorConnQueueOf(connSeqSnapshot(window, project))
}

// doctorConnQueueProbe 现场探一次动作队列状态。
//
// 为什么必须现场探：`seq` / `seqAbandoned` 是**每条响应**上的顶层字段，
// 而 `connSeqLast` 只活在本进程里。`doctor` 每次都是新进程，读内存桶永远是
// unknown —— 那会让这条检查形同虚设（板2 正是这样安静 wedge 了十几轮）。
//
// 用一个只读动作探：它不会改画布，代价只有一次往返。
// 探不到就返回 unknown，**不**当成 clean。
func doctorConnQueueProbe() doctorConnQueue {
	// 先看本进程（如果 doctor 在同一进程里跑过动作）；没有就读**上次落盘**的观测。
	// 绝不做现场探测：探测本身会往有 wedge 的队列里再塞一条动作。
	if c := connSeqSnapshot("", ""); c.Known {
		return doctorConnQueueOf(c)
	}
	if c, ok := loadPersistedConnSeq(); ok {
		return doctorConnQueueOf(c)
	}
	return doctorConnQueueOf(schSeqCounters{})
}
