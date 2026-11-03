package app

// cmd_login.go — 一条命令接入公司服务器。
//
// 存在意义：L2 的终态是「工程师机器可以不装 easycirq.exe」。要做到这一点，
// 至少得让他们**不用手动配 daemon 地址和 token**——那正是这一步。
//
// 登录只做三件事：验证服务器确实在跑、存下地址与 token、告诉人接下来会怎样。
// 它**不碰 LLM 密钥**：那是服务端的事，工程师机器上不该出现。

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

func newLoginCmd(stdout, stderr io.Writer) *cobra.Command {
	var server, token, engineer string
	var statusOut, logout bool

	c := &cobra.Command{
		Use:   "login",
		Short: "登录公司服务器，之后所有命令发往那里",
		Long: "企业部署下把命令发往公司服务器，而不是本机 daemon。\n\n" +
			"  easycirq login --server https://easycirq.company.com --token <token>\n" +
			"  easycirq login --status     看当前登录状态\n" +
			"  easycirq login --logout     退出登录，回到本机模式\n\n" +
			"登录后会做一次连通性检查（GET /health）。连不上就保存，等于让工程师\n" +
			"以为配置好了其实用不了，所以宁可当场失败。\n\n" +
			"**这个命令不配置、也不保存 LLM 密钥。** 密钥只在公司服务器上；\n" +
			"工程师机器上保存的只是你的 token。",
		Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			if statusOut {
				return printLoginStatus(stdout)
			}
			if logout {
				if err := clearCredentials(); err != nil {
					return fmt.Errorf("退出登录失败: %w", err)
				}
				fmt.Fprintln(stdout, "已退出登录。之后的命令发往本机 daemon（如果没有，先运行 easycirq daemon start）。")
				return nil
			}

			if strings.TrimSpace(server) == "" || strings.TrimSpace(token) == "" {
				return fmt.Errorf("需要 --server 和 --token：\n" +
					"  easycirq login --server https://<公司服务器> --token <token>\n" +
					"（token 向公司管理员申请；没有 token 就没人能验证你是谁）")
			}

			srv := strings.TrimRight(strings.TrimSpace(server), "/")
			if !strings.HasPrefix(srv, "https://") && !strings.HasPrefix(srv, "http://") {
				return fmt.Errorf("--server 必须是 http:// 或 https:// 开头，收到 %q\n"+
					"（内网用 http 也可以，但 token 会明文传输，建议用 https）", srv)
			}

			// 连通性检查：连不上就别存。
			health, err := probeServerHealth(srv)
			if err != nil {
				return fmt.Errorf("连不上 %s：%w\n"+
					"  确认服务器地址、公司网络是否可达，以及网关是否在运行", srv, err)
			}
			// **还必须验证 token 本身。**
			//
			// /health 是免鉴权的，只探它在 2026-11-03 的实测里放过了
			// 一个错误 token：登录报成功，之后每条命令 401。工程师会以为
			// 配置好了，实际一条都发不出去——正是要防的那类"看起来成了"。
			//
			// system.health 由服务端自己回答，不需要 EDA 窗口，
			// 所以拿它做鉴权探测最合适：它只证明"这个 token 被接受"。
			if err := probeServerAuth(srv, strings.TrimSpace(token)); err != nil {
				return fmt.Errorf("token 被服务器拒绝：%w\n"+
					"  可能已过期、已吊销，或不是这家服务器的 token。\n"+
					"  向管理员确认后重试；凭据未保存。", err)
			}

			cred := Credentials{Server: srv, Token: strings.TrimSpace(token),
				Engineer: strings.TrimSpace(engineer)}
			path, err := saveCredentials(cred)
			if err != nil {
				return fmt.Errorf("保存凭据失败: %w", err)
			}

			fmt.Fprintf(stdout, "已登录 %s\n", srv)
			if engineer != "" {
				fmt.Fprintf(stdout, "  工程师：%s\n", engineer)
			}
			fmt.Fprintf(stdout, "  服务器：%s（%v 个已登记 token）\n", srv, health["tokens"])
			fmt.Fprintf(stdout, "  凭据保存到：%s\n", path)
			fmt.Fprintln(stdout)
			fmt.Fprintln(stdout, "之后的命令都发往公司服务器。要回到本机模式：easycirq login --logout")
			fmt.Fprintln(stdout, "注意：这只代表你能连上服务器，不代表你的 EDA 客户端已经连上——")
			fmt.Fprintln(stdout, "      客户端需要在插件里配 easycirqDaemonUrl 和 easycirqAuthToken。")
			return nil
		},
	}
	c.Flags().StringVar(&server, "server", "", "公司服务器地址，如 https://easycirq.company.com")
	c.Flags().StringVar(&token, "token", "", "管理员发的 token")
	c.Flags().StringVar(&engineer, "engineer", "", "（可选）你的名字，只用于显示")
	c.Flags().BoolVar(&statusOut, "status", false, "显示当前登录状态")
	c.Flags().BoolVar(&logout, "logout", false, "退出登录，回到本机模式")
	return c
}

