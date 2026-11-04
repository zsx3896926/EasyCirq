package app

// cmd_panel.go — 产品面板：本地网页，把已经存在的东西做得看得见。
//
// 设计铁律（写在代码里，因为最容易被破坏）：
//
//  1. **面板零判定逻辑。** 它不判断"能不能交付"，只把 `easycirq phase show --json`
//     和 `easycirq card --json` 的结果原样搬到浏览器上。一旦这里出现第二套判断，
//     就会有两个真相来源，迟早不一致 —— 而用户看到的那个可能是错的。
//
//  2. **只监听 127.0.0.1。** 与 llm-proxy 同一条纪律。监听 0.0.0.0 意味着同一
//     办公网里任何人都能看到你的板子和你的设计数据。
//
//  3. **面板挂了不影响 CLI。** 两者是独立的进程，面板只是 CLI 的一个消费者。
//
// 为什么用子进程调自己：这样"面板看到的"和"你在终端看到的"必然是同一份，
// 因为跑的是同一条命令。多一次进程启动换掉一整类不一致的 bug，很划算。

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
)

// panelSnapshot 是 /api/snapshot 的返回体：原样转发三个命令的 JSON。
//
// 注意每个字段都是 json.RawMessage —— 面板不做解析、不做汇总、不做判断，
// 只是搬运。这样上游加字段，面板自动就多了字段。
type panelSnapshot struct {
	Project string          `json:"project"`
	Phase   json.RawMessage `json:"phase"`
	Card    json.RawMessage `json:"card"`
	Status  json.RawMessage `json:"status"`
	// Artifacts 是 `easycirq artifacts --json` 的原样转发（P4「历史与产物」）。
	// 面板照旧只搬运不判断 —— 交付证据该列什么由 CLI 决定。
	Artifacts json.RawMessage   `json:"artifacts"`
	Errors    map[string]string `json:"errors,omitempty"`
	FetchedAt string            `json:"fetchedAt"`
}

func newPanelCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var (
		portRaw   string
		project   string
		noBrowser bool
	)
	cmd := &cobra.Command{
		Use:   "panel",
		Short: "打开本地面板：看见这块板走到哪、卡在哪、缺什么",
		Long: "启动一个**只监听 127.0.0.1** 的本地网页。\n\n" +
			"面板不判断任何事——它把 `phase show --json` 和 `card --json` 的结果\n" +
			"原样显示出来。所以你在浏览器里看到的，和你在终端里跑出来的是同一份。\n\n" +
			"  easycirq panel                       # 自动选端口并打开浏览器\n" +
			"  easycirq panel --no-open             # 只打印 URL\n" +
			"  easycirq panel --project <uuid>      # 指定工程\n" +
			"  easycirq panel --port 23115          # 指定端口（被占用则报错）",
		RunE: func(_ *cobra.Command, _ []string) error {
			return runPanel(cfg, portRaw, project, noBrowser, stdout, stderr)
		},
	}
	cmd.Flags().StringVar(&portRaw, "port", "", "端口或区间（默认取 --ports 的区间，从起始端口往后找第一个空闲的）")
	cmd.Flags().StringVar(&project, "project", "", "工程 uuid 或名称（默认用全局 --project）")
	cmd.Flags().BoolVar(&noBrowser, "no-open", false, "只打印 URL，不自动打开浏览器")
	return cmd
}

func runPanel(cfg *appConfig, portRaw, project string, noBrowser bool,
	stdout, stderr io.Writer) error {

	if project == "" {
		project = cfg.project
	}

	ln, addr, err := listenLoopback(cfg, portRaw)
	if err != nil {
		return err
	}
	defer ln.Close()

	self, err := os.Executable()
	if err != nil {
		return fmt.Errorf("找不到自己的可执行文件：%w", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		// CSP：默认只允许自己，不许外链。面板不需要任何外部资源。
		w.Header().Set("Content-Security-Policy",
			"default-src 'self'; style-src 'self' 'unsafe-inline'; "+
				"script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Write(panelHTML)
	})
	// ── /api/run：面板上的"跑门 / 推进"（P3）────────────────────────────
	//
	// 硬要求是「面板操作与 CLI 逐字节一致」。唯一能满足它的做法是**重执行 CLI
	// 本身**并把它的输出原样返回 —— 面板不拼命令、不改写、不解释。
	mux.HandleFunc("/api/run", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", http.MethodPost)
			http.Error(w, "此端点只接受 POST：写操作不能被链接/预取顺带触发", http.StatusMethodNotAllowed)
			return
		}
		var req panelRunRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8<<10)).Decode(&req); err != nil {
			http.Error(w, "请求体不是合法 JSON: "+err.Error(), http.StatusBadRequest)
			return
		}
		if req.Project == "" {
			req.Project = project
		}
		res := runPanelCommand(self, req.Cmd, req.Project, 120*time.Second)
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		enc.Encode(res)
	})

	mux.HandleFunc("/api/snapshot", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query().Get("project")
		if q == "" {
			q = project
		}
		snap := collectSnapshot(self, q)
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		enc.Encode(snap)
	})

	srv := &http.Server{Handler: mux, ReadHeaderTimeout: 10 * time.Second}

	url := "http://" + addr + "/"
	fmt.Fprintf(stdout, "面板已启动：%s\n", url)
	fmt.Fprintf(stdout, "（只监听 127.0.0.1；Ctrl+C 停止。关掉面板不影响 easycirq 命令。）\n")
	if project == "" {
		fmt.Fprintf(stdout, "提示：没指定工程，先跑 easycirq project info 或加 --project <uuid>。\n")
	}

	if !noBrowser {
		openBrowser(url)
	}

	// Ctrl+C 优雅退出。
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		srv.Shutdown(shutCtx)
	}()

	if err := srv.Serve(ln); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}

