package app

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// mkScript creates a fake bom-enrich.py at path (with parents) and returns path.
func mkScript(t *testing.T, path string) string {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("#!/usr/bin/env python3\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

// realInstallWins reports whether the resolver finds bom-enrich.py outside the
// directories a test planted. The ladder probes installed skills before the cwd
// rung, so on a developer machine that already has the skill, isolation of HOME
// cannot reach the fallback regardless of what the test sets up.
func realInstallWins(plantedRoots ...string) bool {
	got, err := resolveEnrichScript("")
	if err != nil {
		return false
	}
	for _, root := range plantedRoots {
		if root != "" && strings.HasPrefix(got, root) {
			return false
		}
	}
	return true
}

// isolate points HOME (→ the installed skill dirs) and cwd at empty temp dirs and
// clears the env override, so a probe only finds what a test plants. PATH is
// emptied too: a real bom-enrich.py on the developer's PATH must not leak in.
func isolate(t *testing.T) (home string) {
	t.Helper()
	home = t.TempDir()
	t.Setenv("HOME", home)
	// Windows resolves the user home from USERPROFILE, not HOME; without this
	// the probe finds the developer's real ~/.claude/skills and the test measures
	// the host instead of the fixture.
	t.Setenv("USERPROFILE", home)
	// CLAUDE_CONFIG_DIR / CODEX_HOME override the client home outright
	// (see selfupdate.skillDir). Leaving them set is what made this test
	// *skip on developer machines and fail on CI*: here the probe found a real
	// install elsewhere and skipped; there the assertions actually ran. A test
	// whose verdict depends on the host is not a test.
	t.Setenv("CLAUDE_CONFIG_DIR", "")
	t.Setenv("CODEX_HOME", "")
	t.Setenv("EASYCIRQ_SKILLS_DIR", "")
	t.Setenv("PATH", "")
	t.Chdir(t.TempDir())
	return home
}

// TestResolveEnrichScriptPriority walks the probe ladder (issue #115): each rung
// wins while it exists, and removing it falls through to the next.
func TestResolveEnrichScriptPriority(t *testing.T) {
	home := isolate(t)

	skillsRoot := t.TempDir()
	envScript := mkScript(t, filepath.Join(skillsRoot, "easycirq-agent", "scripts", "bom-enrich.py"))
	// 必须种在**当前技能名**下面：rung 3 用的是 selfupdate.SkillName（"easycirq"），
	// 它把 rel 的第一段剥掉再拼到 …/skills/easycirq 上。原来这里种的是旧名
	// design-hardware，rung 3 永远找不到 —— 于是 case 3 在 CI 上一直是红的，
	// 而在开发者机器上被 realInstallWins 跳过掩盖（walkUp 从临时构建目录往上爬，
	// 第 6 层正好是真实用户目录）。旧名的覆盖在 TestResolveEnrichScriptPreMergeSkillName。
	installed := mkScript(t, filepath.Join(home, ".claude", "skills", "easycirq", "scripts", "bom-enrich.py"))

	// cwd rung: a repo-shaped tree, with cwd a few levels down.
	repo := t.TempDir()
	cwdScript := mkScript(t, filepath.Join(repo, ".agents", "skills", "easycirq", "scripts", "bom-enrich.py"))
	deep := filepath.Join(repo, "a", "b")
	if err := os.MkdirAll(deep, 0o755); err != nil {
		t.Fatal(err)
	}

	explicit := mkScript(t, filepath.Join(t.TempDir(), "custom-enrich.py"))

	t.Run("1 explicit --script wins over everything", func(t *testing.T) {
		t.Setenv("EASYCIRQ_SKILLS_DIR", skillsRoot)
		got, err := resolveEnrichScript(explicit)
		if err != nil || got != explicit {
			t.Fatalf("got %q, %v; want %q", got, err, explicit)
		}
	})

	t.Run("1b explicit --script that does not exist is a hard error", func(t *testing.T) {
		t.Setenv("EASYCIRQ_SKILLS_DIR", skillsRoot) // a valid fallback exists…
		missing := filepath.Join(t.TempDir(), "typo.py")
		got, err := resolveEnrichScript(missing)
		if err == nil {
			t.Fatalf("a --script typo must not silently fall through (got %q)", got)
		}
		if !strings.Contains(err.Error(), missing) {
			t.Errorf("error must name the bad path: %v", err)
		}
	})

	t.Run("2 EASYCIRQ_SKILLS_DIR beats the installed skill dir", func(t *testing.T) {
		t.Setenv("EASYCIRQ_SKILLS_DIR", skillsRoot)
		got, err := resolveEnrichScript("")
		if err != nil || got != envScript {
			t.Fatalf("got %q, %v; want %q", got, err, envScript)
		}
	})

	t.Run("3 installed skill dir is found from an unrelated cwd (#115)", func(t *testing.T) {
		if realInstallWins(home) {
			t.Skip("a real skill install outside the fixture wins on this host")
		}
		got, err := resolveEnrichScript("")
		if err != nil || got != installed {
			t.Fatalf("got %q, %v; want %q", got, err, installed)
		}
	})

	t.Run("5 cwd walk-up when no skill is installed", func(t *testing.T) {
		// 跳过判定必须在**同一个状态**下做：上面 case 3 往 home/.claude 里种了
		// 一个安装，所以此刻 realInstallWins 看到的是 case 3 的产物，不是这条
		// 要测的"没有安装"。先删掉，再判断——顺序错了这条就会误判。
		if err := os.RemoveAll(filepath.Join(home, ".claude")); err != nil {
			t.Fatal(err)
		}
		if realInstallWins(repo, home) {
			// 走到这里说明"从测试二进制往上爬"找到了夹具之外的安装。
			// 那是测试进程的构建目录决定的（Windows 上 go-build 目录在
			// %TEMP% 下，往上第 6 层常常就是真实用户目录），测试改不了。
			// CI 上爬不到东西，这条会真的断言。
			t.Skip("a real skill install wins before the cwd rung on this host")
		}
		t.Chdir(deep)
		got, err := resolveEnrichScript("")
		if err != nil || got != cwdScript {
			t.Fatalf("got %q, %v; want %q", got, err, cwdScript)
		}
	})
}

// TestResolveEnrichScriptPreMergeSkillName: an old easycirq-schematic install
// still resolves (the pre-merge skill name).
func TestResolveEnrichScriptPreMergeSkillName(t *testing.T) {
	isolate(t)
	root := t.TempDir()
	want := mkScript(t, filepath.Join(root, "easycirq-schematic", "scripts", "bom-enrich.py"))
	t.Setenv("EASYCIRQ_SKILLS_DIR", root)
	got, err := resolveEnrichScript("")
	if err != nil || got != want {
		t.Fatalf("got %q, %v; want %q", got, err, want)
	}
}

// TestResolveEnrichScriptNotFoundListsProbedPaths: the failure must be
// actionable — every probed path plus the --script hint (issue #115).
func TestResolveEnrichScriptNotFoundListsProbedPaths(t *testing.T) {
	home := isolate(t)
	root := t.TempDir()
	t.Setenv("EASYCIRQ_SKILLS_DIR", root)
	if realInstallWins(root, home) {
		t.Skip("a real skill install is present, so the probe always succeeds here")
	}

	_, err := resolveEnrichScript("")
	if err == nil {
		t.Fatal("want an error when no copy of the script exists")
	}
	msg := err.Error()
	for _, want := range []string{
		filepath.Join(root, "easycirq-agent", "scripts", "bom-enrich.py"),                      // env rung
		filepath.Join(home, ".claude", "skills", "easycirq", "scripts", "bom-enrich.py"), // installed rung
		filepath.Join(home, ".codex", "skills", "easycirq", "scripts", "bom-enrich.py"),
		"$PATH/bom-enrich.py",
		"--script",
		"EASYCIRQ_SKILLS_DIR",
	} {
		if !strings.Contains(msg, want) {
			t.Errorf("error must mention %q; got:\n%s", want, msg)
		}
	}
	// The cwd rung must appear too (the dir the CLI was actually run from).
	cwd, _ := os.Getwd()
	if !strings.Contains(msg, filepath.Join(cwd, ".agents", "skills")) {
		t.Errorf("error must list the cwd probe %q; got:\n%s", filepath.Join(cwd, ".agents", "skills"), msg)
	}
}
