package app

import (
	"fmt"
	"io"
	"sort"
	"strings"

	"github.com/spf13/cobra"
)

// designatorEntry is one placed reference in the project-wide audit.
type designatorEntry struct {
	Page       string
	Designator string
}

// designatorDuplicates returns the references that appear on more than one page.
// EasyEDA designators are PROJECT-scoped: duplicates across pages make the
// platform silently renumber one of them on save/reload (observed R6→R12,
// R8→R13), after which connect-by-designator and the BOM rows point at the
// wrong part with no error anywhere.
func designatorDuplicates(entries []designatorEntry) map[string][]string {
	seen := map[string][]string{}
	for _, e := range entries {
		d := strings.TrimSpace(e.Designator)
		if d == "" {
			continue
		}
		seen[d] = append(seen[d], e.Page)
	}
	out := map[string][]string{}
	for d, pages := range seen {
		if len(pages) > 1 {
			sort.Strings(pages)
			out[d] = pages
		}
	}
	return out
}

// newSchDesignatorAuditCmd reports cross-page duplicate references.
func newSchDesignatorAuditCmd(cfg *appConfig, window *string, stdout, stderr io.Writer) *cobra.Command {
	var asJSON bool
	cmd := &cobra.Command{
		Use:   "designator-audit",
		Short: "Report designators that appear on more than one page (they get silently renumbered)",
		Long: `Designators are project-scoped in EasyEDA. When the same reference exists on
two pages, saving or reloading renumbers one of them WITHOUT any error, and
every later connect-by-designator / BOM row then addresses the wrong part.

This audits the whole project in one shot and exits 1 when duplicates exist.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			res, err := requestAction(cfg, "schematic.components.list", *window, map[string]any{"allPages": true})
			if err != nil {
				return err
			}
			comps, err := parseLayoutComps(res.Result)
			if err != nil {
				return err
			}
			entries := make([]designatorEntry, 0, len(comps))
			for _, c := range comps {
				if strings.EqualFold(strings.TrimSpace(c.ComponentType), "part") == false {
					continue
				}
				page := c.ID
				if strings.TrimSpace(page) == "" {
					page = "?"
				}
				entries = append(entries, designatorEntry{Page: page, Designator: c.Designator})
			}
			dups := designatorDuplicates(entries)
			if asJSON {
				fmt.Fprintf(stdout, "{\"duplicates\":%d,\"pagesScanned\":%d}\n", len(dups), len(entries))
			}
			if len(dups) == 0 {
				fmt.Fprintf(stdout, "✓ designator-audit: %d placed parts, no cross-page duplicates\n", len(entries))
				return nil
			}
			names := make([]string, 0, len(dups))
			for d := range dups {
				names = append(names, d)
			}
			sort.Strings(names)
			for _, d := range names {
				fmt.Fprintf(stdout, "ERROR %s on primitives %s — rename one of them\n", d, strings.Join(dups[d], ", "))
			}
			return fmt.Errorf("%d designator(s) duplicated in the project", len(dups))
		},
	}
	cmd.Flags().BoolVar(&asJSON, "json", false, "emit a one-line JSON summary")
	return cmd
}
