package app

import (
	"os"
	"path/filepath"
	"testing"
)

// The whole point of compressing old audit days is that they stay readable. If
// readAuditRows cannot open a .gz, prune silently destroys the evidence that
// audit cost and audit export depend on.
func TestReadAuditRowsReadsACompressedDay(t *testing.T) {
	dir := t.TempDir()
	plain := filepath.Join(dir, "2026-10-30.jsonl")
	body := `{"ts":"2026-10-30T01:00:00Z","requestId":"req_1","command":"easycirq status","action":"document.current","ok":true}`
	if err := os.WriteFile(plain, []byte(body+"\n"), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	if err := gzipFile(plain); err != nil {
		t.Fatalf("compress: %v", err)
	}
	if _, err := os.Stat(plain); !os.IsNotExist(err) {
		t.Fatalf("original should be gone after compressing")
	}
	rows, err := readAuditRows(plain)
	if err != nil {
		t.Fatalf("reading the compressed day failed: %v", err)
	}
	if len(rows) != 1 || rows[0].Action != "document.current" {
		t.Fatalf("compressed rows not read back: %+v", rows)
	}
}

func TestReadAuditRowsPrefersPlainThenFallsBack(t *testing.T) {
	dir := t.TempDir()
	plain := filepath.Join(dir, "2026-10-31.jsonl")
	if err := os.WriteFile(plain, []byte(`{"action":"plain"}`+"\n"), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	rows, err := readAuditRows(plain)
	if err != nil {
		t.Fatalf("plain read: %v", err)
	}
	if len(rows) != 1 || rows[0].Action != "plain" {
		t.Fatalf("plain file not preferred: %+v", rows)
	}

	gz := filepath.Join(dir, "2026-10-29.jsonl")
	if err := os.WriteFile(gz, []byte(`{"action":"zipped"}`+"\n"), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	if err := gzipFile(gz); err != nil {
		t.Fatalf("compress: %v", err)
	}
	rows, err = readAuditRows(gz)
	if err != nil {
		t.Fatalf("fallback read: %v", err)
	}
	if len(rows) != 1 || rows[0].Action != "zipped" {
		t.Fatalf("fallback did not read the gz: %+v", rows)
	}
}

