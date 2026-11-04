package app

// cmd_diag.go — 一键诊断包。
//
// 目标是**用户不用被教**：出了问题点一下，得到一个文件，发给支持就能定位。
//
// 这个命令的设计原则是「默认不含」，不是「默认全含再删」：
//
//   · 环境变量走**白名单**，不 dump 全部再过滤 —— 过滤表永远会漏掉新加的变量
//   · 网表、原理图、BOM 内容**根本不读** —— 它们是客户的商业数据
//   · 只收"描述状态"的东西：版本、doctor 结论、相位证据（只有状态与指纹）
//
// 诊断包里有什么、没有什么，写在包内的 README.txt 里 —— 用户可以自己核对，
// 而不是相信我们。

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/zsx3896926/EasyCirq/runtime/internal/version"
)

// diagEnvAllowlist 是**唯一**会被收集的环境变量集合。
//
// 加变量前先问：这个值会不会泄漏客户的设计或凭据？会，就不要加。
// 密钥类变量一律不进这个表 —— 不是靠"之后删掉"，是根本不读。
var diagEnvAllowlist = []string{
	"EASYCIRQ_SKILLS_DIR", // 技能目录路径（不敏感，排查加载问题必需）
	"EASYCIRQ_PHASE_DIR",  // 相位证据目录
	"OS", "ARCH",          // 由 runtime 提供，这里仅作说明
	"LANG", "LC_ALL", // 编码问题排查
	"PYTHONIOENCODING",
}

func newDiagCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var out string
	cmd := &cobra.Command{
		Use:   "diag",
		Short: "导出一个诊断包，发给支持就能定位问题（不含设计数据）",
		Long: "把排查问题需要的东西打成一个 zip：版本、doctor 结论、相位证据状态、\n" +
			"少量环境变量。\n\n" +
			"**不含**：网表、原理图、BOM 内容、任何密钥。包内 README.txt 会列清楚\n" +
			"收了什么、没收录什么，你可以自己核对。\n\n" +
			"  easycirq diag\n" +
			"  easycirq diag --out D:\\tmp\\easycirq-diag.zip",
		RunE: func(_ *cobra.Command, _ []string) error {
			path, err := writeDiagBundle(cfg, out)
			if err != nil {
				return err
			}
			fmt.Fprintf(stdout, "诊断包已生成：%s\n", path)
			fmt.Fprintf(stdout, "里面没有你的设计数据（网表/原理图/BOM 都没收），可以放心发出去。\n")
			return nil
		},
	}
	cmd.Flags().StringVar(&out, "out", "", "输出路径（默认放到临时目录）")
	return cmd
}

