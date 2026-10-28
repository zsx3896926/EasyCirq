"""Tests for the B1 task launcher sidecar (``task_launcher``).

Every test drives a real launcher subprocess over loopback HTTP with the bundled
fake agent.  No test calls a real EDA, a daemon, a connector or the network.
"""
