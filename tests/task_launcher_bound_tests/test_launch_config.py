"""Launch configuration: settings.json, mcp.json, hardened argv, routing text."""

from __future__ import annotations

import unittest
from pathlib import Path

from task_launcher_bound_tests import support


class SettingsTests(support.BoundTestCase):
    def test_settings_deny_contains_all_dangerous_tools(self) -> None:
        harness = self.harness()
        settings = support.read_json(harness.task_dir / "settings.json")
        deny = settings["permissions"]["deny"]
        self.assertEqual(set(deny), set(support.DENIED_AGENT_TOOLS))
        self.assertEqual(len(deny), 8)
        for tool in ("Bash", "Write", "Edit", "NotebookEdit", "Agent", "Task", "WebFetch", "WebSearch"):
            self.assertIn(tool, deny)

    def test_settings_allow_is_the_read_only_surface(self) -> None:
        harness = self.harness()
        settings = support.read_json(harness.task_dir / "settings.json")
        allow = settings["permissions"]["allow"]
        self.assertEqual(set(allow), set(support.ALLOWED_AGENT_TOOLS))
        for tool in ("Bash", "Write", "Edit", "Agent", "Task", "WebFetch", "WebSearch"):
            self.assertNotIn(tool, allow)
        self.assertIn(f"Skill({support.SKILL_NAME})", allow)
        self.assertIn("mcp__easycirq_bound__*", allow)

    def test_settings_default_mode_and_env_are_minimal(self) -> None:
        harness = self.harness()
        settings = support.read_json(harness.task_dir / "settings.json")
        self.assertEqual(settings["permissions"]["defaultMode"], "default")
        self.assertEqual(settings["env"], {"EASYCIRQ_BOUND_PHASE": "1"})

    def test_settings_do_not_contain_the_token_or_hmac_key(self) -> None:
        harness = self.harness()
        text = support.read_text(harness.task_dir / "settings.json")
        self.assertNotIn(harness.token, text)
        self.assertNotIn("hmac", text.lower())

    def test_default_settings_have_no_hooks(self) -> None:
        harness = self.harness()
        settings = support.read_json(harness.task_dir / "settings.json")
        self.assertNotIn("hooks", settings)

    def test_hooks_flag_write_optional_hook_layer(self) -> None:
        harness = self.harness(hooks=True)
        settings = support.read_json(harness.task_dir / "settings.json")
        hooks = settings["hooks"]
        self.assertEqual(set(hooks), {"PreToolUse", "PostToolUse", "Stop"})
        command_strings = []
        for groups in hooks.values():
            for group in groups:
                self.assertIsInstance(group.get("matcher", ""), str)
                for hook in group.get("hooks", []):
                    self.assertEqual(hook["type"], "command")
                    self.assertGreater(hook["timeout"], 0)
                    command_strings.append(hook["command"])
        commands = " ".join(command_strings)
        for script in ("mark_skill.py", "require_skill.py", "verify_stop.py"):
            self.assertIn(script, commands)
        self.assertIn(str(harness.task_dir), commands)
        self.assertNotIn(harness.token, commands)


class McpConfigTests(support.BoundTestCase):
    def test_mcp_json_mounts_only_the_bound_supervisor(self) -> None:
        harness = self.harness()
        document = support.read_json(harness.task_dir / "mcp.json")
        servers = document["mcpServers"]
        self.assertEqual(len(servers), 1)
        name = next(iter(servers))
        self.assertIn(name, ("easycirq_bound", "easycirq-bound"))
        server = servers[name]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(Path(server["command"]).name.lower(), Path(__import__("sys").executable).name.lower())
        args = server["args"]
        self.assertEqual(args[:4], ["-m", "task_launcher.bound", "serve", "--config"])
        self.assertIn(str(harness.config_path), args)
        self.assertIn("--token-file", args)
        self.assertIn(str(harness.token_file), args)

    def test_mcp_json_env_is_a_whitelist(self) -> None:
        harness = self.harness()
        server = next(iter(support.read_json(harness.task_dir / "mcp.json")["mcpServers"].values()))
        env = server["env"]
        self.assertEqual(set(env), {"PYTHONPATH", "PYTHONIOENCODING"})
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(Path(env["PYTHONPATH"]).resolve(), support.WORKTREE.resolve())

    def test_mcp_json_does_not_embed_secrets(self) -> None:
        harness = self.harness()
        text = support.read_text(harness.task_dir / "mcp.json")
        self.assertNotIn(harness.token, text)
        self.assertNotIn("hmac", text.lower())
        self.assertIn("task.token", text)


