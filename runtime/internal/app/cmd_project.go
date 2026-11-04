package app

import (
	"fmt"
	"io"
	"time"

	"github.com/spf13/cobra"
)

// newProjectCmd returns the "project" subcommand group.
func newProjectCmd(cfg *appConfig, stdout, stderr io.Writer) *cobra.Command {
	var window string

	proj := &cobra.Command{
		Use:   "project",
		Short: "Read EasyEDA project and document context",
	}
	proj.PersistentFlags().StringVar(&window, "window", "", "EasyEDA window ID")
	proj.AddCommand(newProjectExportSourceCmd(cfg, stdout, stderr, &window))
	proj.AddCommand(newProjectDrawingsCmd(stdout))

	proj.AddCommand(
		func() *cobra.Command {
			var friendlyName, teamUUID string
			var timeout time.Duration
			c := &cobra.Command{
				Use:     "find",
				Short:   "Find projects by exact friendly name without opening them",
				Long:    "Read official project UUIDs and project info. With --team, the API inventories that team's root folder only. An empty or incomplete enumeration reports unknown, not absent; absence is only established within a complete team-root inventory.",
				Args:    cobra.NoArgs,
				Example: `  easycirq project find --window <window-id> --name "AT32F415 demo" --team <team-uuid>`,
				RunE: func(cmd *cobra.Command, args []string) error {
					if friendlyName == "" {
						return fmt.Errorf("--name is required")
					}
					if timeout < 5*time.Second || timeout > 10*time.Minute {
						return fmt.Errorf("--timeout must be between 5s and 10m")
					}
					payload := map[string]any{"friendlyName": friendlyName}
					if teamUUID != "" {
						payload["teamUuid"] = teamUUID
					}
					return dispatchTimed(cfg, "project.find", window, payload, timeout, stdout, stderr)
				},
			}
			c.Flags().StringVar(&friendlyName, "name", "", "exact project friendly name (required)")
			c.Flags().StringVar(&teamUUID, "team", "", "exact owning team UUID; scopes inventory to its root folder")
			// The official inventory needs one detail read per UUID. A real 52-project
			// team takes ~19s, exceeding the common 20s budget minus daemon grace.
			c.Flags().DurationVar(&timeout, "timeout", 90*time.Second, "total lookup wait budget (5s to 10m); incomplete inventory never proves absence")
			return c
		}(),
		func() *cobra.Command {
			var friendlyName, projectName, teamUUID, folderUUID, description string
			var open bool
			c := &cobra.Command{
				Use:     "create",
				Short:   "Create an EasyEDA project container through the official API",
				Args:    cobra.NoArgs,
				Example: `  easycirq project create --name "AT32F415 demo" --open`,
				RunE: func(cmd *cobra.Command, args []string) error {
					if friendlyName == "" {
						return fmt.Errorf("--name is required")
					}
					payload := map[string]any{"friendlyName": friendlyName, "open": open}
					if projectName != "" {
						payload["projectName"] = projectName
					}
					if teamUUID != "" {
						payload["teamUuid"] = teamUUID
					}
					if folderUUID != "" {
						payload["folderUuid"] = folderUUID
					}
					if description != "" {
						payload["description"] = description
					}
					// 用 capture 而不是 dispatch：`--open` 之后还要把第一页激活，
					// 只建工程容器是不够的（页面默认 hidden，后续读写全部失败）。
					res, err := requestActionTimed(cfg, "project.create", window,
						payload, defaultActionTimeout)
					if err != nil || res == nil || !res.OK {
						if res == nil {
							return err
						}
						return encodeResultEnvelope(res, res.Result, stdout)
					}
					report := map[string]any{}
					for k, v := range res.Result {
						report[k] = v
					}
					if open {
						report["pageActivated"] = activateFirstPage(cfg, window)
					}
					return encodeResultEnvelope(res, report, stdout)
				},
			}
			c.Flags().StringVar(&friendlyName, "name", "", "project display name (required)")
			c.Flags().StringVar(&projectName, "internal-name", "", "optional internal project name")
			c.Flags().StringVar(&teamUUID, "team", "", "target team/workspace UUID")
			c.Flags().StringVar(&folderUUID, "folder", "", "target folder UUID")
			c.Flags().StringVar(&description, "description", "", "project description")
			c.Flags().BoolVar(&open, "open", false, "open the newly created project")
			return c
		}(),

		// project info → project.current
		&cobra.Command{
			Use:   "info",
			Short: "Read current EasyEDA project information",
			Args:  cobra.NoArgs,
			RunE: func(cmd *cobra.Command, args []string) error {
				return dispatch(cfg, "project.current", window, nil, stdout, stderr)
			},
		},

		// project doc → document.current
		&cobra.Command{
			Use:   "doc",
			Short: "Read active editor document and schematic page context",
			Args:  cobra.NoArgs,
			RunE: func(cmd *cobra.Command, args []string) error {
				return dispatch(cfg, "document.current", window, nil, stdout, stderr)
			},
		},

		// project open --uuid <uuid> → document.open
		func() *cobra.Command {
			var uuid, projectUUID, pageUUID string
			var discard bool
			c := &cobra.Command{
				Use:     "open",
				Short:   "Open a project by --project-uuid, or a legacy document by --uuid",
				Args:    cobra.NoArgs,
				Example: `  easycirq project open --uuid 6b3a2f01-...`,
				RunE: func(cmd *cobra.Command, args []string) error {
					if projectUUID != "" {
						if uuid != "" {
							return fmt.Errorf("use only --project-uuid or --uuid")
						}
						if !discard {
							return fmt.Errorf("openProject can discard unsaved data; save all documents first, then explicitly pass --allow-discard-unsaved")
						}
						res, value, err := projectTransferRequest(cfg, window, "open", projectUUID, pageUUID)
						if err != nil {
							return err
						}
						return encodeResultEnvelope(res, value, stdout)
					}
					if pageUUID != "" {
						return fmt.Errorf("--page-uuid requires --project-uuid")
					}
					if uuid == "" {
						return fmt.Errorf("--project-uuid or legacy --uuid is required")
					}
					return dispatch(cfg, "document.open", window,
						map[string]any{"uuid": uuid}, stdout, stderr)
				},
			}
			c.Flags().StringVar(&uuid, "uuid", "", "legacy: document UUID within the current project")
			c.Flags().StringVar(&projectUUID, "project-uuid", "", "project UUID to open and verify")
			c.Flags().StringVar(&pageUUID, "page-uuid", "", "optional schematic page UUID; wait for its tree and verify active page")
			c.Flags().BoolVar(&discard, "allow-discard-unsaved", false, "acknowledge official API may discard unsaved data; save all documents first")
			return c
		}(),
	)

	proj.AddCommand(newProjectExportCmd(cfg, &window, stdout))
	proj.AddCommand(newProjectImportCmd(cfg, &window, stdout))
	return proj
}

