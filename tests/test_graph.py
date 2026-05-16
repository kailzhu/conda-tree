# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""Pure unit tests for graph construction and traversal.

These tests require no conda installation — all inputs are built from
MockRecord namedtuples defined in conftest.py.
"""
from __future__ import annotations

import networkx
import pytest

from conda_tree.cli import find_reachable_pkgs, is_node_reachable, make_cache_graph


# ── make_cache_graph ──────────────────────────────────────────────────────────

class TestMakeCacheGraph:
    def test_node_count(self, linear_records):
        g = make_cache_graph(linear_records)
        assert len(g.nodes) == 3

    def test_node_versions_stored(self, linear_records):
        g = make_cache_graph(linear_records)
        assert g.nodes["A"]["version"] == "1.0"
        assert g.nodes["B"]["version"] == "2.0"
        assert g.nodes["C"]["version"] == "3.0"

    def test_edges_built_correctly(self, linear_records):
        g = make_cache_graph(linear_records)
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "C")
        assert not g.has_edge("A", "C")  # not a direct edge

    def test_dep_version_spec_stripped(self, linear_records):
        """'B >=1.0' must produce an edge to node 'B', not 'B >=1.0'."""
        g = make_cache_graph(linear_records)
        assert "B" in g.nodes
        assert "B >=1.0" not in g.nodes

    def test_dep_version_stored_on_edge(self, linear_records):
        g = make_cache_graph(linear_records)
        assert g.edges["A", "B"]["version"] == [">=1.0"]

    def test_empty_depends_creates_isolated_node(self):
        from tests.conftest import MockRecord
        records = [MockRecord("solo", "1.0", ())]
        g = make_cache_graph(records)
        assert "solo" in g.nodes
        assert list(g.out_edges("solo")) == []

    def test_cycle_records(self, cycle_records):
        g = make_cache_graph(cycle_records)
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "A")

    def test_diamond_graph(self, diamond_records):
        g = make_cache_graph(diamond_records)
        assert g.has_edge("A", "B")
        assert g.has_edge("A", "C")
        assert g.has_edge("B", "D")
        assert g.has_edge("C", "D")


# ── Leaf detection ────────────────────────────────────────────────────────────

class TestGetLeaves:
    def _get_leaves(self, graph):
        return [n for n, deg in graph.in_degree() if deg == 0]

    def test_linear_only_a_is_leaf(self, linear_records):
        g = make_cache_graph(linear_records)
        leaves = self._get_leaves(g)
        assert leaves == ["A"]

    def test_cycle_only_c_is_leaf(self, cycle_records):
        """A and B form a cycle — neither has in-degree 0. C is the true leaf."""
        g = make_cache_graph(cycle_records)
        leaves = self._get_leaves(g)
        assert set(leaves) == {"C"}

    def test_diamond_only_a_is_leaf(self, diamond_records):
        g = make_cache_graph(diamond_records)
        leaves = self._get_leaves(g)
        assert leaves == ["A"]


# ── Cycle detection ───────────────────────────────────────────────────────────

class TestCycleDetection:
    def test_no_cycles_in_linear(self, linear_records):
        g = make_cache_graph(linear_records)
        cycles = list(networkx.simple_cycles(g))
        assert cycles == []

    def test_cycle_found(self, cycle_records):
        g = make_cache_graph(cycle_records)
        cycles = list(networkx.simple_cycles(g))
        # There should be exactly one cycle involving A and B
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B"}

    def test_no_cycles_in_diamond(self, diamond_records):
        g = make_cache_graph(diamond_records)
        cycles = list(networkx.simple_cycles(g))
        assert cycles == []


# ── is_node_reachable ─────────────────────────────────────────────────────────

class TestIsNodeReachable:
    def test_direct_edge_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        assert is_node_reachable(g, "A", "B") is True

    def test_transitive_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        assert is_node_reachable(g, "A", "C") is True

    def test_reverse_not_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        assert is_node_reachable(g, "C", "A") is False

    def test_same_node_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        # A node is reachable from itself (trivial path)
        assert is_node_reachable(g, "A", "A") is True

    def test_nonexistent_node_not_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        assert is_node_reachable(g, "A", "Z") is False

    def test_list_source_any_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        # Both C and A are in the list; A can reach C, C cannot reach A
        assert is_node_reachable(g, ["C", "A"], "C") is True

    def test_list_source_none_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        assert is_node_reachable(g, ["C"], "A") is False


# ── find_reachable_pkgs ───────────────────────────────────────────────────────

class TestFindReachablePkgs:
    def test_down_search_from_a(self, linear_records):
        g = make_cache_graph(linear_records)
        result = find_reachable_pkgs(g, "A", down_search=True)
        assert set(result) == {"B", "C"}

    def test_down_search_excludes_self(self, linear_records):
        g = make_cache_graph(linear_records)
        result = find_reachable_pkgs(g, "A", down_search=True)
        assert "A" not in result

    def test_up_search_from_c(self, linear_records):
        """C is depended on by B which is depended on by A."""
        g = make_cache_graph(linear_records)
        result = find_reachable_pkgs(g, "C", down_search=False)
        assert set(result) == {"A", "B"}

    def test_up_search_from_b(self, linear_records):
        g = make_cache_graph(linear_records)
        result = find_reachable_pkgs(g, "B", down_search=False)
        assert set(result) == {"A"}

    def test_exclude_breaks_path(self, linear_records):
        """Excluding B should prevent A from reaching C via B."""
        g = make_cache_graph(linear_records)
        result = find_reachable_pkgs(g, "A", down_search=True, exclude_pkgs={"B"})
        # Path A→B→C is broken by excluding B; C is not reachable
        assert "C" not in result

    def test_leaf_has_no_down_reachable(self, linear_records):
        g = make_cache_graph(linear_records)
        result = find_reachable_pkgs(g, "C", down_search=True)
        assert result == []
