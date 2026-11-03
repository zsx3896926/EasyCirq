package gateway

// llm.go — LLM 转发：真 key 只在服务器。
//
// # 这是方案 B 的立论所在
//
// 终态第 3 条是「LLM 密钥只在服务器，工程师机器上任何文件都找不到真 key」。
// 这个文件就是那句承诺的实现。
//
// # 链路
//
//	Agent ──base_url──▶ 工程师机器上的本机代理（easycirq login 起）
//	                        │ 带 token
//	                        ▼
//	                     本文件：/llm/* ──真 key──▶ 公司 LLM
//
// # 三个必须守住的点
//
//  1. **key 从环境变量读，不写进配置文件。** 配置文件会被备份、被复制、
//     被 `cat` 出来；环境变量至少不在文件系统里留一份。
//  2. **上游返回什么就回什么，不解析、不改写。** 我们不是 LLM 网关产品，
//     只是一段带凭据的转发；解析 body 只会引入协议兼容问题。
//  3. **审计只记元数据，不记内容。** 图纸和提示词可能涉密，落盘即泄露。
//     记：谁、什么时候、状态码、耗时、上游给的 usage（如果响应里有）。
//
// # 已知边界（不装）
//
//  · 只做 OpenAI 兼容的转发（`/v1/chat/completions` 这类路径原样透传）。
//    不兼容的协议要另做转换，那取决于客户 C2 的答复。
//  · 不做重试、不做流式之外的缓冲策略：流式原样透传，非流式原样透传。
//  · 不做配额与限流。企业要按人限额，得先有 C5 的答复。

import (
	"context"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// LLMOptions 配置转发。
type LLMOptions struct {
	// BaseURL 是上游 LLM 的根，例如 https://api.deepseek.com 或内网地址。
	// 为空表示**不启用**转发——此时 /llm/* 返回 503 并说明没配。
	BaseURL string
	// APIKeyEnv 是**存放真 key 的环境变量名**。刻意不叫 APIKey：
	// 让调用方只能从环境读，避免有人顺手把 key 写进命令行参数
	// （命令行参数会进 ps 和 shell 历史）。
	APIKeyEnv string
	// Timeout 是单次转发上限，零值用 120s。
	Timeout time.Duration
}

func (o LLMOptions) key() string {
	if o.APIKeyEnv == "" {
		return ""
	}
	return strings.TrimSpace(os.Getenv(o.APIKeyEnv))
}

func (o LLMOptions) timeout() time.Duration {
	if o.Timeout <= 0 {
		return 120 * time.Second
	}
	return o.Timeout
}

// handleLLM 把 /llm/<path> 原样转发到 <BaseURL>/<path>，附上真 key。
//
// 只接受已鉴权的调用（和 /action 同一套 token）。**未登录不给转发**——
// 否则服务器就是一个开放的 LLM 代理人，谁发现地址都能白用公司的额度。
func (s *Server) handleLLM(w http.ResponseWriter, r *http.Request) {
	up := s.opts.LLM
	if strings.TrimSpace(up.BaseURL) == "" {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{
			"error": "LLM forwarding is not configured on this server",
			"hint": "服务端启动时给 --llm-base-url 和 --llm-key-env；" +
				"未配置时不会替任何人转发",
		})
		return
	}
	key := up.key()
	if key == "" {
		// 配了地址却没有 key：这是**配置错误**，不是"没启用"。
		// 明说，否则会表现成上游 401，看起来像用户的 token 有问题。
		writeJSON(w, http.StatusInternalServerError, map[string]any{
			"error": "upstream key missing",
			"hint":  "环境变量 " + up.APIKeyEnv + " 为空或未设置",
		})
		return
	}

	tok, ok := s.opts.Tokens.lookup(bearerToken(r))
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]any{
			"error": "token not accepted",
			"hint":  "token 不存在、已过期，或未在服务端登记",
		})
		return
	}

	// /llm/v1/chat/completions → <base>/v1/chat/completions
	sub := strings.TrimPrefix(r.URL.Path, "/llm")
	sub = strings.TrimPrefix(sub, "/")
	if sub == "" {
		writeJSON(w, http.StatusNotFound, map[string]any{
			"error": "missing upstream path",
			"hint":  "用法：/llm/v1/chat/completions（/llm 之后的路径原样透传）",
		})
		return
	}
	target := strings.TrimRight(up.BaseURL, "/") + "/" + sub
	if r.URL.RawQuery != "" {
		target += "?" + r.URL.RawQuery
	}

	// 绑在入站请求的 context 上：客户端断开时，上游请求立刻放弃，
	// 不给服务器白跑一个没人要的长补全。
	ctx, cancel := context.WithTimeout(r.Context(), up.timeout())
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, r.Method, target, r.Body)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	// 透传与协议相关的头，但**不**透传客户端的 Authorization——
	// 那是我们的 token，不该出现在上游日志里。
	for _, h := range []string{"Content-Type", "Accept"} {
		if v := r.Header.Get(h); v != "" {
			req.Header.Set(h, v)
		}
	}
	req.Header.Set("Authorization", "Bearer "+key)

	started := time.Now()
	resp, err := llmClient.Do(req)
	if err != nil {
		s.logLLM(tok, r.Method, sub, 0, time.Since(started), "transport_error")
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"error": "upstream unreachable",
			"hint":  "服务端到 LLM 的网络不通，检查上游地址与出网策略",
		})
		return
	}
	defer resp.Body.Close()

	// 上游的状态码原样回：401/429/400 的含义必须让调用方原汁原味看到。
	for _, h := range []string{"Content-Type"} {
		if v := resp.Header.Get(h); v != "" {
			w.Header().Set(h, v)
		}
	}
	// 流式响应要能边收边发，别缓。
	w.WriteHeader(resp.StatusCode)
	if _, err := io.Copy(w, resp.Body); err != nil {
		s.logLLM(tok, r.Method, sub, resp.StatusCode, time.Since(started), "stream_interrupted")
		return
	}
	s.logLLM(tok, r.Method, sub, resp.StatusCode, time.Since(started), "")
}

// logLLM 只记元数据。**不记请求体、不记响应体**：
// 图纸和提示词可能涉密，落盘即泄露。
func (s *Server) logLLM(tok Token, method, sub string, status int, dur time.Duration, note string) {
	line := "llm: " + tok.Engineer + " " + method + " " + sub
	if status != 0 {
		line += " -> " + http.StatusText(status)
	}
	line += " " + dur.Round(time.Millisecond).String()
	if note != "" {
		line += " (" + note + ")"
	}
	// token 不写进去——它已经在别处出现过很多次了，这里没必要再留一份。
	s.mu.Lock()
	logw := s.log
	s.mu.Unlock()
	if logw != nil {
		_, _ = io.WriteString(logw, line+"\n")
	}
}

// llmClient 是转发用的 HTTP 客户端。
//
// **刻意不设 Timeout**：流式补全可能几分钟，客户端超时会把正常的长回答掐断。
// 单次请求的时限由 context 控制（LLMOptions.Timeout），上游无响应时也一样生效。
var llmClient = &http.Client{}