func writeDiagBundle(cfg *appConfig, out string) (string, error) {
	if out == "" {
		out = filepath.Join(os.TempDir(),
			fmt.Sprintf("easycirq-diag-%s.zip", time.Now().Format("20060102-150405")))
	}
	if err := os.MkdirAll(filepath.Dir(out), 0o755); err != nil {
		return "", err
	}
	f, err := os.Create(out)
	if err != nil {
		return "", err
	}
	defer f.Close()

	zw := zip.NewWriter(f)
	add := func(name string, data []byte) error {
		w, err := zw.Create(name)
		if err != nil {
			return err
		}
		_, err = w.Write(data)
		return err
	}

	// 1. 清单：能自证这个包是从哪来的
	manifest := map[string]any{
		"schema":      "easycirq-diag/v1",
		"version":     version.Version,
		"connector":   version.ConnectorVersion,
		"goVersion":   runtime.Version(),
		"os":          runtime.GOOS,
		"arch":        runtime.GOARCH,
		"generatedAt": time.Now().UTC().Format(time.RFC3339),
		"included": []string{
			"manifest.json", "README.txt", "doctor.txt", "phase.json", "env.json",
		},
		"excluded": []string{
			"netlist（网表内容）", "schematic（原理图/BOM 内容）",
			"credentials（密钥/令牌）", "logs with design data",
		},
	}
	b, _ := json.MarshalIndent(manifest, "", "  ")
	if err := add("manifest.json", b); err != nil {
		return "", err
	}

	// 2. README：用户能自己核对，而不是相信我们
	readme := `EasyCirq 诊断包

这个包里**只有排查问题需要的东西**，没有你的设计数据。

收录了：
  manifest.json   版本、平台、生成时间
  doctor.txt      easycirq doctor 的输出（连接器/daemon/Python 状态）
  phase.json      各相位的证据**状态**（pass/fail/blocked 之类）与板子指纹
  env.json        少量环境变量（目录、编码），**不含任何密钥**
  README.txt      本文件

没有收录（也不需要你提供）：
  · 网表内容
  · 原理图 / BOM 内容
  · 任何 API key、令牌、密码

如果你在这个包里发现了不该出现的东西，那是我们的 bug，请告诉我们。
`
	if err := add("README.txt", []byte(readme)); err != nil {
		return "", err
	}

	// 3. doctor 输出：调自己，拿结论不拿过程
	doctorOut := func() string {
		self, err := os.Executable()
		if err != nil {
			return "（拿不到可执行文件路径）"
		}
		cmd := exec.Command(self, "doctor")
		cmd.Stderr = io.Discard
		out, _ := cmd.Output() // 非零退出也可能有有用输出，照样收
		return string(out)
	}()
	if err := add("doctor.txt", []byte(doctorOut)); err != nil {
		return "", err
	}

	// 4. 相位证据：**只有状态与指纹**，不含板子内容
	phase := collectPhaseStates()
	b, _ = json.MarshalIndent(phase, "", "  ")
	if err := add("phase.json", b); err != nil {
		return "", err
	}

	// 5. 环境变量：白名单，逐个取值
	env := map[string]string{
		"GOOS":   runtime.GOOS,
		"GOARCH": runtime.GOARCH,
	}
	for _, k := range diagEnvAllowlist {
		if v := os.Getenv(k); v != "" {
			env[k] = v
		}
	}
	b, _ = json.MarshalIndent(env, "", "  ")
	if err := add("env.json", b); err != nil {
		return "", err
	}

	if err := zw.Close(); err != nil {
		return "", err
	}
	return out, nil
}

// collectPhaseStates 只读证据文件里的**状态**。
//
// 证据文件本来就只有相位名 → 状态 → 指纹，没有板子内容；这里再过一道，
// 只挑出状态与指纹两个字段，防止将来证据文件里加了别的字段被无意带出去。
func collectPhaseStates() map[string]any {
	dir := os.Getenv("EASYCIRQ_PHASE_DIR")
	if dir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return map[string]any{"note": "拿不到证据目录"}
		}
		dir = filepath.Join(home, ".easycirq", "phase")
	}
	res := map[string]any{"dir": dir, "projects": map[string]any{}}
	entries, err := os.ReadDir(dir)
	if err != nil {
		res["note"] = "证据目录还不可读（可能还没跑过相位命令）"
		return res
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)

	projects := res["projects"].(map[string]any)
	for _, name := range names {
		raw, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			continue
		}
		var doc map[string]any
		if json.Unmarshal(raw, &doc) != nil {
			continue
		}
		// 白名单挑字段：只留状态机相关的东西。
		trimmed := map[string]any{}
		for _, k := range []string{"schema", "phase", "fingerprint"} {
			if v, ok := doc[k]; ok {
				trimmed[k] = v
			}
		}
		if ev, ok := doc["evidence"].(map[string]any); ok {
			states := map[string]any{}
			for phase, v := range ev {
				if m, ok := v.(map[string]any); ok {
					if verdict, ok := m["verdict"]; ok {
						states[phase] = verdict
					}
				} else {
					states[phase] = v
				}
			}
			trimmed["evidence"] = states
		}
		projects[strings.TrimSuffix(name, ".json")] = trimmed
	}
	return res
}
