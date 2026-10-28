"""Offline, subprocess-only acceptance tests for the B1-Bound package.

The test process never imports ``task_launcher.bound``: every assertion drives
the public CLI / MCP stdio surface in a child process, exactly like the real
launcher and agent runtime would. All state is written to ``tempfile``
directories so the repository itself is never modified.
"""
