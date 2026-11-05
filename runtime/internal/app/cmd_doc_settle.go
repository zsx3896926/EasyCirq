package app

import (
	"fmt"
	"time"
)

// Doc/page state is an implicit global in EasyEDA: `document.open` returns as
// soon as the tab is created, BEFORE the page's primitives/netlist finish
// (re)loading. A read command fired immediately after a switch therefore
// samples a half-loaded page and gets empty/stale data (issue #67). These
// helpers close that race by (1) confirming the target is the live active
// document and (2) waiting until its data stops changing.

// settleTracker decides when a sequence of sampled primitive counts has
// "settled" — the connector exposes no load-complete signal, so we treat a
// count that is identical across two consecutive polls as loaded. A non-empty
// stable count settles immediately; a stable count of 0 only settles after a
// grace window (minEmptySamples), so a page mid-load (0 → 93) is not mistaken
// for a genuinely empty page.
type settleTracker struct {
	last            int
	hasLast         bool
	samples         int
	minEmptySamples int
}

// observe records one sample and reports whether the page has settled.
func (s *settleTracker) observe(count int) bool {
	s.samples++
	prev, had := s.last, s.hasLast
	s.last, s.hasLast = count, true
	if !had || prev != count {
		return false
	}
	if count > 0 {
		return true
	}
	return s.samples >= s.minEmptySamples
}

// docSettleDeadline bounds how long waitDocSettle polls before giving up and
// letting the caller proceed with whatever the page currently holds.
const docSettleDeadline = 8 * time.Second

// docSettleInterval is the gap between primitive-count samples.
const docSettleInterval = 400 * time.Millisecond

// docSettleMaxProbeErrors caps consecutive probe failures. The probe is a plain
// read; when it fails this many times in a row it is not "still loading", it is
// the wrong probe for this document (or the window is gone), and polling on to
// the deadline only produces noise. Issue #161: a PCB target used to burn the
// full 8s as 21 consecutive EDA_CALL_FAILED rows in the audit log, all of them
// swallowed into "keep polling".
const docSettleMaxProbeErrors = 3

// settleProbeAction picks the count probe for a document type. The two document
// families expose disjoint list actions, so probing with the wrong one fails on
// every sample rather than returning a count.
func settleProbeAction(docType string) string {
	if docType == "pcb" {
		return "pcb.components.list"
	}
	return "schematic.components.list"
}

// countActivePageWith reads the active document's component count via the given
// list action. The second return distinguishes "read produced a count" from
// "read failed" so the caller can stop retrying a probe that cannot work here.
func countActivePageWith(cfg *appConfig, window, action string) (int, bool) {
	res, err := requestAction(cfg, action, window, nil)
	if err != nil || res.Result == nil {
		return 0, false
	}
	if c, ok := res.Result["count"].(float64); ok {
		return int(c), true
	}
	if comps, ok := res.Result["components"].([]any); ok {
		return len(comps), true
	}
	return 0, false
}

// waitDocSettle polls the active page's primitive count until it stabilizes
// (two identical consecutive reads) or the deadline passes. It returns true if
// the page settled, false on timeout — callers proceed either way, using the
// bool to flag ready:false when the page never quieted down.
func waitDocSettle(cfg *appConfig, window string) bool {
	return waitDocSettleFor(cfg, window, "schematic")
}

// waitDocSettleFor is waitDocSettle with the probe chosen by document type, so
// a PCB target is polled with pcb.components.list instead of the schematic
// probe. It also bails out after docSettleMaxProbeErrors consecutive read
// failures instead of spinning to the deadline (issue #161).
func waitDocSettleFor(cfg *appConfig, window, docType string) bool {
	action := settleProbeAction(docType)
	tracker := &settleTracker{minEmptySamples: 3}
	deadline := time.Now().Add(docSettleDeadline)
	probeErrors := 0
	for {
		count, ok := countActivePageWith(cfg, window, action)
		if ok {
			probeErrors = 0
			if tracker.observe(count) {
				return true
			}
		} else {
			probeErrors++
			if probeErrors >= docSettleMaxProbeErrors {
				return false
			}
		}
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(docSettleInterval)
	}
}

