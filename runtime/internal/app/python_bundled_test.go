package app

// python_bundled_test.go — 自带解释器：交付要求「客户不用装 Python」。
//
// 守的是一条很具体的失败：装完之后核心功能全废，而安装器还说「装好了」。

import (
	"errors"
	"path/filepath"
	"strings"
	"testing"
)

// fakeExe 造一个解析器：exe 在 <root>/bin/easycirq.exe，给定哪些自带路径"存在"。
func fakeResolver(goos, root string, present map[string]bool,
	probeOK bool, env map[string]string) pythonResolver {
	exe := filepath.Join(root, "bin", "easycirq.exe")
	return pythonResolver{
		goos: goos,
		getenv: func(k string) string {
			if v, ok := env[k]; ok {
				return v
			}
			return ""
		},
		lookPath: func(f string) (string, error) {
			return "", errors.New("not on PATH")
		},
		probe: func(path string, args ...string) error {
			if probeOK {
				return nil
			}
			return errors.New("probe failed")
		},
		exePath: func() (string, error) { return exe, nil },
		exists:  func(p string) bool { return present[filepath.Clean(p)] },
	}
}

func bundledWinPath(root string) string {
	return filepath.Clean(filepath.Join(root, "bin", "..", "python", "python.exe"))
}

// 自带解释器存在时，它必须胜出 —— 即使 PATH 上一个都找不到。
func TestBundledInterpreterWinsOverAnEmptyPath(t *testing.T) {
	root := filepath.Join("C:", "inst")
	r := fakeResolver("windows", root, map[string]bool{bundledWinPath(root): true},
		true, nil)
	path, lead, err := r.resolve()
	if err != nil {
		t.Fatalf("自带解释器在却报找不到：%v", err)
	}
	if !strings.HasSuffix(path, "python.exe") || !strings.Contains(path, "python") {
		t.Errorf("解析到别的东西：%s", path)
	}
	if len(lead) != 0 {
		t.Errorf("自带解释器不该带前导参数：%v", lead)
	}
}

// 自带的不存在 -> 回落到 PATH 阶梯，行为与接入前一致。
func TestNoBundledFallsBackToThePathLadder(t *testing.T) {
	root := filepath.Join("C:", "inst")
	r := fakeResolver("windows", root, map[string]bool{}, true, nil)
	r.lookPath = func(f string) (string, error) {
		if f == "python" {
			return `C:\somewhere\python.exe`, nil
		}
		return "", errors.New("no")
	}
	path, _, err := r.resolve()
	if err != nil {
		t.Fatalf("回落失败：%v", err)
	}
	if path != `C:\somewhere\python.exe` {
		t.Errorf("回落到 %s", path)
	}
}

// 自带的存在但跑不起来（损坏、架构不对）-> 必须继续往下找，不许直接报死。
func TestBrokenBundledInterpreterFallsThrough(t *testing.T) {
	root := filepath.Join("C:", "inst")
	// probe 只对"自带那一个"失败：坏掉的自带解释器必须让位给 PATH，
	// 而不是把整条阶梯堵死。
	r := fakeResolver("windows", root, map[string]bool{bundledWinPath(root): true},
		true, nil)
	r.probe = func(path string, args ...string) error {
		if strings.Contains(path, filepath.Join("python", "python.exe")) {
			return errors.New("probe failed")
		}
		return nil
	}
	r.lookPath = func(f string) (string, error) {
		if f == "python3" {
			return `C:\other\python3.exe`, nil
		}
		return "", errors.New("no")
	}
	path, _, err := r.resolve()
	if err != nil {
		t.Fatalf("自带坏了却整体报错：%v", err)
	}
	if path != `C:\other\python3.exe` {
		t.Errorf("应回落到 python3，实际 %s", path)
	}
}

// EASYCIRQ_PYTHON 仍然最高优先 —— 显式覆盖不许被自带解释器盖掉。
func TestExplicitEnvStillBeatsBundled(t *testing.T) {
	root := filepath.Join("C:", "inst")
	r := fakeResolver("windows", root, map[string]bool{bundledWinPath(root): true},
		true, map[string]string{envPython: `D:\venv\python.exe`})
	r.lookPath = func(f string) (string, error) {
		if f == `D:\venv\python.exe` {
			return f, nil
		}
		return "", errors.New("no")
	}
	path, _, err := r.resolve()
	if err != nil {
		t.Fatalf("%v", err)
	}
	if path != `D:\venv\python.exe` {
		t.Errorf("env 覆盖失效：%s", path)
	}
}

// EASYCIRQ_NO_BUNDLED_PYTHON=1 必须真的关掉自带解释器（测试与排障要用）。
func TestNoBundledSwitchDisablesIt(t *testing.T) {
	root := filepath.Join("C:", "inst")
	r := fakeResolver("windows", root, map[string]bool{bundledWinPath(root): true},
		true, map[string]string{envNoBundled: "1"})
	if _, _, err := r.resolve(); err == nil {
		t.Fatal("关掉自带解释器后不该还能解析成功")
	}
}

// 报错必须指出「自带解释器缺失 = 安装不完整」，而不是只叫人去装 Python。
func TestErrorNamesTheBundledLocation(t *testing.T) {
	root := filepath.Join("C:", "inst")
	r := fakeResolver("windows", root, map[string]bool{}, true, nil)
	_, _, err := r.resolve()
	if err == nil {
		t.Fatal("没有解释器却没报错")
	}
	msg := err.Error()
	for _, want := range []string{"<install>/python", "tried the bundled python", envPython} {
		if !strings.Contains(msg, want) {
			t.Errorf("报错缺 %q：%s", want, msg)
		}
	}
}

// 自带解释器的候选路径必须包含 bin/../python 与同目录两种布局。
func TestBundledCandidatesCoverBothLayouts(t *testing.T) {
	root := filepath.Join("C:", "inst")
	got := bundledPythonCandidates("windows", filepath.Join(root, "bin", "easycirq.exe"))
	if len(got) < 2 {
		t.Fatalf("候选太少：%v", got)
	}
	joined := strings.Join(got, "|")
	// filepath.Join 会规范化 "bin/.."，所以要比较规范化后的路径
	wantParent := filepath.Clean(filepath.Join(root, "python", "python.exe"))
	if !strings.Contains(joined, wantParent) {
		t.Errorf("缺 <root>/python 布局（应是 %s）：%v", wantParent, got)
	}
	wantFlat := filepath.Clean(filepath.Join(root, "bin", "python", "python.exe"))
	if !strings.Contains(joined, wantFlat) {
		t.Errorf("缺同目录布局（应是 %s）：%v", wantFlat, got)
	}

	posix := bundledPythonCandidates("linux", "/opt/easycirq/bin/easycirq")
	pj := strings.Join(posix, "|")
	wantPosix := filepath.Clean(filepath.Join("/opt/easycirq", "python", "bin", "python3"))
	if !strings.Contains(pj, wantPosix) {
		t.Errorf("POSIX 候选缺 %s：%v", wantPosix, posix)
	}
}
