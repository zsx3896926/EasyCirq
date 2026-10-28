package app

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/zsx3896926/EasyCirq/runtime/internal/selfupdate"
)

// newTaskCmd returns the "task" group — scaffold an enforced schematic task.
func newTaskCmd(stdout, stderr io.Writer) *cobra.Command {
	t := &cobra.Command{
		Use:   "task",
		Short: "Scaffold an enforced schematic task (delivery gate + Claude Code Stop hook)",
	}
	t.AddCommand(newTaskNewCmd(stdout, stderr))
	return t
}

// taskSettings is the per-task Claude Code settings.json emitted by `task new`.
type taskSettings struct {
	Hooks map[string][]taskHookGroup `json:"hooks"`
}

type taskHookGroup struct {
	Hooks []taskHook `json:"hooks"`
}

type taskHook struct {
	Type    string `json:"type"`
	Command string `json:"command"`
}

func findSkillScripts() (string, error) {
	for _, target := range selfupdate.Targets(false) {
		if !target.Present {
			continue
		}
		scripts := filepath.Join(target.Dir, "scripts")
		if _, err := os.Stat(filepath.Join(scripts, "sch_delivery_hook.py")); err == nil {
			return scripts, nil
		}
	}
	return "", fmt.Errorf("no installed easycirq skill with sch_delivery_hook.py found (install the skill, or set --skill-scripts)")
}

