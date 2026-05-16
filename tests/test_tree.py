# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""Pure unit tests for the print_dep_tree string renderer."""
from __future__ import annotations

import argparse

import pytest

from conda_tree.cli import make_cache_graph, print_dep_tree
from tests.conftest import MockRecord


def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {"exclude": [], "full": False, "small": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_state(args: argparse.Namespace, down_search: bool = True) -> dict:
    return {
        "down_search": down_search,
        "args": args,
        "indent": 0,
        "empty_cols": [],
        "is_last": False,
        "tree_exists": set(),
        "hidden_dependencies": False,
        "pkgs_with_cycles": set(),
    }


class TestRootNodeRendering:
    def test_root_with_version(self, linear_records):
        g = make_cache_graph(linear_records)
        args = _make_args()
        state = _make_state(args)
        # C has no deps so its tree is just the root line
        output, _ = print_dep_tree(g, "C", None, state)
        assert output.startswith("C==3.0")

    def test_root_without_version(self):
        records = [MockRecord("mypkg", None, ())]
        g = make_cache_graph(records)
        args = _make_args()
        state = _make_state(args)
        output, _ = print_dep_tree(g, "mypkg", None, state)
        assert "mypkg" in output


class TestBranchCharacters:
    def test_last_child_uses_corner(self, linear_records):
        """The only child of a node should render with '└─'."""
        g = make_cache_graph(linear_records)
        args = _make_args()
        state = _make_state(args)
        output, _ = print_dep_tree(g, "A", None, state)
        assert "└─" in output

    def test_not_last_child_uses_tee(self, diamond_records):
        """When a node has multiple children, all but the last use '├─'."""
        g = make_cache_graph(diamond_records)
        args = _make_args()
        state = _make_state(args)
        output, _ = print_dep_tree(g, "A", None, state)
        assert "├─" in output

    def test_full_linear_tree_structure(self, linear_records):
        g = make_cache_graph(linear_records)
        args = _make_args()
        state = _make_state(args)
        output, _ = print_dep_tree(g, "A", None, state)
        assert "A==" in output
        assert "B" in output
        assert "C" in output


class TestDeduplication:
    def test_repeated_dep_shows_displayed_above(self):
        """A package already expanded earlier is summarised as 'displayed above'.

        Use a graph where E has children (F), and E appears as a dep of both
        B and C.  The first time we visit E (via B→E) we expand E→F and add E
        to tree_exists.  The second time (via C→E) E is already in tree_exists
        so the subtree is hidden and 'displayed above' is shown.
        """
        records = [
            MockRecord("root", "1.0", ("B", "C")),
            MockRecord("B",    "2.0", ("E",)),
            MockRecord("C",    "3.0", ("E",)),
            MockRecord("E",    "5.0", ("F",)),   # E has a child so hide is meaningful
            MockRecord("F",    "6.0", ()),
        ]
        g = make_cache_graph(records)
        args = _make_args(full=False)
        state = _make_state(args)
        output, final_state = print_dep_tree(g, "root", None, state)
        assert "displayed above" in output
        assert final_state["hidden_dependencies"] is True

    def test_dep_without_children_is_not_hidden(self, diamond_records):
        """D is shared but has no children — the deduplicate/hide path is never
        triggered because there is nothing to hide under D."""
        g = make_cache_graph(diamond_records)
        args = _make_args(full=False)
        state = _make_state(args)
        output, final_state = print_dep_tree(g, "A", None, state)
        # D appears twice in the output (once under B, once under C)
        assert output.count("D") >= 2
        # But because D has no children, hidden_dependencies stays False
        assert final_state["hidden_dependencies"] is False

    def test_full_flag_suppresses_dedup(self):
        """With --full, the second occurrence of E is still expanded."""
        records = [
            MockRecord("root", "1.0", ("B", "C")),
            MockRecord("B",    "2.0", ("E",)),
            MockRecord("C",    "3.0", ("E",)),
            MockRecord("E",    "5.0", ("F",)),
            MockRecord("F",    "6.0", ()),
        ]
        g = make_cache_graph(records)
        args = _make_args(full=True)
        state = _make_state(args)
        output, final_state = print_dep_tree(g, "root", None, state)
        assert "displayed above" not in output


class TestExcludeList:
    def test_excluded_package_subtree_not_rendered(self, linear_records):
        """When B is in the exclude list its dep C should not appear in output."""
        g = make_cache_graph(linear_records)
        args = _make_args(exclude=["B"])
        state = _make_state(args)
        output, _ = print_dep_tree(g, "A", None, state)
        # B itself is shown (it is a direct dep of A)
        assert "B" in output
        # C should be absent — B's subtree is suppressed
        assert "C" not in output


class TestUpSearch:
    def test_whoneeds_renders_parent(self, linear_records):
        """In up-search mode, whoneeds C shows B as a dependent."""
        g = make_cache_graph(linear_records)
        args = _make_args()
        state = _make_state(args, down_search=False)
        output, _ = print_dep_tree(g, "C", None, state)
        assert "C==" in output
        assert "B" in output
