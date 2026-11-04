"""复现 BoundGateTests 的偶发失败，并把 stdout 一起打出来。

测试只把 stderr 塞进断言消息，而 launcher 在 LauncherError 时把 payload 打到
stdout，所以从测试输出里看不到真正的原因。
"""
import json
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1] / "tests"
sys.path.insert(0, str(TESTS))

from task_launcher_tests.support import base_request, write_request  # noqa: E402
from task_launcher_tests.test_bound_integration import run_cli  # noqa: E402


def attempt(index: int):
    with tempfile.TemporaryDirectory(prefix="b1-bound-gate-") as raw:
        tmp = Path(raw)
        state_dir = tmp / "state"
        task_id = "task-bound-gate-001"
        request_path = write_request(tmp, base_request(task_id, timeout_s=120))
        template = {
            "argv": [
                "{python}", "-m", "task_launcher.fake_agent",
                "-p", "{user_prompt}",
                "--plugin-dir", "{plugin_dir}",
                "--append-system-prompt-file", "{routing_file}",
                "--mcp-config", "{mcp_config}",
                "--output-format", "stream-json",
                "--verbose",
                "--allowedTools", "{allowed_tools}",
                "--settings", "{settings}",
                "--disallowedTools", "{disallowed_tools}",
                "--add-dir", "{task_dir}",
            ]
        }
        template_path = tmp / "claude-template.json"
        template_path.write_text(json.dumps(template), encoding="utf-8")
        completed = run_cli([
            "run", "--request", str(request_path), "--state-dir", str(state_dir),
            "--bound", "--agent-profile", "claude",
            "--claude-exe", sys.executable,
            "--agent-argv-template", str(template_path),
        ])
        if completed.returncode != 1:
            print(f"run {index}: returncode={completed.returncode}")
            print("--- stdout ---")
            print((completed.stdout or "")[:1500])
            print("--- stderr ---")
            print((completed.stderr or "")[:800])
            result = state_dir / "tasks" / task_id / "result.json"
            print("--- result.json exists:", result.is_file())
            return False
        return True


def main():
    for index in range(1, 41):
        if not attempt(index):
            return 1
        print(f"run {index}: ok")
    print("no failure in 40 runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
