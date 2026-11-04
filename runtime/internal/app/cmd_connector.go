package app

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/zsx3896926/EasyCirq/runtime/internal/version"
)

// The connector command group owns the in-EDA part of the toolchain from this
// repository's point of view: locating the .eext this build ships with, reading
// its manifest, and verifying that what is loaded in the EasyEDA window is the
// same build. Installing the extension itself is a deliberate human action in
// EasyEDA (Extensions → Import extension, then allow external interaction and
// restart); the CLI prints the exact steps instead of pretending it can do it.

type connectorManifest struct {
	Name        string `json:"name"`
	UUID        string `json:"uuid"`
	DisplayName string `json:"displayName"`
	Version     string `json:"version"`
	Publisher   string `json:"publisher"`
	EngineEDA   string `json:"enginesEda,omitempty"`
}

type connectorArtifact struct {
	Path     string             `json:"path"`
	Exists   bool               `json:"exists"`
	Size     int64              `json:"size,omitempty"`
	SHA256   string             `json:"sha256,omitempty"`
	Manifest *connectorManifest `json:"manifest,omitempty"`
	Source   string             `json:"source,omitempty"`
}

func newConnectorCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "connector",
		Short: "Locate, inspect and verify the EasyCirq connector .eext",
	}
	cmd.AddCommand(
		newConnectorPathCmd(stdout),
		newConnectorVerifyCmd(cfg, stdout, stderr),
		newConnectorInstallStepsCmd(stdout),
	)
	return cmd
}

func connectorSearchPaths() []string {
	var out []string
	if p := strings.TrimSpace(os.Getenv("EASYCIRQ_CONNECTOR_EEXT")); p != "" {
		out = append(out, p)
	}
	if exe, err := os.Executable(); err == nil {
		dir := filepath.Dir(exe)
		// Installed layout: <install>/bin/easycirq.exe + <install>/connector/*.eext
		out = append(out,
			filepath.Join(dir, "..", "connector"),
			filepath.Join(dir, "connector"),
		)
		// Development layout: <repo>/runtime/dist/easycirq.exe + <repo>/connector/build/dist
		out = append(out,
			filepath.Join(dir, "..", "..", "connector", "build", "dist"),
			filepath.Join(dir, "..", "..", "..", "connector", "build", "dist"),
		)
	}
	if dir := stateDir(); dir != "" {
		out = append(out, filepath.Join(dir, "connector"))
	}
	return out
}

// connectorEextVersion 从文件名里抠版本号（easycirq-connector_v1.0.21.eext）。
// 抠不到就返回空串——调用方会把它当作"最旧"，不参与择优。
func connectorEextVersion(path string) string {
	base := strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
	if i := strings.LastIndex(base, "_v"); i >= 0 {
		return base[i+2:]
	}
	return ""
}

// versionLess 比较点分版本号；无法解析的一律算"更旧"。
func versionLess(a, b string) bool {
	pa, pb := strings.Split(a, "."), strings.Split(b, ".")
	for i := 0; i < len(pa) || i < len(pb); i++ {
		var na, nb int
		if i < len(pa) {
			na, _ = strconv.Atoi(pa[i])
		}
		if i < len(pb) {
			nb, _ = strconv.Atoi(pb[i])
		}
		if na != nb {
			return na < nb
		}
	}
	return false
}

