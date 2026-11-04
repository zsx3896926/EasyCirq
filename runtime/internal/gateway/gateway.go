// Package gateway 是企业部署的多租户入口。
//
// # 它是干什么的
//
// 本地模式下，每个工程师机器上跑一个 daemon（单租户、127.0.0.1）。
// 企业部署时，工程师的 EDA 客户端连公司服务器，服务器要同时服务 N 个人，
// 并把每个命令送到**发起它的那个人的窗口**。
//
// 这个包就是那层：按 token 分辨是谁，把连接和请求路由到该租户的 daemon。
//
// # 为什么不是重写一个 daemon
//
// daemon 包里已经有一整套经过测试的东西：变更门禁、审计日志、产物落盘、
// 多窗口路由、陈旧读检测。重写一遍会**造出第二套更弱的规则**——那是最坏的
// 结果，因为工程师会以为自己受同一套门禁保护。
//
// 所以这里给每个租户起一个**进程内**的 daemon（复用 daemon.Server），
// 只按 token 做多路复用。
//
// # 边界（本包不做的事）
//
//   - 不做账号管理、邀请码、密码：token 由外部生成并放进 token 表
//   - 不做 LLM 网关：那是另一件事（见 docs/enterprise-deployment.md）
//   - 不做 TLS 终止：前置反向代理负责，本包只讲明文 HTTP/WS
//   - 不支持跨租户共享窗口：一个 token 只看得见自己的连接
package gateway

import (
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/zsx3896926/EasyCirq/runtime/internal/daemon"
)

// Token 是 token 表里的一条。
type Token struct {
	Token    string `json:"token"`
	Engineer string `json:"engineer"`
	// Expires 为空表示不过期。企业应当设它——token 走 query 参数，
	// 会出现在代理日志里，长期有效的 token 等于长期泄露。
	Expires string `json:"expires,omitempty"`
}

// TokenTable 是全部可用 token。文件格式：
//
//	{"tokens": [{"token": "...", "engineer": "张工", "expires": "2026-12-31T00:00:00Z"}]}
type TokenTable struct {
	Tokens []Token `json:"tokens"`
}

// LoadTokenTable 从 JSON 读 token 表。
func LoadTokenTable(r io.Reader) (*TokenTable, error) {
	var t TokenTable
	dec := json.NewDecoder(r)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&t); err != nil {
		return nil, fmt.Errorf("token table: %w", err)
	}
	seen := map[string]bool{}
	for i, tok := range t.Tokens {
		if strings.TrimSpace(tok.Token) == "" {
			return nil, fmt.Errorf("token table: entry %d has an empty token", i)
		}
		if seen[tok.Token] {
			return nil, fmt.Errorf("token table: duplicate token at entry %d", i)
		}
		seen[tok.Token] = true
		if strings.TrimSpace(tok.Engineer) == "" {
			return nil, fmt.Errorf("token table: entry %d has no engineer name"+
				" — an unnamed token cannot be audited", i)
		}
	}
	return &t, nil
}

// lookup 找到 token 对应的条目。用常数时间比较，避免靠响应时间猜 token。
func (t *TokenTable) lookup(presented string) (Token, bool) {
	if t == nil || presented == "" {
		return Token{}, false
	}
	var found Token
	ok := false
	for _, cand := range t.Tokens {
		if subtle.ConstantTimeCompare([]byte(cand.Token), []byte(presented)) == 1 {
			found = cand
			ok = true
			// 不 break：即使命中也要把所有条目比完，否则响应时间会透露
			// 命中的位置。
		}
	}
	if !ok {
		return Token{}, false
	}
	if found.Expires != "" {
		exp, err := time.Parse(time.RFC3339, found.Expires)
		if err != nil || time.Now().After(exp) {
			return found, false
		}
	}
	return found, true
}

// tenant 是一个租户的运行时：一个进程内 daemon。
type tenant struct {
	token  Token
	srv    *daemon.Server
	handle http.Handler
	stop   func()
}

// Options 配置 gateway。
type Options struct {
	// Tokens 是鉴权来源。为 nil 时所有请求一律拒绝（而不是放行）。
	Tokens *TokenTable
	// Log 接收诊断输出。
	Log io.Writer
	// PublicPort 是 gateway 对外公布的端口，只用于 /health 的展示。
	PublicPort int
	// DaemonOptions 用于给每个租户造 daemon。Host/Port 必须为空——
	// 租户的 daemon 不绑端口。
	DaemonOptions daemon.Options
	// LLM 是转发配置。BaseURL 为空表示**不启用**转发。
	LLM LLMOptions
}

// Server 是多租户入口。
type Server struct {
	opts    Options
	log     io.Writer
	mu      sync.Mutex
	tenants map[string]*tenant // 按 token 建，懒加载
}

// New 构造 gateway。不绑定端口——由调用方决定怎么监听。
func New(opts Options) *Server {
	logw := opts.Log
	if logw == nil {
		logw = io.Discard
	}
	return &Server{opts: opts, log: logw, tenants: map[string]*tenant{}}
}

// tenantFor 取（必要时创建）token 对应的租户运行时。
func (s *Server) tenantFor(tok Token) (*tenant, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if t, ok := s.tenants[tok.Token]; ok {
		return t, nil
	}

	dopts := s.opts.DaemonOptions
	// 租户 daemon 绝不能绑端口：它是进程内的，端口留给 gateway。
	// 端口范围给一个占位值即可，health 展示用 PublicPort。
	dopts.Host = "127.0.0.1"
	if dopts.PortStart == 0 {
		dopts.PortStart, dopts.PortEnd = 1, 1
	}

	srv := daemon.New(dopts)
	stop := srv.Prepare(s.log)
	t := &tenant{
		token:  tok,
		srv:    srv,
		handle: srv.Handler(s.opts.PublicPort),
		stop:   stop,
	}
	s.tenants[tok.Token] = t
	fmt.Fprintf(s.log, "gateway: tenant %q (%s) created\n",
		tok.Engineer, redact(tok.Token))
	return t, nil
}

// Close 释放全部租户。
func (s *Server) Close() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, t := range s.tenants {
		if t.stop != nil {
			t.stop()
		}
	}
	s.tenants = map[string]*tenant{}
}

// redact 把 token 变成可进日志的形式：只露前 4 位。
// token 走 query 参数，会进代理日志，所以**我们自己不要再多露一处**。
func redact(token string) string {
	if len(token) <= 4 {
		return "***"
	}
	return token[:4] + "…"
}

// Routes 返回 gateway 的 HTTP 面。
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/eda", s.handleConnector)
	mux.HandleFunc("/action", s.handleAction)
	// "/llm/" 之后是原样透传的上游路径（如 /llm/v1/chat/completions）
	mux.HandleFunc("/llm/", s.handleLLM)
	return mux
}

// bearerToken 从 Authorization: Bearer 取 token；/eda 走 query。
func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	const prefix = "Bearer "
	if len(h) > len(prefix) && strings.EqualFold(h[:len(prefix)], prefix) {
		return strings.TrimSpace(h[len(prefix):])
	}
	return ""
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	s.mu.Lock()
	n := len(s.tenants)
	s.mu.Unlock()
	writeJSON(w, http.StatusOK, map[string]any{
		"service": "easycirq-gateway",
		"tenants": n,
		"tokens":  tokenCount(s.opts.Tokens),
		"llm":     strings.TrimSpace(s.opts.LLM.BaseURL) != "",
		"version": "1",
	})
}

func tokenCount(t *TokenTable) int {
	if t == nil {
		return 0
	}
	return len(t.Tokens)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}
