package app

import "testing"

// 卡点 #6 的验收：查询词一个都没出现，就不许返回。
// 这几条用的是板1 实测到的**真实错配**，不是构造出来的。
func TestLibDeviceMatches(t *testing.T) {
	tvsExpander := map[string]any{
		"name":        "PCA9554DGVR",
		"description": "接口类型:I2C；SMBus;I/O 数量:8;时钟频率(fc):400kHz;",
		"lcsc":        "C2669679",
	}
	nmos := map[string]any{
		"name":        "N沟道MOSFET",
		"description": "漏源电压(Vdss):150V;连续漏极电流(Id):14A;",
		"lcsc":        "C40918661",
	}
	realTvs := map[string]any{
		"name":        "SMBJ5.0A",
		"description": "TVS二极管 单向 5V 击穿电压6.4V SMB",
		"lcsc":        "C115088",
	}
	realLdo := map[string]any{
		"name":        "AMS1117-3.3",
		"description": "线性稳压器 3.3V 1A SOT-223",
		"lcsc":        "C6186",
	}

	cases := []struct {
		name  string
		query string
		comp  map[string]any
		want  bool
	}{
		{"TVS 查询不该命中 I2C 扩展器", "TVS SMBJ", tvsExpander, false},
		{"TVS 查询命中真 TVS", "TVS SMBJ", realTvs, true},
		{"AMS1117 查询不该命中 MOSFET", "AMS1117 3.3", nmos, false},
		{"AMS1117 查询命中真 LDO", "AMS1117 3.3", realLdo, true},
		{"LCSC 号命中", "C6186", realLdo, true},
		{"查不到任何词 → 不命中", "zzz-nonsense", realLdo, false},
		{"查询没有可判定的词 → 不筛选", "-", tvsExpander, true},
	}
	for _, c := range cases {
		if got := libDeviceMatches(c.query, c.comp); got != c.want {
			t.Errorf("%s: libDeviceMatches(%q) = %v, want %v",
				c.name, c.query, got, c.want)
		}
	}
}

func TestLibSearchTokens(t *testing.T) {
	got := libSearchTokens("TVS SMBJ 5.0")
	want := []string{"tvs", "smbj", "5.0"}
	if len(got) != len(want) {
		t.Fatalf("got %v want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got %v want %v", got, want)
		}
	}
	// 单字符会被丢掉：留着只会制造误命中
	if toks := libSearchTokens("a b C6186"); len(toks) != 1 || toks[0] != "c6186" {
		t.Fatalf("单字符应当被丢掉，实际 %v", toks)
	}
}

func TestFilterLibResults(t *testing.T) {
	comps := []map[string]any{
		{"name": "PCA9554DGVR", "description": "接口类型:I2C"},
		{"name": "SMBJ5.0A", "description": "TVS二极管 单向"},
		{"name": "SN74CB3T16211DGVR", "description": "总线开关"},
	}
	kept, dropped := filterLibResults("TVS SMBJ", comps)
	if len(kept) != 1 || dropped != 2 {
		t.Fatalf("应当只留 1 条、丢 2 条，实际 kept=%d dropped=%d", len(kept), dropped)
	}
	if kept[0]["name"] != "SMBJ5.0A" {
		t.Fatalf("留下的应当是真正的 TVS，实际 %v", kept[0]["name"])
	}
}

// 板1 的真凶：封装名 TVSOP-48 里含有 tvs 这三个字母，裸 Contains 会让每次
// "TVS" 查询都命中 TVSOP 封装的任意器件 —— 一颗 16 位锁存器就这样被当成了 TVS。
func TestTokenNeedsAWordBoundary(t *testing.T) {
	latch := map[string]any{
		"name":           "SN74AVC16373DGVR",
		"manufacturerId": "SN74AVC16373DGVR",
		"description":    "SN74AVC16373 具有三态输出的 16 位透明 D 类锁存器",
		"footprintName":  "TVSOP-48_L9.7-W4.4-P0.40-LS6.4-BL",
	}
	if libDeviceMatches("TVS SMBJ", latch) {
		t.Fatal("TVSOP 封装让锁存器被当成了 TVS —— 这正是板1 选错器件的原因")
	}
	real := map[string]any{
		"name":          "SMBJ5.0A",
		"description":   "TVS二极管 单向",
		"footprintName": "SMB_L4.3-W3.7",
	}
	if !libDeviceMatches("TVS SMBJ", real) {
		t.Fatal("真正的 TVS 反而没命中")
	}
	// 封装词仍然要能查：0402 必须命中 0402 封装的器件
	r0402 := map[string]any{
		"name":          "0603WAF1002T5E",
		"description":   "厚膜电阻 10kΩ",
		"footprintName": "R0402",
	}
	if !libDeviceMatches("10k 0402", r0402) {
		t.Fatal("封装词 0402 应当仍然能命中")
	}
}

// 型号前缀必须能命中："STM32F030" 要找到 "STM32F030C8T6"。
// 这条和上一条是同一个改动的两面 —— 边界太松会把 TVSOP 当 TVS，
// 太紧又会把真正想要的型号筛掉。
func TestPartNumberPrefixStillMatches(t *testing.T) {
	mcu := map[string]any{
		"name":           "STM32F030C8T6-YJLTY",
		"manufacturerId": "STM32F030C8T6-YJLTY",
		"footprintName":  "LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL",
	}
	if !libDeviceMatches("STM32F030", mcu) {
		t.Fatal("STM32F030 应当命中 STM32F030C8T6 —— 按型号前缀查是最常见的用法")
	}
	res0402 := map[string]any{"name": "10k", "footprintName": "R0402"}
	if !libDeviceMatches("10k 0402", res0402) {
		t.Fatal("0402 应当命中 R0402")
	}
}