class AgentArgvTests(support.BoundTestCase):
    def fake_plugin_dir(self) -> Path:
        plugin_dir = self.temp_dir(prefix="zgb-plugin-") / "design-hardware"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "design-hardware"}\n', encoding="utf-8")
        return plugin_dir

    def test_without_plugin_dir_agent_is_not_ready(self) -> None:
        harness = self.harness()
        self.assertFalse(harness.summary["agent_ready"])
        self.assertEqual(harness.summary["agent_argv"], [])
        not_run = " ".join(harness.summary["agent_not_run"])
        self.assertIn("NOT RUN", not_run)
        self.assertIn("--plugin-dir", not_run)
        command = support.read_json(harness.task_dir / "agent.command.json")
        self.assertEqual(command["argv"], [])
        self.assertFalse(command["agent_ready"])

    def test_with_plugin_dir_argv_contains_all_hardening_flags(self) -> None:
        plugin_dir = self.fake_plugin_dir()
        harness = self.harness(plugin_dir=plugin_dir)
        argv = harness.summary["agent_argv"]
        self.assertTrue(argv)
        for flag in (
            "-p",
            "--mcp-config",
            "--plugin-dir",
            "--append-system-prompt-file",
            "--settings",
            "--output-format",
            "--allowedTools",
            "--disallowedTools",
        ):
            self.assertIn(flag, argv, flag)
        self.assertIn("stream-json", argv)
        self.assertIn("--verbose", argv)
        prompt_index = argv.index("-p") + 1
        self.assertEqual(argv[prompt_index], harness.request["goal"]["user_prompt"])

    def test_with_plugin_dir_argv_pins_the_read_only_tool_surface(self) -> None:
        harness = self.harness(plugin_dir=self.fake_plugin_dir())
        argv = harness.summary["agent_argv"]
        allowed = argv[argv.index("--allowedTools") + 1].split(",")
        disallowed = argv[argv.index("--disallowedTools") + 1].split(",")
        self.assertEqual(set(allowed), set(support.ALLOWED_AGENT_TOOLS))
        self.assertEqual(set(disallowed), set(support.DENIED_AGENT_TOOLS))
        for tool in ("Bash", "Write", "Edit", "Agent", "Task", "WebFetch", "WebSearch"):
            self.assertNotIn(tool, allowed)

    def test_with_plugin_dir_argv_has_no_secrets_or_bypass_flags(self) -> None:
        harness = self.harness(plugin_dir=self.fake_plugin_dir())
        joined = " ".join(harness.summary["agent_argv"])
        self.assertNotIn(harness.token, joined)
        self.assertNotIn(harness.config()["token_sha256"], joined)
        self.assertNotIn("hmac", joined.lower())
        for forbidden in (
            "--dangerously-skip-permissions",
            "bypassPermissions",
            "--allow-dangerously-skip-permissions",
        ):
            self.assertNotIn(forbidden, joined)

    def test_agent_command_file_matches_plan_summary(self) -> None:
        harness = self.harness(plugin_dir=self.fake_plugin_dir())
        command = support.read_json(harness.task_dir / "agent.command.json")
        self.assertEqual(command["schema"], "easycirq.bound.agent-command/v1")
        self.assertEqual(command["argv"], harness.summary["agent_argv"])
        self.assertEqual(Path(command["cwd"]).resolve(), harness.task_dir.resolve())
        self.assertIn("PYTHONIOENCODING", command["env_whitelist"])
        self.assertNotIn("EASYCIRQ_BOUND_TOKEN", command["env_whitelist"])
        self.assertNotIn("EASYCIRQ_BOUND_HMAC_KEY", command["env_whitelist"])

    def test_nonexistent_plugin_dir_is_rejected(self) -> None:
        root = self.temp_dir()
        request = support.make_request("bound-plugin-missing")
        support.write_json(root / "request.json", request)
        completed = support.run_cli(
            "plan",
            "--request",
            root / "request.json",
            "--out",
            root / "task",
            "--plugin-dir",
            root / "does-not-exist",
        )
        self.assertEqual(completed.returncode, 2)
        document = support.parse_stdout_json(completed)
        self.assertEqual(document["error"]["code"], "INVALID_CONFIG")