// listenLoopback 绑定 127.0.0.1 上第一个可用端口。
//
// 显式写死 "127.0.0.1:" 而不是 ":"：后者等于 0.0.0.0，同一网段的人都能访问。
// 这不是可配置项 —— 面板显示的是未公开的设计数据。
func listenLoopback(cfg *appConfig, portRaw string) (net.Listener, string, error) {
	raw := strings.TrimSpace(portRaw)
	if raw == "" {
		raw = cfg.ports
	}
	if raw == "" {
		raw = "23111-23120"
	}
	var start, end int
	if strings.Contains(raw, "-") {
		s, e, err := parsePortRange(raw)
		if err != nil {
			return nil, "", err
		}
		start, end = s, e
	} else {
		p, err := parseSinglePort(raw)
		if err != nil {
			return nil, "", err
		}
		// 指定单个端口时只试这一个：用户点名要它，悄悄换掉更让人困惑。
		start, end = p, p
	}
	var lastErr error
	for p := start; p <= end; p++ {
		addr := fmt.Sprintf("127.0.0.1:%d", p)
		ln, err := net.Listen("tcp", addr)
		if err == nil {
			return ln, addr, nil
		}
		lastErr = err
	}
	return nil, "", fmt.Errorf("面板起不来：端口 %s 全被占用（最后错误：%v）", raw, lastErr)
}

func parseSinglePort(raw string) (int, error) {
	var p int
	if _, err := fmt.Sscanf(raw, "%d", &p); err != nil {
		return 0, fmt.Errorf("端口 %q 不是数字", raw)
	}
	if p <= 0 || p > 65535 {
		return 0, fmt.Errorf("端口 %d 超出范围", p)
	}
	return p, nil
}

// collectSnapshot 调自己拿 JSON，原样转发。
//
// 每个命令失败时把错误放进 errors 而不是崩掉整个面板：一个命令挂了，
// 其他两个还能显示 —— 半张有用的界面比白屏好。
func collectSnapshot(self, project string) panelSnapshot {
	snap := panelSnapshot{
		Project:   project,
		Errors:    map[string]string{},
		FetchedAt: time.Now().Format(time.RFC3339),
	}
	fetch := func(args ...string) (json.RawMessage, string) {
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, self, args...)
		cmd.Stderr = io.Discard
		out, err := cmd.Output()
		// **非零退出不等于没有数据。** `card` 和 `status` 用退出码表达语义
		// （0 可以 / 1 不行 / 2 还没检查过），而 exit 2 时它们照样打印完整 JSON。
		// 早期版本把 err != nil 当成失败直接丢弃 stdout，结果面板永远显示不出
		// "还没检查过"那张卡 —— 而那正是这层界面最该说清的状态。
		// 所以：只要 stdout 是合法 JSON 就用它，退出码只管"命令有没有正常结束"。
		out = []byte(strings.TrimSpace(string(out)))
		if len(out) > 0 && json.Valid(out) {
			return json.RawMessage(out), ""
		}
		if err != nil {
			return nil, err.Error()
		}
		return nil, "输出不是 JSON"
	}

	phaseArgs := []string{"phase", "show", "--json"}
	if project != "" {
		phaseArgs = append(phaseArgs, "--project", project)
	}
	if v, e := fetch(phaseArgs...); v != nil {
		snap.Phase = v
	} else {
		snap.Errors["phase"] = e
	}

	if v, e := fetch("card", "--json"); v != nil {
		snap.Card = v
	} else {
		snap.Errors["card"] = e
	}

	if v, e := fetch("status", "--json"); v != nil {
		snap.Status = v
	} else {
		snap.Errors["status"] = e
	}

	// 产物清单（P4「历史与产物」）：面板只显示 CLI 说的那几样，不自己决定
	// "什么算证据"。限 10 条 —— 一个人要交出去的文件不会比这更多，
	// 而总数由 CLI 的 total 字段如实带出。
	if v, e := fetch("artifacts", "--json", "--limit", "10"); v != nil {
		snap.Artifacts = v
	} else {
		snap.Errors["artifacts"] = e
	}

	if len(snap.Errors) == 0 {
		snap.Errors = nil
	}
	return snap
}

// openBrowser 尽力打开默认浏览器，失败不影响服务。
func openBrowser(url string) {
	var cmd *exec.Cmd
	switch strings.ToLower(filepath.Ext(os.Args[0])) {
	case ".exe":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	if err := cmd.Start(); err != nil {
		// 打不开就算了：URL 已经打印出来，用户自己点。
		return
	}
	go cmd.Wait()
}
