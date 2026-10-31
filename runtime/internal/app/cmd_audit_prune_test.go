package app

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func writeAuditDay(t *testing.T, dir string, day time.Time, size int) string {
	t.Helper()
	path := filepath.Join(dir, day.Format("2006-01-02")+".jsonl")
	payload := bytes.Repeat([]byte("x"), size)
	if err := os.WriteFile(path, payload, 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
	return path
}

func TestAuditPruneDeletesDaysOlderThanTheWindow(t *testing.T) {
	dir := t.TempDir()
	now := time.Now()
	old := writeAuditDay(t, dir, now.AddDate(0, 0, -30), 1024)
	fresh := writeAuditDay(t, dir, now, 1024)

	plan, err := planAuditPrune(dir, 14, 100)
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	if len(plan.Delete) != 1 || filepath.Base(plan.Delete[0].Path) != filepath.Base(old) {
		t.Fatalf("expected the old file in the delete set: %+v", plan.Delete)
	}

	var out bytes.Buffer
	if _, _, _, err := applyAuditPlan(plan); err != nil {
		t.Fatalf("apply: %v", err)
	}
	if _, err := os.Stat(old); !os.IsNotExist(err) {
		t.Fatalf("old file should be gone")
	}
	printAuditPlan(&out, plan, "已执行")
	if _, err := os.Stat(fresh); err != nil {
		t.Fatalf("fresh file must survive: %v", err)
	}
}

func TestAuditPruneCompressesInsteadOfDeletingWhenTooBig(t *testing.T) {
	dir := t.TempDir()
	now := time.Now()
	// two files inside the retention window, together over the limit
	writeAuditDay(t, dir, now.AddDate(0, 0, -2), 400*1024)
	newer := writeAuditDay(t, dir, now.AddDate(0, 0, -1), 400*1024)

	plan, err := planAuditPrune(dir, 14, 0.0005) // ~0.5 MB
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	if len(plan.Delete) != 0 {
		t.Fatalf("nothing should be deleted inside the window: %+v", plan.Delete)
	}
	if len(plan.Zip) == 0 {
		t.Fatalf("expected compression: %+v", plan)
	}
	if _, _, _, err := applyAuditPlan(plan); err != nil {
		t.Fatalf("apply: %v", err)
	}
	if _, err := os.Stat(newer); err != nil {
		t.Fatalf("the newest file must never be touched: %v", err)
	}
}

func TestAuditPruneDryRunTouchesNothing(t *testing.T) {
	dir := t.TempDir()
	old := writeAuditDay(t, dir, time.Now().AddDate(0, 0, -40), 512)
	plan, err := planAuditPrune(dir, 7, 100)
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	var out bytes.Buffer
	printAuditPlan(&out, plan, "计划")
	if !strings.Contains(out.String(), "计划") {
		t.Fatalf("dry run output should say it is a plan:\n%s", out.String())
	}
	if _, err := os.Stat(old); err != nil {
		t.Fatalf("dry run must not delete: %v", err)
	}
}

func TestAuditPruneReportsTheSizeAfterNotBefore(t *testing.T) {
	dir := t.TempDir()
	writeAuditDay(t, dir, time.Now(), 8*1024*1024)
	plan, err := planAuditPrune(dir, 14, 0.001) // 1 MB
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	var out bytes.Buffer
	printAuditPlan(&out, plan, "计划")
	// The per-file line shows the size before compressing (that is what gets
	// compressed); the summary must show the size AFTER.
	if !strings.Contains(out.String(), "压缩保存") {
		t.Fatalf("should say files are kept compressed:\n%s", out.String())
	}
	if !strings.Contains(out.String(), "保留 1 个文件") {
		t.Fatalf("summary missing:\n%s", out.String())
	}
	if !strings.Contains(out.String(), "1.0 MB") {
		t.Fatalf("summary should report the post-compress estimate (1.0 MB):\n%s", out.String())
	}
}

func TestAuditPruneOnMissingDirectoryIsHarmless(t *testing.T) {
	plan, err := planAuditPrune(filepath.Join(t.TempDir(), "nope"), 14, 2)
	if err != nil {
		t.Fatalf("missing dir should not error: %v", err)
	}
	if len(plan.Delete) != 0 || len(plan.Zip) != 0 {
		t.Fatalf("nothing to do: %+v", plan)
	}
}

func TestAuditPruneIgnoresUnrelatedFiles(t *testing.T) {
	dir := t.TempDir()
	keep := filepath.Join(dir, "notes.txt")
	if err := os.WriteFile(keep, []byte("keep me"), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	plan, err := planAuditPrune(dir, 0, 0)
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	for _, item := range plan.Delete {
		if filepath.Base(item.Path) == "notes.txt" {
			t.Fatalf("must not touch non-audit files")
		}
	}
	if _, err := os.Stat(keep); err != nil {
		t.Fatalf("unrelated file must survive: %v", err)
	}
}