// activateFirstPage 建完工程后把第一张原理图页激活。
//
// 为什么必须做：`project.create` 只创建工程容器，页面建出来是 **hidden** 的
// （pageVisibility=hidden），此时 `sch read` / `sch list` 一律失败，报
// 「获取所有器件失败」。用户看到的是"连不上"，实际只差这一步。
//
// 全链路实测（2026-11-04）：
//
//	project create --open        → ok:true, pageVisibility=hidden
//	sch read                     → ok:false 「获取所有器件失败」
//	sch open --page <uuid>       → ok:true,  pageVisibility=visible
//	sch read                     → ok:true,  netlistAvailable=true
//
// 失败不当作建工程失败：工程已经建好了，这里只报告"页面没能激活"及原因，
// 让调用方自己决定要不要再跑 `sch open --page`。
func activateFirstPage(cfg *appConfig, window string) map[string]any {
	out := map[string]any{"activated": false}

	// 页面是异步建出来的：工程刚创建时 pages.list 会返回空，一两秒后才有。
	// 所以有界重试，而不是查一次就判"没有页面"——那会让 `--open` 看起来
	// 不生效，用户又得手动 `sch open --page` 一遍。
	var raw []any
	var lastErr string
	for attempt := 0; attempt < 8; attempt++ {
		if attempt > 0 {
			time.Sleep(250 * time.Millisecond)
		}
		pagesRes, err := requestActionTimed(cfg, "schematic.pages.list", window,
			nil, 30*time.Second)
		if err != nil || pagesRes == nil || !pagesRes.OK {
			lastErr = "schematic.pages.list failed"
			continue
		}
		got, _ := pagesRes.Result["pages"].([]any)
		if len(got) > 0 {
			raw = got
			out["waitedMs"] = attempt * 250
			break
		}
	}
	if len(raw) == 0 {
		if lastErr != "" {
			out["reason"] = lastErr +
				"; run `easycirq sch open --page <uuid>` yourself"
		} else {
			out["reason"] = "the new project has no schematic page after ~2s; " +
				"run `easycirq sch open --page <uuid>` yourself"
		}
		return out
	}
	first, ok := raw[0].(map[string]any)
	if !ok {
		out["reason"] = "unexpected pages payload"
		return out
	}
	pageUUID, _ := first["uuid"].(string)
	if pageUUID == "" {
		out["reason"] = "first page has no uuid"
		return out
	}
	out["pageUuid"] = pageUUID
	if name, _ := first["name"].(string); name != "" {
		out["pageName"] = name
	}

	openRes, err := requestActionTimed(cfg, "schematic.page.open", window,
		map[string]any{"schematicPageUuid": pageUUID}, 60*time.Second)
	if err != nil || openRes == nil || !openRes.OK {
		out["reason"] = "schematic.page.open failed; run `easycirq sch open --page " +
			pageUUID + "` yourself"
		return out
	}
	out["activated"] = true
	if ctx := openRes.Context; ctx != nil && ctx.PageVisibility != "" {
		out["pageVisibility"] = ctx.PageVisibility
	}
	return out
}
