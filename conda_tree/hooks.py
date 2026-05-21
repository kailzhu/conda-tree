# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""conda plugin hook registration for conda-tree."""
from conda.plugins import hookimpl
from conda.plugins.types import CondaSubcommand

from conda_tree.cli import main


@hookimpl
def conda_subcommands():
    yield CondaSubcommand(
        name="tree",
        action=main,
        summary="Display conda dependency trees",
    )
