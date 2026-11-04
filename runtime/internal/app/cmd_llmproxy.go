package app

// cmd_llmproxy.go — 本机 LLM 代理（127.0.0.1:23190）。
//
// # 它解决什么
//
// 有了服务器端的 LLM 转发，Agent 也可以直接指 <服务器>/llm —— 但那样
// **token 会写进 Agent 的配置文件**。Agent 配置经常被截图、被贴进群、
// 被提交到仓库。token 进了那里就等于泄露。
//
// 这个代理让 Agent 只看到 `http://127.0.0.1:23190/v1`：本机回环地址不含
// 任何凭据，而 token 由代理在转发时补上，读的是 easycirq login 存的凭据文件。
//
// # 边界
//
//   · 只监听 127.0.0.1（不对外）
//   · 只转发，不改写内容
//   · 真 key 从不经过这里——服务器换 key，本机永远看不到

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
)

// DefaultLLMProxyAddr 是本机代理的默认监听地址。B 方案里定的就是它。
const DefaultLLMProxyAddr = "127.0.0.1:23190"

func newLLMProxyCmd(stdout, stderr io.Writer) *cobra.Command {
	var listen string
	c := &cobra.Command{
		Use:   "llm-proxy",
		Short: "本机 LLM 代理：让 Agent 指向本机，token 不进它的配置",
		Long: "把 Agent 的 base_url 指向本机回环地址，转发时补上 easycirq login 存的 token。\n\n" +
			"  easycirq login --server https://<公司服务器> --token <token>\n" +
			"  easycirq llm-proxy                       # 前台运行\n" +
			"  easycirq llm-proxy --listen 127.0.0.1:23190\n\n" +
			"然后把 Agent 的 base_url 配成 http://127.0.0.1:23190/v1。\n\n" +
			"**为什么要有这一层**：直接让 Agent 指服务器地址，就得把 token 写进\n" +
			"Agent 的配置文件，而这类文件经常被截图、被贴进群、被提交到仓库。\n" +
			"本机回环地址里没有任何凭据。\n\n" +
			"只监听回环，不对外；只转发，不改写；真 key 从不经过这里。",
		Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			cred, remote, err := loadCredentials()
			if err != nil {
				return err
			}
			if !remote {
				return fmt.Errorf("还没有登录公司服务器：\n" +
					"  easycirq login --server https://<公司服务器> --token <token>\n" +
					"（本机代理要拿你的 token 才能转发）")
			}

			ln, err := net.Listen("tcp", listen)
			if err != nil {
				return fmt.Errorf("监听 %s 失败: %w", listen, err)
			}

			// 只接受回环来源：哪怕误配成 0.0.0.0，也不把转发能力给到外网。
			handler := loopbackOnly(newLLMProxyHandler(cred))

			srv := &http.Server{Handler: handler, ReadHeaderTimeout: 5 * time.Second}
			fmt.Fprintf(stdout, "本机 LLM 代理已在 http://%s 上监听\n", ln.Addr().String())
			fmt.Fprintf(stdout, "  转发到：%s/llm\n", cred.Server)
			fmt.Fprintf(stdout, "  Agent 的 base_url 配成：http://%s/v1\n", ln.Addr().String())
			fmt.Fprintf(stdout, "  token 只在这个进程里用，不会写进 Agent 的配置。\n")
			fmt.Fprintf(stdout, "  Ctrl+C 停止。\n")

			ctx, stop := signal.NotifyContext(context.Background(),
				os.Interrupt, syscall.SIGTERM)
			defer stop()

			errCh := make(chan error, 1)
			go func() { errCh <- srv.Serve(ln) }()
			select {
			case <-ctx.Done():
				shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				defer cancel()
				return srv.Shutdown(shutdownCtx)
			case err := <-errCh:
				if errors.Is(err, http.ErrServerClosed) {
					return nil
				}
				return err
			}
		},
	}
	c.Flags().StringVar(&listen, "listen", DefaultLLMProxyAddr,
		"监听地址（只应绑回环）")
	return c
}

// loopbackOnly 拒绝非回环来源。误配成 0.0.0.0 时也不至于把转发能力放出去。
func loopbackOnly(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			http.Error(w, "bad remote addr", http.StatusBadRequest)
			return
		}
		ip := net.ParseIP(host)
		if ip == nil || !ip.IsLoopback() {
			http.Error(w,
				"this proxy only serves requests from this machine",
				http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// newLLMProxyHandler 把 /v1/... 转发到 <server>/llm/v1/...，带上 token。
func newLLMProxyHandler(cred Credentials) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Agent 配的 base_url 是 /v1，请求路径会是 /v1/chat/completions
		// 这类；原样接到服务器的 /llm 后面。
		sub := strings.TrimPrefix(r.URL.Path, "/")
		if sub == "" {
			http.Error(w, "missing path", http.StatusNotFound)
			return
		}
		target := cred.Server + "/llm/" + sub
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}

		ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
		defer cancel()
		req, err := http.NewRequestWithContext(ctx, r.Method, target, r.Body)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		for _, h := range []string{"Content-Type", "Accept"} {
			if v := r.Header.Get(h); v != "" {
				req.Header.Set(h, v)
			}
		}
		// 这里加的是**工程师的 token**；真 key 由服务器换。
		req.Header.Set("Authorization", "Bearer "+cred.Token)

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			http.Error(w,
				"company server unreachable: "+err.Error(),
				http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		if v := resp.Header.Get("Content-Type"); v != "" {
			w.Header().Set("Content-Type", v)
		}
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	})
}