func newTaskNewCmd(stdout, stderr io.Writer) *cobra.Command {
	var dir, prompt, client, permissionMode, python, skillScripts string
	var launch, requireVisual, requireStyle bool
	var maxTurns int

	c := &cobra.Command{
		Use:   "new",
		Short: "Create a task workspace wired with the schematic-delivery Stop hook",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			if client != "" && client != "claude" {
				return fmt.Errorf("the delivery Stop hook is currently Claude Code only; got client %q", client)
			}
			if launch && strings.TrimSpace(prompt) == "" {
				return fmt.Errorf("--launch requires --prompt")
			}

			if skillScripts == "" {
				ss, err := findSkillScripts()
				if err != nil {
					return err
				}
				skillScripts = ss
			}
			if python == "" {
				p, err := exec.LookPath("python")
				if err != nil {
					return fmt.Errorf("python not found on PATH: %w", err)
				}
				python = p
			}

			workdir := dir
			if workdir == "" {
				workdir = fmt.Sprintf("easycirq-task-%s", time.Now().Format("20060102-150405"))
			}
			absWorkdir, err := filepath.Abs(workdir)
			if err != nil {
				return err
			}
			if err := os.MkdirAll(absWorkdir, 0o755); err != nil {
				return err
			}

			evidence := filepath.Join(absWorkdir, "delivery.json")
			hookLog := filepath.Join(absWorkdir, "hook.log")
			hookPath := filepath.Join(skillScripts, "sch_delivery_hook.py")
			gatePath := filepath.Join(skillScripts, "sch_delivery_check.py")

			commandParts := []string{
				fmt.Sprintf(`"%s"`, python),
				fmt.Sprintf(`"%s"`, hookPath),
				"--evidence", fmt.Sprintf(`"%s"`, evidence),
				"--gate", fmt.Sprintf(`"%s"`, gatePath),
				"--frame-plan", fmt.Sprintf(`"%s"`, filepath.Join(absWorkdir, "frame-plan.json")),
				"--layout", fmt.Sprintf(`"%s"`, filepath.Join(absWorkdir, "layout.json")),
				"--text-audit", fmt.Sprintf(`"%s"`, filepath.Join(absWorkdir, "text-audit.json")),
				"--style", fmt.Sprintf(`"%s"`, filepath.Join(absWorkdir, "style-input.json")),
				"--log", fmt.Sprintf(`"%s"`, hookLog),
			}
			if requireStyle {
				commandParts = append(commandParts, "--require-style")
			}
			if requireVisual {
				commandParts = append(commandParts, "--require-visual")
			}
			command := strings.Join(commandParts, " ")
			settings := taskSettings{Hooks: map[string][]taskHookGroup{
				"Stop": {{Hooks: []taskHook{{Type: "command", Command: command}}}},
			}}
			settingsPath := filepath.Join(absWorkdir, "settings.json")
			blob, err := json.MarshalIndent(settings, "", "  ")
			if err != nil {
				return err
			}
			if err := os.WriteFile(settingsPath, append(blob, '\n'), 0o644); err != nil {
				return err
			}

			skillRoot := filepath.Dir(skillScripts)
			styleFlag := ""
			if requireStyle {
				styleFlag = " --style <style-input.json> --require-style"
			}
			visualFlag := ""
			if requireVisual {
				visualFlag = " --require-visual"
			}
			stylePlanPath := filepath.Join(absWorkdir, "style-plan.json")
			stylePlan := `{
  "schema": "easycirq-sch-style-plan/v1",
  "sheet": {"width_mm": 297, "height_mm": 210, "size": "A4"},
  "zones": [],
  "titleBlock": {"project": "", "version": "", "date": "", "sheet": "", "page": "", "size": "A4"}
}
`
			if err := os.WriteFile(stylePlanPath, []byte(stylePlan), 0o644); err != nil {
				return err
			}

			designPlanPath := filepath.Join(absWorkdir, "design-plan.md")
			designPlan := fmt.Sprintf(`# 设计时流程（先版式后器件，契约 R12）

## Stage 0 版式蓝图
编辑 %s：图纸模板、分区框（id/title/order/purpose/rect_mm/borderColor/titleSize）、标题栏。

## Stage 1 蓝图门禁（必须 PASS 才能继续）
    %s %s %s

## Stage 2 写分区框
按 style-plan.json 在 EDA 画 module frame（order/title/purpose）。

## Stage 3 器件落位
按分区放器件，吸附网格，行/列对齐。

## Stage 4 连线/标签
局部短线直连，跨区语义网络标签，GND/AGND 统一朝下。

## Stage 5 导出 + 风格审计
导出 SVG/PNG，并写 style-input.json 后运行：
    %s %s <style-input.json>

## Stage 6 完整交付门禁
    %s %s --frame-plan <frame-plan.json> --layout <layout.json> --text-audit <text-audit.json>%s%s --out %s
`, stylePlanPath,
				python, filepath.Join(skillScripts, "sch_style_plan_check.py"), stylePlanPath,
				python, filepath.Join(skillScripts, "sch_style_audit.py"),
				python, filepath.Join(skillScripts, "sch_delivery_check.py"),
				styleFlag, visualFlag, evidence)
			if err := os.WriteFile(designPlanPath, []byte(designPlan), 0o644); err != nil {
				return err
			}

			taskDoc := fmt.Sprintf(`# EasyCirq enforced schematic task

Reference look (open it before drawing):

    %s

Style rules:

    %s

Design-time flow (do Stage 0 first; do not write devices before the blueprint passes):

    %s

The Stop hook blocks this task from finishing until a PASS report exists at:

    %s

Final gate command:

    %s %s --frame-plan <frame-plan.json> --layout <layout.json> --text-audit <text-audit.json>%s%s --out %s

PASS is a structural + style acceptance (framed zones with order/purpose,
palette/typography, owned non-overlapping labels); it is not electrical,
visual or hardware proof.
`, filepath.Join(skillRoot, "assets", "style-reference", "esp32-schematic.png"),
				filepath.Join(skillRoot, "references", "schematic-style.md"),
				designPlanPath,
				evidence, python, filepath.Join(skillScripts, "sch_delivery_check.py"),
				styleFlag, visualFlag, evidence)
			if err := os.WriteFile(filepath.Join(absWorkdir, "task.md"), []byte(taskDoc), 0o644); err != nil {
				return err
			}

			fmt.Fprintf(stdout, "task dir   : %s\n", absWorkdir)
			fmt.Fprintf(stdout, "settings   : %s\n", settingsPath)
			fmt.Fprintf(stdout, "delivery   : %s\n", evidence)
			fmt.Fprintf(stdout, "hook       : %s\n", hookPath)
			if requireStyle {
				fmt.Fprintln(stdout, "style      : required (sch_style_audit.py; see task.md)")
			}
			fmt.Fprintf(stdout, "style plan : %s\n", stylePlanPath)
			fmt.Fprintf(stdout, "design flow: %s\n", designPlanPath)
			if requireVisual {
				fmt.Fprintln(stdout, "visual     : required (add --require-visual to the delivery check)")
			}

			if !launch {
				fmt.Fprintln(stdout, "next       : claude -p \"<your prompt>\" --settings \""+settingsPath+"\" --permission-mode "+permissionMode)
				return nil
			}

			claude, err := exec.LookPath("claude")
			if err != nil {
				return fmt.Errorf("claude not found on PATH: %w", err)
			}
			launchArgs := []string{"-p", prompt, "--settings", settingsPath,
				"--permission-mode", permissionMode, "--max-turns", fmt.Sprintf("%d", maxTurns)}
			child := exec.Command(claude, launchArgs...)
			child.Stdout = stdout
			child.Stderr = stderr
			child.Stdin = os.Stdin
			return child.Run()
		},
	}

	c.Flags().StringVar(&dir, "dir", "", "task workspace directory (default: ./easycirq-task-<timestamp>)")
	c.Flags().StringVar(&prompt, "prompt", "", "initial prompt; required with --launch")
	c.Flags().StringVar(&client, "client", "claude", "AI client (claude only for the Stop hook)")
	c.Flags().BoolVar(&launch, "launch", false, "launch Claude Code after scaffolding")
	c.Flags().IntVar(&maxTurns, "max-turns", 12, "turn cap when launching")
	c.Flags().StringVar(&permissionMode, "permission-mode", "plan", "Claude Code permission mode")
	c.Flags().BoolVar(&requireVisual, "require-visual", false, "record that SVG evidence is required")
	c.Flags().BoolVar(&requireStyle, "require-style", true, "require the style audit in the delivery command")
	c.Flags().StringVar(&python, "python", "", "python executable (default: python on PATH)")
	c.Flags().StringVar(&skillScripts, "skill-scripts", "", "explicit skill scripts directory (default: auto-detect)")
	return c
}
