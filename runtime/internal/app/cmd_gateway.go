package app

// cmd_gateway.go — 企业部署：在服务器上跑多租户入口。
//
// 这是 L2 的服务端。它做的事很窄：按 token 分辨是谁，把握手和命令送到
// 那个人自己的 daemon 实例（进程内复用 daemon 包）。门禁、审计、产物、
// 窗口路由全部沿用 daemon 的既有实现——**不在这里重写**，否则会出现
// 第二套更弱的规则。

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"github.com/zsx3896926/EasyCirq/runtime/internal/daemon"
	"github.com/zsx3896926/EasyCirq/runtime/internal/gateway"
	"github.com/zsx3896926/EasyCirq/runtime/internal/version"
)

func newGatewayCmd(stdout, stderr io.Writer) *cobra.Command {
	var tokensPath, listen string
	var asJSON bool

	c := &cobra.Command{
		Use:   "gateway",
		Short: "在服务器上跑多租户入口，供企业统一部署",
		Long: "让多个工程师的 EDA 客户端连同一台公司服务器。\n\n" +
			"每个 token 对应一个人，命令只会送到那个人自己的窗口——**跨租户互不可见**。\n\n" +
			"  easycirq gateway --tokens tokens.json --listen :8443\n\n" +
			"token 表格式：\n" +
			"  {\"tokens\": [{\"token\": \"...\", \"engineer\": \"张工\",\n" +
			"                \"expires\": \"2026-12-31T00:00:00Z\"}]}\n\n" +
			"部署要点：\n" +
			"  · TLS 由前置反向代理终止，本命令只讲明文 HTTP/WS\n" +
			"  · 客户端把 easycirqDaemonUrl 指向 wss://<代理>/eda，\n" +
			"    easycirqAuthToken 填发到的 token\n" +
			"  · /health 免鉴权，可用于负载均衡探活\n\n" +
			"尚不包含（有意为之）：账号管理、邀请码、LLM 网关、跨机器数据同步。",
		Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			if strings.TrimSpace(tokensPath) == "" {
				return fmt.Errorf("需要 --tokens <token 表路径>：\n" +
					"  easycirq gateway --tokens tokens.json --listen :8443\n" +
					"（没有 token 表就没人能连，跑起来也没用）")
			}
			f, err := os.Open(tokensPath)
			if err != nil {
				return fmt.Errorf("打开 token 表失败: %w", err)
			}
			defer f.Close()
			tbl, err := gateway.LoadTokenTable(f)
			if err != nil {
				return err
			}

			gw := gateway.New(gateway.Options{
				Tokens:     tbl,
				Log:        stderr,
				PublicPort: portOf(listen),
				DaemonOptions: daemon.Options{
					Version:   version.Version,
					PortStart: 1,
					PortEnd:   1,
					Host:      "127.0.0.1",
					ArtifactDir: "",
				},
			})
			defer gw.Close()

			srv := &http.Server{
				Handler:           gw.Routes(),
				ReadHeaderTimeout: 5 * time.Second,
			}

			ln, err := net.Listen("tcp", listen)
			if err != nil {
				return fmt.Errorf("监听 %s 失败: %w", listen, err)
			}

			if asJSON {
				fmt.Fprintf(stdout,
					"{\"service\": \"easycirq-gateway\", \"listen\": %q, \"tokens\": %d}\n",
					ln.Addr().String(), len(tbl.Tokens))
			} else {
				fmt.Fprintf(stdout, "easycirq gateway 已在 %s 上监听\n", ln.Addr().String())
				fmt.Fprintf(stdout, "  token 数：%d\n", len(tbl.Tokens))
				fmt.Fprintln(stdout, "  客户端配置：easycirqDaemonUrl = wss://<此地址前置代理>/eda")
				fmt.Fprintln(stdout, "  注意：本进程只讲明文 HTTP/WS，TLS 由前置代理终止。")
			}

			ctx, stop := signal.NotifyContext(context.Background(),
				os.Interrupt, syscall.SIGTERM)
			defer stop()

			errCh := make(chan error, 1)
			go func() { errCh <- srv.Serve(ln) }()

			select {
			case <-ctx.Done():
				shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
				defer cancel()
				return srv.Shutdown(shutdownCtx)
			case err := <-errCh:
				if err == http.ErrServerClosed {
					return nil
				}
				return err
			}
		},
	}
	c.Flags().StringVar(&tokensPath, "tokens", "", "token 表 JSON 路径（必填）")
	c.Flags().StringVar(&listen, "listen", ":8443", "监听地址，如 :8443 或 127.0.0.1:8443")
	c.Flags().BoolVar(&asJSON, "json", false, "以 JSON 输出启动信息")
	return c
}

// portOf 从 ":8443" / "127.0.0.1:8443" 里取端口，只用于 /health 的展示。
func portOf(listen string) int {
	if i := strings.LastIndex(listen, ":"); i >= 0 {
		if p, err := strconv.Atoi(listen[i+1:]); err == nil {
			return p
		}
	}
	return 0
}
