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
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/zsx3896926/hardware-design-skill/runtime/internal/version"
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
		Short: "Locate, inspect and verify the Zhigou connector .eext",
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
	if p := strings.TrimSpace(os.Getenv("ZHIGOU_CONNECTOR_EEXT")); p != "" {
		out = append(out, p)
	}
	if exe, err := os.Executable(); err == nil {
		dir := filepath.Dir(exe)
		// Installed layout: <install>/bin/zhigou.exe + <install>/connector/*.eext
		out = append(out,
			filepath.Join(dir, "..", "connector"),
			filepath.Join(dir, "connector"),
		)
		// Development layout: <repo>/runtime/dist/zhigou.exe + <repo>/connector/build/dist
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

func findConnectorEext() (string, string) {
	for _, dir := range connectorSearchPaths() {
		st, err := os.Stat(dir)
		if err != nil {
			continue
		}
		if !st.IsDir() {
			if strings.HasSuffix(strings.ToLower(dir), ".eext") {
				return dir, "env"
			}
			continue
		}
		matches, _ := filepath.Glob(filepath.Join(dir, "*.eext"))
		if len(matches) > 0 {
			sort.Strings(matches)
			return matches[len(matches)-1], dir
		}
	}
	return "", ""
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
				"schema":          "zhigou-connector-verify/v1",
				"expectedName":    expectedConnectorName,
				"expectedVersion": expectedConnectorVersion,
				"runtimeVersion":  version.Version,
			}
			verdict := "ok"
			path, _ := findConnectorEext()
			art := connectorArtifact{Source: "not-found"}
			if path == "" {
				report["eext"] = art
				report["verdict"] = "blocked"
				report["reason"] = "没有找到与运行时配套的 .eext（构建包缺失或安装目录不完整）"
				enc := json.NewEncoder(stdout)
				enc.SetIndent("", "  ")
				_ = enc.Encode(report)
				fmt.Fprintln(stderr, "zhigou connector verify — blocked: .eext not found")
				return errActionFailed
			}
			art.Path = path
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
			fmt.Fprintf(stderr, "zhigou connector verify — %s (eext %s, loaded windows: %d)\n",
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
				"5. 回到命令行运行 `zhigou doctor`：connector 状态应为 connected，且 connectorVersion 为 " + expectedConnectorVersion,
				"注意：导入是 EDA 内的显式人工动作，本工具链不会、也不应该替你点击；导入后以真实握手而非磁盘文件判断安装成功。",
			}
			out := map[string]any{
				"schema":    "zhigou-connector-install-steps/v1",
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