class PlanArtifactTests(support.BoundTestCase):
    def test_plan_summary_declares_no_repo_writes_and_no_eda(self) -> None:
        harness = self.harness()
        summary = harness.summary
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["schema"], "easycirq.bound.plan/v1")
        self.assertFalse(summary["wrote_repo"])
        self.assertEqual(summary["real_eda"], "NOT RUN")
        self.assertEqual(summary["eda_calls"], 0)
        self.assertEqual(summary["phase"], 1)
        self.assertEqual(summary["backend"], "fixture")
        self.assertEqual(summary["audit_engine"], "fixture")
        self.assertEqual(summary["b1"]["note"], "BLOCKED ON B1")
        self.assertEqual(
            set(summary["files"]),
            {
                "request.json",
                "bound.config.json",
                "routing.md",
                "mcp.json",
                "settings.json",
                "agent.command.json",
                "task.token",
            },
        )

    def test_config_contains_only_the_token_hash(self) -> None:
        harness = self.harness()
        config = harness.config()
        self.assertEqual(config["schema"], "easycirq.bound.config/v1")
        self.assertEqual(config["token_sha256"], support.sha256_hex(harness.token))
        self.assertNotIn("token", config)
        config_text = support.read_text(harness.config_path)
        self.assertNotIn(harness.token, config_text)
        self.assertNotIn("hmac", config_text.lower())
        self.assertEqual(config["phase"], 1)
        self.assertFalse(config["eda_authorized"])
        self.assertEqual(config["versions"], harness.summary["versions"])
        self.assertEqual(config["limits"], harness.summary["limits"])

    def test_no_artifact_leaks_the_token(self) -> None:
        harness = self.harness()
        for name in (
            "bound.config.json",
            "request.json",
            "routing.md",
            "mcp.json",
            "settings.json",
            "agent.command.json",
        ):
            text = support.read_text(harness.task_dir / name)
            self.assertNotIn(harness.token, text, name)

    def test_routing_md_contains_the_hard_rules(self) -> None:
        harness = self.harness()
        routing = support.read_text(harness.task_dir / "routing.md")
        self.assertIn(support.SKILL_NAME, routing)
        self.assertIn("task_start", routing)
        self.assertIn("snapshot_read", routing)
        self.assertIn("finalize", routing)
        self.assertIn("NOT RUN", routing)
        self.assertIn("只读", routing)
        versions = harness.summary["versions"]
        for value in versions.values():
            self.assertIn(value, routing)
        self.assertNotIn(harness.token, routing)

    def test_plan_into_non_empty_dir_requires_force(self) -> None:
        harness = self.harness()
        stale = harness.task_dir / "stale.txt"
        stale.write_text("stale\n", encoding="utf-8")
        completed = support.run_cli(
            "plan",
            "--request",
            harness.request_path,
            "--out",
            harness.task_dir,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(
            support.parse_stdout_json(completed)["error"]["code"], "INVALID_CONFIG"
        )
        forced = support.run_cli(
            "plan",
            "--request",
            harness.request_path,
            "--out",
            harness.task_dir,
            "--force",
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertFalse(stale.exists())
        self.assertTrue((harness.task_dir / "bound.config.json").is_file())

    def test_invalid_request_documents_are_refused(self) -> None:
        root = self.temp_dir()
        cases = []
        null_no_missing = support.make_request("bound-invalid-null")
        null_no_missing["context"].pop("missing_fields", None)
        cases.append(null_no_missing)
        bad_mode = support.make_request("bound-invalid-mode")
        bad_mode["mode"] = "read_write"
        cases.append(bad_mode)
        bad_task_id = support.make_request("任务一")
        cases.append(bad_task_id)
        for index, request in enumerate(cases):
            support.write_json(root / ("request-%d.json" % index), request)
            completed = support.run_cli(
                "plan",
                "--request",
                root / ("request-%d.json" % index),
                "--out",
                root / ("task-%d" % index),
            )
            self.assertEqual(completed.returncode, 2, request)
            self.assertEqual(
                support.parse_stdout_json(completed)["error"]["code"], "INVALID_REQUEST"
            )

    def test_task_dir_outside_state_root_is_refused(self) -> None:
        root = self.temp_dir()
        request = support.make_request("bound-state-root")
        support.write_json(root / "request.json", request)
        completed = support.run_cli(
            "plan",
            "--request",
            root / "request.json",
            "--out",
            root / "task",
            "--state-root",
            root / "state",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(
            support.parse_stdout_json(completed)["error"]["code"],
            "PATH_OUTSIDE_TASK_DIR",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
