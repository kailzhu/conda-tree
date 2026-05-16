# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""Shared fixtures for the conda-tree test suite."""
from __future__ import annotations

from collections import namedtuple

import pytest

pytest_plugins = "conda.testing.fixtures"

# A lightweight stand-in for PrefixRecord usable in pure unit tests.
# Must expose .name, .version, and .depends (tuple of dep spec strings).
MockRecord = namedtuple("MockRecord", ["name", "version", "depends"])


@pytest.fixture
def linear_records():
    """A → B → C linear dependency chain.

    A depends on B, B depends on C, C has no dependencies.
    A is a leaf (in-degree 0 from the perspective of who needs it).
    """
    return [
        MockRecord("A", "1.0", ("B >=1.0",)),
        MockRecord("B", "2.0", ("C",)),
        MockRecord("C", "3.0", ()),
    ]


@pytest.fixture
def cycle_records():
    """A ⇄ B cycle, plus an isolated node C.

    A depends on B, B depends on A (cycle).
    C has no dependencies and nothing depends on it (true leaf).
    """
    return [
        MockRecord("A", "1.0", ("B",)),
        MockRecord("B", "2.0", ("A",)),
        MockRecord("C", "3.0", ()),
    ]


@pytest.fixture
def diamond_records():
    """Diamond dependency: A → B, A → C, B → D, C → D.

    D is a shared transitive dep — tests deduplication behaviour.
    """
    return [
        MockRecord("A", "1.0", ("B", "C")),
        MockRecord("B", "2.0", ("D",)),
        MockRecord("C", "3.0", ("D",)),
        MockRecord("D", "4.0", ()),
    ]


@pytest.fixture(scope="session")
def integration_env(session_tmp_env):
    """Real conda environment with requests + flask installed.

    Session-scoped so it is created once and reused across all integration
    tests — creating a conda env takes ~30 s.
    """
    with session_tmp_env("requests", "flask", "--channel", "conda-forge") as prefix:
        yield prefix
