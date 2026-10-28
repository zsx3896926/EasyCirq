"""Token binding, task-id binding and the four-party version handshake."""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support


class TokenBindingTests(support.BoundTestCase):
    def test_valid_token_starts_the_supervisor(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.assertEqual(client.request("ping")["result"], {})
        self.assertIn(harness.task_id, client.stderr_text())

    def test_token_passed_as_option_works(self) -> None:
        harness = self.harness()
        client = support.MCPClient(
            config_path=harness.config_path, token_file=None, token=harness.token
        )
        self.addCleanup(client.close)
        client.initialize()
        self.assertEqual(client.request("ping")["result"], {})

    def test_missing_token_file_exits_two_with_token_missing(self) -> None:
        harness = self.harness()
        harness.token_file.unlink()
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("TOKEN_MISSING", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_wrong_token_exits_two_with_token_invalid(self) -> None:
        harness = self.harness()
        harness.token_file.write_text("not-the-token", encoding="utf-8", newline="\n")
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("TOKEN_INVALID", completed.stderr)

    def test_absent_token_option_exits_two(self) -> None:
        harness = self.harness()
        completed = support.run_serve_expect_exit(harness.config_path)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("TOKEN_MISSING", completed.stderr)

    def test_second_serve_on_same_task_dir_is_refused(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.start_task(client, harness)
        self.assertEqual(len(support.load_receipts(harness.task_dir)), 1)
        client.close()
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("TASK_ALREADY_STARTED", completed.stderr)


class ConfigStartupTests(support.BoundTestCase):
    def test_missing_config_exits_two(self) -> None:
        harness = self.harness()
        completed = support.run_serve_expect_exit(harness.root / "missing.json")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("INVALID_CONFIG", completed.stderr)

    def test_unknown_config_field_exits_two(self) -> None:
        harness = self.harness()
        config = harness.config()
        config["unexpected_field"] = "nope"
        harness.save_config(config)
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(
            "INVALID_CONFIG" in completed.stderr or "INVALID_ARGUMENTS" in completed.stderr,
            completed.stderr,
        )

    def test_server_version_mismatch_exits_two(self) -> None:
        harness = self.harness()
        config = harness.config()
        config["versions"]["server"] = "9.9.9"
        harness.save_config(config)
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("VERSION_MISMATCH", completed.stderr)

    def test_backend_version_mismatch_exits_two(self) -> None:
        harness = self.harness()
        config = harness.config()
        config["versions"]["backend"] = "fixture-9"
        harness.save_config(config)
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("VERSION_MISMATCH", completed.stderr)

    def test_real_eda_backend_without_authorization_exits_two(self) -> None:
        harness = self.harness(plan_extra=("--backend", "official_cli"))
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("EDA_NOT_AUTHORIZED", completed.stderr)

    def test_token_hash_is_bound_to_the_token_file(self) -> None:
        harness = self.harness()
        config = harness.config()
        self.assertEqual(config["token_sha256"], support.sha256_hex(harness.token))
        self.assertNotIn(harness.token, support.read_text(harness.config_path))


class TaskIdAndToolchainHandshakeTests(support.BoundTestCase):
    def test_wrong_task_id_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        error = self.assert_tool_error(
            client,
            "task_start",
            support.start_arguments(harness, task_id="another-task-0001"),
            code="TASK_ID_MISMATCH",
        )
        self.assertEqual(error["detail"]["expected"], harness.task_id)

    def test_each_toolchain_version_must_match(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        for field in ("skill", "plugin", "server", "backend"):
            toolchain = dict(harness.summary["versions"])
            toolchain[field] = "9.9.9"
            error = self.assert_tool_error(
                client,
                "task_start",
                support.start_arguments(harness, toolchain=toolchain),
                code="VERSION_MISMATCH",
            )
            self.assertIn(field, error["detail"]["mismatched"])
        # A correct handshake afterwards still works: refusals do not advance.
        payload = self.start_task(client, harness)
        self.assertEqual(payload["state"], "STARTED")

    def test_default_version_is_not_silently_accepted(self) -> None:
        harness = self.harness(plan_extra=("--skill-version", "2.0.0"))
        client = self.client(harness)
        toolchain = dict(harness.summary["versions"])
        toolchain["skill"] = "1.0.2"
        self.assert_tool_error(
            client,
            "task_start",
            support.start_arguments(harness, toolchain=toolchain),
            code="VERSION_MISMATCH",
        )

    def test_version_mismatch_does_not_write_a_receipt(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.assert_tool_error(
            client,
            "task_start",
            support.start_arguments(harness, toolchain=dict(harness.summary["versions"], skill="0.0.1")),
            code="VERSION_MISMATCH",
        )
        entries = support.load_receipts(harness.task_dir)
        self.assertEqual(entries, [])
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "CREATED")

    def test_missing_toolchain_field_is_argument_error_not_handshake(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = support.start_arguments(harness)
        del arguments["toolchain"]["backend"]
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
