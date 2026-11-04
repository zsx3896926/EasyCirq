package app

// connectorLooksDegraded 探一次连接器健康度，判断它是否处于降级状态。
//
// 用一次**只读**动作（列出器件）来探，而不是去解析 `health` 的输出 ——
// 后者当前混了人话、不是干净 JSON（这本身是另一个待修的点）。
// 只读动作不改变板子，代价是一次往返。
//
// 探不到（连接器还没连上）时返回 false：拒绝 `--replace` 的理由是"降级"，
// 而不是"连不上"——连不上时后续动作自己会失败并报出原因。
func connectorLooksDegraded(cfg *appConfig, window string) bool {
	res, err := requestActionTimed(cfg, "schematic.components.list", window,
		map[string]any{}, acConnectPinTimeout)
	if err != nil || res == nil {
		return false
	}
	return acDegradedWarning(res)
}