// findConnectorEext 返回可用的 .eext，**按版本号取最高的**。
//
// 原来是"取第一个含有 .eext 的目录"，而 connectorSearchPaths 把安装目录
// （<install>/connector）排在仓库构建目录（connector/build/dist）之前。
// 2026-11-02 实测后果：`easycirq connector path` 打印的是安装目录里 10-28 的
// v0.1.4（259KB），而仓库里 11-01 构建的 v1.0.20（2.2MB，含修复）排在后面被忽略。
// 用户按这个路径去导入，导进的是更旧的包 —— 命令把人指向了错误的东西。
//
// 现在把所有候选收齐，按版本号择优；版本相同再比修改时间。同为最高版本时
// 保持搜索顺序（安装目录优先），所以没冲突时行为不变。
func findConnectorEext() (string, string) {
	type candidate struct {
		path  string
		dir   string
		ver   string
		mtime int64
	}
	var all []candidate

	for _, dir := range connectorSearchPaths() {
		st, err := os.Stat(dir)
		if err != nil {
			continue
		}
		if !st.IsDir() {
			if strings.HasSuffix(strings.ToLower(dir), ".eext") {
				info, _ := st.ModTime().Unix(), 0
				_ = info
				return dir, "env"
			}
			continue
		}
		matches, _ := filepath.Glob(filepath.Join(dir, "*.eext"))
		for _, m := range matches {
			var mtime int64
			if fi, err := os.Stat(m); err == nil {
				mtime = fi.ModTime().Unix()
			}
			all = append(all, candidate{path: m, dir: dir,
				ver: connectorEextVersion(m), mtime: mtime})
		}
	}
	if len(all) == 0 {
		return "", ""
	}
	sort.SliceStable(all, func(i, j int) bool {
		if all[i].ver != all[j].ver {
			return versionLess(all[i].ver, all[j].ver)
		}
		return all[i].mtime < all[j].mtime
	})
	best := all[len(all)-1]
	return best.path, best.dir
}

func readConnectorManifest(path string) (*connectorManifest, error) {
	zr, err := zip.OpenReader(path)
	if err != nil {
		return nil, fmt.Errorf("不是有效的 .eext(zip) 包: %w", err)
	}
	defer zr.Close()
	for _, f := range zr.File {
		if f.Name != "extension.json" {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			return nil, err
		}
		defer rc.Close()
		var raw struct {
			Name        string         `json:"name"`
			UUID        string         `json:"uuid"`
			DisplayName string         `json:"displayName"`
			Version     string         `json:"version"`
			Publisher   string         `json:"publisher"`
			Engines     map[string]any `json:"engines"`
		}
		if err := json.NewDecoder(io.LimitReader(rc, 1<<20)).Decode(&raw); err != nil {
			return nil, fmt.Errorf("解析 extension.json: %w", err)
		}
		m := &connectorManifest{
			Name: raw.Name, UUID: raw.UUID, DisplayName: raw.DisplayName,
			Version: raw.Version, Publisher: raw.Publisher,
		}
		if v, ok := raw.Engines["eda"].(string); ok {
			m.EngineEDA = v
		}
		return m, nil
	}
	return nil, fmt.Errorf(".eext 内缺少 extension.json")
}

func newConnectorPathCmd(stdout io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "path",
		Short: "Print the connector .eext this runtime ships with",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			art := connectorArtifact{Source: "not-found"}
			if path, source := findConnectorEext(); path != "" {
				art.Path, art.Source = path, source
				if st, err := os.Stat(path); err == nil {
					art.Exists, art.Size = true, st.Size()
				}
				if data, err := os.ReadFile(path); err == nil {
					sum := sha256.Sum256(data)
					art.SHA256 = hex.EncodeToString(sum[:])
				}
				if m, err := readConnectorManifest(path); err == nil {
					art.Manifest = m
				}
			}
			enc := json.NewEncoder(stdout)
			enc.SetIndent("", "  ")
			return enc.Encode(art)
		},
	}
}

func newConnectorVerifyCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "verify",
		Short: "Verify the .eext build against this runtime and the loaded connector",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			report := map[string]any{
				"schema":          "easycirq-connector-verify/v1",
				"expectedName":    expectedConnectorName,
				"expectedVersion": expectedConnectorVersion,
				"runtimeVersion":  version.Version,
			}
			verdict := "ok"
			// 原来这里把 findConnectorEext 的第二个返回值丢掉，于是明明找到了
			// 文件，报告里仍写着 source: "not-found" —— 显示的结论和事实相反。
			path, source := findConnectorEext()
			art := connectorArtifact{Source: "not-found"}
			if path == "" {
				report["eext"] = art
				report["verdict"] = "blocked"
				report["reason"] = "没有找到与运行时配套的 .eext（构建包缺失或安装目录不完整）"
				enc := json.NewEncoder(stdout)
				enc.SetIndent("", "  ")
				_ = enc.Encode(report)
				fmt.Fprintln(stderr, "easycirq connector verify — blocked: .eext not found")
				return errActionFailed
			}
			art.Path, art.Source = path, source
			if st, err := os.Stat(path); err == nil {
				art.Exists, art.Size = true, st.Size()
			}
			if data, err := os.ReadFile(path); err == nil {
				sum := sha256.Sum256(data)
				art.SHA256 = hex.EncodeToString(sum[:])
			}
			if m, err := readConnectorManifest(path); err == nil {
				art.Manifest = m
				if m.Name != expectedConnectorName || m.Version != expectedConnectorVersion {
					verdict = "degraded"
				}
			} else {
				verdict = "blocked"
				report["manifestError"] = err.Error()
			}
			report["eext"] = art

			loaded := []string{}
			if portStart, portEnd, err := cfg.portRange(); err == nil {
				ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
				result := scanHealth(ctx, hostPortOptions{host: cfg.host, portStart: portStart, portEnd: portEnd})
				cancel()
				if result.Found != nil {
					var raw struct {
						Windows []doctorWindow `json:"windows"`
					}
					if err := json.Unmarshal(result.Found.Raw, &raw); err == nil {
						for _, w := range raw.Windows {
							loaded = append(loaded, fmt.Sprintf("%s=%s", shortID(w.WindowID), display(w.ConnectorVersion)))
							if w.ConnectorVersion != expectedConnectorVersion && verdict == "ok" {
								verdict = "degraded"
							}
						}
					}
				}
			}
			report["loadedWindows"] = loaded
			report["verdict"] = verdict
			if len(loaded) == 0 {
				report["reason"] = "没有连接器接入 daemon：要么尚未导入/启用扩展，要么 EasyEDA 未重启"
				if verdict == "ok" {
					verdict = "degraded"
					report["verdict"] = verdict
				}
			}
			enc := json.NewEncoder(stdout)
			enc.SetIndent("", "  ")
			if err := enc.Encode(report); err != nil {
				return err
			}
			fmt.Fprintf(stderr, "easycirq connector verify — %s (eext %s, loaded windows: %d)\n",
				verdict, path, len(loaded))
			if verdict == "blocked" {
				return errActionFailed
			}
			return nil
		},
	}
}

func newConnectorInstallStepsCmd(stdout io.Writer) *cobra.Command {
	return &cobra.Command{
		Use:   "install-steps",
		Short: "Print the exact manual steps to load the connector into EasyEDA Pro",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			path, _ := findConnectorEext()
			steps := []string{
				"1. 关闭所有 EasyEDA Pro 窗口（扩展在启动时加载，运行中导入不会生效）",
				"2. 打开 EasyEDA Pro → 「设置 / 扩展」→「导入扩展」，选择: " + path,
				"3. 打开扩展管理器 → 选中 " + expectedConnectorName + " → 允许「外部交互 / Allow external interaction」",
				"4. 重新启动 EasyEDA Pro，打开工程",
				"5. 回到命令行运行 `easycirq doctor`：connector 状态应为 connected，且 connectorVersion 为 " + expectedConnectorVersion,
				"注意：导入是 EDA 内的显式人工动作，本工具链不会、也不应该替你点击；导入后以真实握手而非磁盘文件判断安装成功。",
			}
			out := map[string]any{
				"schema":    "easycirq-connector-install-steps/v1",
				"eext":      path,
				"name":      expectedConnectorName,
				"version":   expectedConnectorVersion,
				"steps":     steps,
				"isolation": "自有扩展 uuid/名称/端口/配置项均与上游 easyeda-agent 连接器隔离，可并存，互不接管",
			}
			enc := json.NewEncoder(stdout)
			enc.SetIndent("", "  ")
			if err := enc.Encode(out); err != nil {
				return err
			}
			for _, s := range steps {
				fmt.Fprintln(os.Stderr, s)
			}
			return nil
		},
	}
}
