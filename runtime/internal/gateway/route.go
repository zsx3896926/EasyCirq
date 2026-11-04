package gateway

// route.go — 把连接器与请求按 token 送到对应租户。
//
// 这里**不做协议转换**：租户的 daemon 原样处理 /eda 的 WebSocket 升级和
// /action 的请求体。gateway 只回答一个问题：这个 token 是谁，他的
// daemon 是哪一个。

import (
	"net/http"
	"strings"
)

// handleConnector 接受连接器的 WebSocket 升级。
//
// token 从 query 取（连接器只能给一个 URL，没有设请求头的地方）。
// 未知或过期的 token 一律 401，且**不区分**「不存在」和「过期」以外的细节：
// 前者不给攻击者枚举信息，后者对工程师有用所以明说。
func (s *Server) handleConnector(w http.ResponseWriter, r *http.Request) {
	presented := strings.TrimSpace(r.URL.Query().Get("token"))
	if presented == "" {
		writeJSON(w, http.StatusUnauthorized, map[string]any{
			"error": "token required",
			"hint":  "在插件的 easycirqAuthToken 配置里填发到的 token",
		})
		return
	}
	tok, ok := s.opts.Tokens.lookup(presented)
	if !ok {
		// 逐字相同的一句话：不透露 token 是否存在。
		writeJSON(w, http.StatusUnauthorized, map[string]any{
			"error": "token not accepted",
			"hint":  "token 不存在、已过期，或未在服务端登记",
		})
		return
	}
	t, err := s.tenantFor(tok)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{
			"error": "tenant unavailable",
			"detail": err.Error(),
		})
		return
	}
	// 交给该租户的 daemon 处理升级。它自己的 /eda 会做握手与窗口注册。
	t.handle.ServeHTTP(w, r)
}

// handleAction 接受 CLI / Agent 发来的命令请求。
//
// token 走 Authorization: Bearer（这里**不**接受 query，避免命令与 token
// 一起进日志和 shell 历史）。
func (s *Server) handleAction(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	presented := bearerToken(r)
	if presented == "" {
		writeJSON(w, http.StatusUnauthorized, map[string]any{
			"error": "missing bearer token",
			"hint":  "请求头加 Authorization: Bearer <token>",
		})
		return
	}
	tok, ok := s.opts.Tokens.lookup(presented)
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]any{
			"error": "token not accepted",
			"hint":  "token 不存在、已过期，或未在服务端登记",
		})
		return
	}
	t, err := s.tenantFor(tok)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{
			"error": "tenant unavailable",
			"detail": err.Error(),
		})
		return
	}
	// 租户的 daemon 负责其余一切：门禁、审计、产物、路由到窗口。
	t.handle.ServeHTTP(w, r)
}
