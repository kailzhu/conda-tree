# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""Integration tests using a real conda environment.

The session-scoped `integration_env` fixture (defined in conftest.py) creates
a conda environment containing `requests` and `flask` once per test session.
All tests call main() in-process with --prefix before the subcommand name,
which is how argparse with subparsers expects global flags to be ordered.
"""
from __future__ import annotations

import json

import pytest

from conda_tree.cli import main


def _prefix_args(prefix, *subcmd_args):
    """Return ['--prefix', <prefix>, *subcmd_args] — global flag before subcommand."""
    return ["--prefix", str(prefix)] + list(subcmd_args)


# ── leaves subcommand ─────────────────────────────────────────────────────────

class TestLeaves:
    def test_leaves_contains_requests(self, integration_env, capsys):
        main(_prefix_args(integration_env, "leaves"))
        out, _ = capsys.readouterr()
        assert "requests" in out

    def test_leaves_contains_flask(self, integration_env, capsys):
        main(_prefix_args(integration_env, "leaves"))
        out, _ = capsys.readouterr()
        assert "flask" in out

    def test_leaves_json_is_list(self, integration_env, capsys):
        main(_prefix_args(integration_env, "leaves", "--json"))
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_leaves_json_contains_requests(self, integration_env, capsys):
        main(_prefix_args(integration_env, "leaves", "--json"))
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert "requests" in data

    def test_leaves_export_channel_format(self, integration_env, capsys):
        """Each --export line must be channel::name=version=build."""
        main(_prefix_args(integration_env, "leaves", "--export"))
        out, _ = capsys.readouterr()
        assert out.strip(), "Expected non-empty output from leaves --export"
        for line in out.strip().splitlines():
            assert "::" in line, f"Missing '::' in export line: {line!r}"
            assert line.count("=") >= 2, f"Expected name=ver=build in: {line!r}"


# ── depends subcommand ────────────────────────────────────────────────────────

class TestDepends:
    def test_depends_requests_shows_urllib3(self, integration_env, capsys):
        main(_prefix_args(integration_env, "depends", "requests"))
        out, _ = capsys.readouterr()
        assert "urllib3" in out

    def test_depends_requests_recursive(self, integration_env, capsys):
        main(_prefix_args(integration_env, "depends", "--recursive", "requests"))
        out, _ = capsys.readouterr()
        assert out.strip()
        assert "urllib3" in out

    def test_depends_tree_flask_contains_jinja2(self, integration_env, capsys):
        main(_prefix_args(integration_env, "depends", "--tree", "flask"))
        out, _ = capsys.readouterr()
        assert "flask" in out
        assert "jinja2" in out

    def test_depends_tree_shows_version(self, integration_env, capsys):
        main(_prefix_args(integration_env, "depends", "--tree", "requests"))
        out, _ = capsys.readouterr()
        assert "requests==" in out

    def test_depends_json(self, integration_env, capsys):
        main(_prefix_args(integration_env, "depends", "--json", "requests"))
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert isinstance(data, list)
        assert "urllib3" in data

    def test_depends_missing_package_exits_nonzero(self, integration_env):
        with pytest.raises(SystemExit) as exc:
            main(_prefix_args(integration_env, "depends", "nonexistent-pkg-xyz"))
        assert exc.value.code != 0

    def test_depends_dot_output(self, integration_env, capsys):
        main(_prefix_args(integration_env, "depends", "--dot", "requests"))
        out, _ = capsys.readouterr()
        assert out.startswith("digraph {")
        assert "requests" in out


# ── whoneeds subcommand ───────────────────────────────────────────────────────

class TestWhoneeds:
    def test_whoneeds_markupsafe_shows_jinja2(self, integration_env, capsys):
        """markupsafe is a dep of jinja2."""
        main(_prefix_args(integration_env, "whoneeds", "markupsafe"))
        out, _ = capsys.readouterr()
        assert "jinja2" in out

    def test_whoneeds_certifi_has_results(self, integration_env, capsys):
        """certifi is a dep of requests (and possibly others)."""
        main(_prefix_args(integration_env, "whoneeds", "certifi"))
        out, _ = capsys.readouterr()
        assert out.strip()

    def test_whoneeds_tree_mode(self, integration_env, capsys):
        main(_prefix_args(integration_env, "whoneeds", "--tree", "markupsafe"))
        out, _ = capsys.readouterr()
        assert "markupsafe" in out

    def test_whoneeds_missing_package_exits_nonzero(self, integration_env):
        with pytest.raises(SystemExit) as exc:
            main(_prefix_args(integration_env, "whoneeds", "nonexistent-pkg-xyz"))
        assert exc.value.code != 0


# ── cycles subcommand ─────────────────────────────────────────────────────────

class TestCycles:
    def test_cycles_output_is_valid_format(self, integration_env, capsys):
        """cycles output, when present, must be newline-separated arrows."""
        main(_prefix_args(integration_env, "cycles"))
        out, _ = capsys.readouterr()
        # cycles are possible in real envs (e.g. pip <-> python)
        # just verify the format: each line is "a -> b -> ... -> a"
        for line in out.strip().splitlines():
            assert "->" in line


# ── deptree subcommand ────────────────────────────────────────────────────────

class TestDeptree:
    def test_deptree_produces_output(self, integration_env, capsys):
        main(_prefix_args(integration_env, "deptree"))
        out, _ = capsys.readouterr()
        assert out.strip()

    def test_deptree_json(self, integration_env, capsys):
        main(_prefix_args(integration_env, "deptree", "--json"))
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_deptree_dot_output(self, integration_env, capsys):
        main(_prefix_args(integration_env, "deptree", "--dot"))
        out, _ = capsys.readouterr()
        assert out.startswith("digraph {")
