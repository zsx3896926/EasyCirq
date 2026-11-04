package app

// conn_seq_persist.go — 把"最近一次观测到的顺序计数器"落盘（卡点 #36）。
//
// 为什么需要：`connSeqLast` 只活在本进程，而 `doctor` / 下一条命令都是新进程。
// 板2 的实测代价是"连接器队列 wedge 了十几轮才被发现" —— 因为没有任何跨进程的
// 地方能看见 `seqAbandoned`。
//
// **落盘的是"最近一次观测"，不是"此刻状态"**。所以文件里带时间戳，读的一方必须
// 如实标注"截至 <时间>"，不能当成实时结论。

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

type persistedConnSeq struct {
	Key          string    `json:"key"`
	Seq          int       `json:"seq"`
	SeqAbandoned int       `json:"seqAbandoned"`
	AbandonedIDs []string  `json:"abandonedIds,omitempty"`
	ObservedAt   time.Time `json:"observedAt"`
}

func connSeqFilePath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".easycirq", "conn-seq.json")
}

// persistConnSeq 写盘。失败**不影响判定**：它只是让下一次新进程能看见，
// 写不进去最坏退回"unknown"，绝不能因为写盘失败把一条真实观测丢掉。
func persistConnSeq(key string, c schSeqCounters) {
	path := connSeqFilePath()
	if path == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(path), 0o755)
	body, err := json.Marshal(persistedConnSeq{
		Key:          key,
		Seq:          c.Seq,
		SeqAbandoned: c.SeqAbandoned,
		AbandonedIDs: c.AbandonedIDs,
		ObservedAt:   time.Now().UTC(),
	})
	if err != nil {
		return
	}
	_ = os.WriteFile(path, body, 0o644)
}

// loadPersistedConnSeq 读回最近一次落盘的观测。
//
// 只接受**带计数器的**记录：没有 seq 字段的旧文件不算数（Known 语义在这里同样成立 ——
// "没带"不等于 0）。
func loadPersistedConnSeq() (schSeqCounters, bool) {
	path := connSeqFilePath()
	if path == "" {
		return schSeqCounters{}, false
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return schSeqCounters{}, false
	}
	var p persistedConnSeq
	if err := json.Unmarshal(body, &p); err != nil {
		return schSeqCounters{}, false
	}
	if p.ObservedAt.IsZero() {
		return schSeqCounters{}, false
	}
	return schSeqCounters{
		Known:        true,
		Seq:          p.Seq,
		SeqAbandoned: p.SeqAbandoned,
		AbandonedIDs: p.AbandonedIDs,
	}, true
}

// persistedConnSeqObservedAt 给报告用：让读者知道这是"截至某时"，不是"此刻"。
func persistedConnSeqObservedAt() time.Time {
	path := connSeqFilePath()
	if path == "" {
		return time.Time{}
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return time.Time{}
	}
	var p persistedConnSeq
	if err := json.Unmarshal(body, &p); err != nil {
		return time.Time{}
	}
	return p.ObservedAt
}