// probeServerHealth 确认服务器是活的。返回 /health 的内容。
func probeServerHealth(server string) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, server+"/health", nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("/health 返回 %d", resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&out); err != nil {
		return nil, fmt.Errorf("/health 不是 JSON：%w", err)
	}
	if out["service"] != "easycirq-gateway" {
		return nil, fmt.Errorf("这个地址不是 EasyCirq 网关（service=%v）", out["service"])
	}
	return out, nil
}

// printLoginStatus 打印当前登录状态。未登录是正常状态，不报错。
func printLoginStatus(out io.Writer) error {
	cred, remote, err := loadCredentials()
	if err != nil {
		return err
	}
	if !remote {
		fmt.Fprintln(out, "当前：未登录（命令发往本机 daemon）")
		fmt.Fprintln(out, "要做企业部署：easycirq login --server https://<公司服务器> --token <token>")
		return nil
	}
	fmt.Fprintf(out, "当前：已登录 %s\n", cred.Server)
	if cred.Engineer != "" {
		fmt.Fprintf(out, "  工程师：%s\n", cred.Engineer)
	}
	fmt.Fprintf(out, "  token：%s\n", redactToken(cred.Token))
	fmt.Fprintf(out, "  凭据文件：%s\n", credentialsFile())
	// 顺手探一次，让「登录了但服务器没了」当场可见
	if _, err := probeServerHealth(cred.Server); err != nil {
		fmt.Fprintf(out, "  ⚠ 现在连不上：%v\n", err)
		fmt.Fprintln(out, "    命令会失败。检查网络，或 easycirq login --logout 回到本机模式。")
		return nil
	}
	fmt.Fprintln(out, "  服务器可达 ✓")
	return nil
}

// redactToken 只露前 4 位。和 gateway 侧同一套口径：
// token 会在很多地方出现，我们自己不该再多露一处。
func redactToken(t string) string {
	t = strings.TrimSpace(t)
	if len(t) <= 4 {
		return "***"
	}
	return t[:4] + "…"
}

// probeServerAuth 用一个需要鉴权的请求验证 token 真的被接受。
//
// 用 system.health：它由服务端 daemon 自己回答，不需要 EDA 窗口，
// 因此不会因为"没人开 EDA"而误判成 token 无效。
func probeServerAuth(server, token string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	body, _ := json.Marshal(map[string]any{
		"type": "request", "version": "v1", "action": "system.health"})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		server+"/action", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	switch resp.StatusCode {
	case http.StatusOK:
		return nil
	case http.StatusUnauthorized, http.StatusForbidden:
		return fmt.Errorf("服务器返回 %d", resp.StatusCode)
	case http.StatusNotFound:
		return fmt.Errorf("服务器没有 /action 端点（返回 404）——这个地址可能不是 EasyCirq 网关")
	default:
		return fmt.Errorf("服务器返回 %d", resp.StatusCode)
	}
}
