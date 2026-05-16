# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""Smoke tests for the conda plugin hook registration."""
from __future__ import annotations

from conda.plugins.types import CondaSubcommand

from conda_tree.hooks import conda_subcommands


def test_hook_yields_exactly_one_subcommand():
    results = list(conda_subcommands())
    assert len(results) == 1


def test_hook_subcommand_name_is_tree():
    results = list(conda_subcommands())
    assert results[0].name == "tree"


def test_hook_action_is_callable():
    results = list(conda_subcommands())
    assert callable(results[0].action)


def test_hook_returns_conda_subcommand_type():
    results = list(conda_subcommands())
    assert isinstance(results[0], CondaSubcommand)


def test_hook_summary_is_nonempty():
    results = list(conda_subcommands())
    assert results[0].summary