// pageScope captures the state switchToPage changed so a caller can restore the
// original active document after a page-scoped read.
type pageScope struct {
	window     string
	prevActive string // active document uuid before the switch (may be "")
	switched   bool   // true if we actually changed the active document
	settled    bool   // true if the target page settled before the deadline
}

// switchToPage resolves a --page target (name or uuid) in the given window,
// brings it to the front if it is not already active, and waits for its data to
// settle. It returns a pageScope so the caller can optionally restore the prior
// active document. Making the page an explicit parameter removes the implicit
// global-state race: check/read/list act on the page the caller named, not
// whatever tab happened to be foreground.
func switchToPage(cfg *appConfig, window, target string) (pageScope, error) {
	docs, activeUUID, win, err := discoverDocs(cfg, window)
	if err != nil {
		return pageScope{}, err
	}
	match, err := resolveDoc(docs, target)
	if err != nil {
		return pageScope{}, err
	}
	sc := pageScope{window: win, prevActive: activeUUID}
	if match.UUID != activeUUID {
		if _, err := requestAction(cfg, "document.open", win,
			map[string]any{"uuid": match.UUID}); err != nil {
			return pageScope{}, err
		}
		sc.switched = true
	}
	// Probe by the resolved document's own type: `doc switch` already guarded
	// this, but --page went through here unguarded, so a PCB target polled the
	// schematic probe 21 times over the full deadline (issue #161).
	sc.settled = waitDocSettleFor(cfg, win, match.Type)
	if err := settleGateError(sc.settled, sc.switched); err != nil {
		return pageScope{}, err
	}
	return sc, nil
}

// settleGateError 决定"切页没就绪"要不要变成错误。
//
// **切页没就绪 != 页面是空的。** 这是「读路径不认 --page」这一族的根因
// （#24 / #39 / 板2 清空脚本）：切过去之后页面还没渲染完，
// `components.list` 返回 0 条，调用方拿到一个**看起来空、其实没读成**的页面 ——
// 于是「删 30 个器件」变成「报告已空、什么也没删」，而退出码是 0。
//
// 只在**真的切过页**时才报错：本来就在这一页、探针也没稳定，说明这一页此刻就是
// 这个样子，读它不比别的时候更不可信；而切页场景下"没就绪"几乎一定意味着
// "读到的是半成品"。
func settleGateError(settled, switched bool) error {
	if settled || !switched {
		return nil
	}
	return fmt.Errorf(
		"切到页面后它没有就绪（探针在期限内没拿到稳定结果）—— " +
			"此时读到的器件数**不可信**，不要当成空页；重试，或先 `easycirq doc switch` 再读")
}

// switchToPageBestEffort 与 switchToPage 相同，但**容忍未就绪**。
//
// 只给那些"读到的数据本来就只是提示、拿到空也不致误判"的调用方用。
// 默认路径必须是严格的 —— 宽松的语义要显式选。
func switchToPageBestEffort(cfg *appConfig, window, target string) (pageScope, error) {
	docs, activeUUID, win, err := discoverDocs(cfg, window)
	if err != nil {
		return pageScope{}, err
	}
	match, err := resolveDoc(docs, target)
	if err != nil {
		return pageScope{}, err
	}
	sc := pageScope{window: win, prevActive: activeUUID}
	if match.UUID != activeUUID {
		if _, err := requestAction(cfg, "document.open", win,
			map[string]any{"uuid": match.UUID}); err != nil {
			return pageScope{}, err
		}
		sc.switched = true
	}
	sc.settled = waitDocSettleFor(cfg, win, match.Type)
	return sc, nil
}

// restore switches back to the document that was active before switchToPage, if
// switchToPage actually changed it. Best-effort: a restore failure is returned
// so the caller can surface it, but the primary read has already happened.
func (sc pageScope) restore(cfg *appConfig) error {
	if !sc.switched || sc.prevActive == "" {
		return nil
	}
	_, err := requestAction(cfg, "document.open", sc.window,
		map[string]any{"uuid": sc.prevActive})
	return err
}
