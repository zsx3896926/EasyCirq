package app

import (
	"runtime"
	"strings"
	"testing"
)

// skipWithoutSymlinkPrivilege turns the Windows "client does not hold the
// required privilege" error into a skip: creating a symlink needs elevation or
// Developer Mode there, and that is an environment limit, not a code defect.
// Any other error still fails the test.
func skipWithoutSymlinkPrivilege(t *testing.T, err error) {
	t.Helper()
	if runtime.GOOS == "windows" && strings.Contains(err.Error(), "privilege") {
		t.Skipf("cannot create symlinks on this host: %v", err)
	}
	t.Fatal(err)
}
