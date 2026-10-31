package app

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// Audit logs grow without bound: one day reached 2.2 GB, and five days sat at
// 5.33 GB with no rotation. The log is what makes "audit cost" possible, so it
// cannot simply be deleted - it needs a retention policy.
//
// Defaults chosen so a normal machine is safe without configuration:
//   --keep-days 14   delete whole day-files older than this
//   --max-total-gb 2 compress the oldest remaining files to .gz until under
//
// Everything is reported before it happens, and --dry-run shows the plan.

const (
	auditDefaultKeepDays = 14
	auditDefaultMaxGB    = 2.0
)

type auditFileInfo struct {
	Path    string
	Day     time.Time
	Size    int64
	IsZiped bool
}

func newAuditPruneCmd(stdout, stderr io.Writer) *cobra.Command {
	var dir string
	var keepDays int
	var maxGB float64
	var dryRun bool
	var asJSON bool

	cmd := &cobra.Command{
		Use:   "prune",
		Short: "Apply a retention policy to the audit log (delete old days, compress large files)",
		Long: `The audit log has no built-in rotation: one day can reach gigabytes. This
applies a policy instead of deleting by hand - which would destroy the evidence
'audit cost' and 'audit export' need.

Policy, in this order:
  1. day-files older than --keep-days are deleted
  2. if the remainder is still larger than --max-total-gb, the oldest files are
     gzip-compressed (lossless; tail/export still read them)

--dry-run prints exactly what would happen and touches nothing.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			root := dir
			if root == "" {
				root = defaultAuditDir()
			}
			plan, err := planAuditPrune(root, keepDays, maxGB)
			if err != nil {
				return err
			}
			if dryRun {
				printAuditPlan(stdout, plan, "计划")
				return nil
			}
			deleted, compressed, freed, err := applyAuditPlan(plan)
			if err != nil {
				return err
			}
			if asJSON {
				fmt.Fprintf(stdout,
					"{\"deleted\":%d,\"compressed\":%d,\"freedBytes\":%d,\"dryRun\":false}\n",
					deleted, compressed, freed)
				return nil
			}
			printAuditPlan(stdout, plan, "已执行")
			fmt.Fprintf(stdout, "\n共释放 %s\n", humanBytes(freed))
			return nil
		},
	}
	cmd.Flags().StringVar(&dir, "dir", "", "audit directory (default ~/.easycirq/audit)")
	cmd.Flags().IntVar(&keepDays, "keep-days", auditDefaultKeepDays, "delete day-files older than this many days")
	cmd.Flags().Float64Var(&maxGB, "max-total-gb", auditDefaultMaxGB, "compress oldest files until total is under this size")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "show the plan without touching files")
	cmd.Flags().BoolVar(&asJSON, "json", false, "print a JSON summary")
	return cmd
}

type auditPlan struct {
	Delete []auditFileInfo
	Zip    []auditFileInfo
	Keep   []auditFileInfo
	Total  int64
	Limit  int64
}

func planAuditPrune(root string, keepDays int, maxGB float64) (auditPlan, error) {
	var plan auditPlan
	entries, err := os.ReadDir(root)
	if err != nil {
		if os.IsNotExist(err) {
			return plan, nil
		}
		return plan, err
	}
	cutoff := time.Now().AddDate(0, 0, -keepDays)
	var files []auditFileInfo
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if !strings.HasSuffix(name, ".jsonl") && !strings.HasSuffix(name, ".jsonl.gz") {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		day := parseAuditDay(name)
		item := auditFileInfo{
			Path:    filepath.Join(root, name),
			Day:     day,
			Size:    info.Size(),
			IsZiped: strings.HasSuffix(name, ".gz"),
		}
		plan.Total += info.Size()
		files = append(files, item)
	}
	sort.Slice(files, func(i, j int) bool { return files[i].Day.Before(files[j].Day) })

	var remaining []auditFileInfo
	for _, file := range files {
		if !file.Day.IsZero() && file.Day.Before(cutoff) {
			plan.Delete = append(plan.Delete, file)
			plan.Total -= file.Size
			continue
		}
		remaining = append(remaining, file)
	}
	limit := int64(maxGB * 1024 * 1024 * 1024)
	plan.Limit = limit
	total := plan.Total
	for _, file := range remaining {
		if total <= limit {
			plan.Keep = append(plan.Keep, file)
			continue
		}
		if file.IsZiped {
			plan.Keep = append(plan.Keep, file)
			continue
		}
		if isActiveAuditDay(file.Day, time.Now()) {
			// The daemon is still appending to today's file. Compressing it either
			// fails (Windows file lock) or splits the day's history in two.
			plan.Keep = append(plan.Keep, file)
			continue
		}
		plan.Zip = append(plan.Zip, file)
		// assume ~8x for jsonl text; exact size is reported after compressing
		total -= file.Size - file.Size/8
	}
	// Total is what the directory will actually hold after the plan runs;
	// telling the customer "5.3 GB" while compressing 5.3 GB would be misleading.
	plan.Total = total
	return plan, nil
}


// isActiveAuditDay reports whether a day-file may still receive writes. A
// day-based name means "today" is the active one; yesterday and older are
// finished by definition.
func isActiveAuditDay(day, now time.Time) bool {
	if day.IsZero() {
		return true // no date in the name: assume live rather than risk it
	}
	y1, m1, d1 := day.Date()
	y2, m2, d2 := now.Date()
	return y1 == y2 && m1 == m2 && d1 == d2
}

func applyAuditPlan(plan auditPlan) (deleted, compressed int, freed int64, err error) {
	for _, file := range plan.Delete {
		if removeErr := os.Remove(file.Path); removeErr != nil {
			return deleted, compressed, freed, removeErr
		}
		deleted++
		freed += file.Size
	}
	for _, file := range plan.Zip {
		before := file.Size
		if zipErr := gzipFile(file.Path); zipErr != nil {
			return deleted, compressed, freed, zipErr
		}
		if info, statErr := os.Stat(file.Path + ".gz"); statErr == nil {
			freed += before - info.Size()
		}
		compressed++
	}
	return deleted, compressed, freed, nil
}

func printAuditPlan(out io.Writer, plan auditPlan, title string) {
	fmt.Fprintf(out, "审计日志保留策略 — %s\n\n", title)
	if len(plan.Delete) == 0 && len(plan.Zip) == 0 {
		// If the total is still over the limit, saying only "nothing to do" is
		// confusing: the customer set a ceiling and it is not being met. Explain
		// that the remaining bulk is the active day, which becomes eligible
		// tomorrow.
		fmt.Fprintf(out, "  无需处理，共 %s\n", humanBytes(plan.Total))
		if plan.Total > plan.Limit && plan.Limit > 0 {
			fmt.Fprintf(out,
				"\n  当前已超过上限（%s），但剩下的都是今天正在写入的文件；\n"+
					"  明天它成为历史日后会被自动压缩。\n",
				humanBytes(plan.Limit))
		}
		return
	}
	if len(plan.Delete) > 0 {
		fmt.Fprintf(out, "  删除 %d 个过期文件：\n", len(plan.Delete))
		for _, file := range plan.Delete {
			fmt.Fprintf(out, "    %s  %s  %s\n",
				filepath.Base(file.Path), file.Day.Format("2006-01-02"), humanBytes(file.Size))
		}
	}
	if len(plan.Zip) > 0 {
		fmt.Fprintf(out, "  压缩 %d 个最大文件：\n", len(plan.Zip))
		for _, file := range plan.Zip {
			fmt.Fprintf(out, "    %s  %s\n", filepath.Base(file.Path), humanBytes(file.Size))
		}
	}
	kept := len(plan.Keep) + len(plan.Zip)
	fmt.Fprintf(out, "\n  保留 %d 个文件（其中 %d 个压缩保存），%s\n",
		kept, len(plan.Zip), humanBytes(plan.Total))
}

func parseAuditDay(name string) time.Time {
	base := strings.TrimSuffix(strings.TrimSuffix(name, ".gz"), ".jsonl")
	day, err := time.Parse("2006-01-02", base)
	if err != nil {
		return time.Time{}
	}
	return day
}

func humanBytes(n int64) string {
	const unit = 1024
	if n < unit {
		return fmt.Sprintf("%d B", n)
	}
	div, exp := int64(unit), 0
	for value := n / unit; value >= unit && exp < 4; value /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(n)/float64(div), "KMGTP"[exp])
}
