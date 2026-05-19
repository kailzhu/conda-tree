# Copyright (C) conda-tree contributors
# SPDX-License-Identifier: MIT
"""conda-tree CLI: dependency tree helper for conda environments."""
from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
from typing import Iterable

import colorama
import networkx
from colorama import Style

from conda.core.prefix_data import PrefixData

from . import __version__

colorama.init()

# The number of spaces per indent level
TABSIZE = 3


# ── Data access ───────────────────────────────────────────────────────────────

def get_prefix_data(prefix: str) -> PrefixData:
    """Return a PrefixData instance for the given environment prefix."""
    return PrefixData(prefix)


# ── Graph construction ────────────────────────────────────────────────────────

def make_cache_graph(records: Iterable) -> networkx.DiGraph:
    """Build a directed dependency graph from an iterable of package records.

    Each record must expose .name, .version, and .depends attributes.
    .depends is a tuple/list of dependency spec strings like "numpy >=1.20".
    This accepts both real PrefixRecord objects and MockRecord namedtuples,
    making it fully testable without a live conda installation.
    """
    g = networkx.DiGraph()
    for record in records:
        g.add_node(record.name, version=record.version)
        for dep in record.depends:
            dep_name = dep.split(" ")[0]
            dep_version = dep.split(" ")[1:]
            g.add_edge(record.name, dep_name, version=dep_version)
    return g


def print_graph_dot(g: networkx.DiGraph, exclude_pkgs: set = set()) -> None:
    """Print a Graphviz DOT representation of the dependency graph."""
    print("digraph {")
    for k, v in g.edges():
        if k not in exclude_pkgs and v not in exclude_pkgs:
            print(f'  "{k}" -> "{v}"')
    print("}")


# ── Tree rendering ─────────────────────────────────────────────────────────────

def print_dep_tree(
    g: networkx.DiGraph, pkg: str, prev: str | None, state: dict
) -> tuple[str, dict]:
    """Recursively render a dependency tree as a Unicode box-drawing string.

    Returns (rendered_string, updated_state).
    """
    down_search, args = state["down_search"], state["args"]
    indent = state["indent"]
    empty_cols, is_last = state["empty_cols"], state["is_last"]

    s = ""
    v = g.nodes[pkg].get("version")

    edges = g.out_edges(pkg) if down_search else g.in_edges(pkg)
    e = [i[1] for i in edges] if down_search else [i[0] for i in edges]

    if len(args.exclude) > 0:
        for p in args.exclude:
            state["tree_exists"].add(p)

    dependencies_to_hide = (
        True
        if (
            (pkg in state["tree_exists"] and not getattr(args, "full", False))
            or (
                getattr(args, "full", False)
                and pkg in state["tree_exists"]
                and pkg in state["pkgs_with_cycles"]
            )
        )
        else False
    )
    will_create_subtree = len(e) >= 1
    if len(e) > 0:
        state["tree_exists"].add(pkg)

    if indent == 0:
        if v is not None:
            s += f"{pkg}=={v}\n"
        else:
            s += pkg
    else:
        requirement = (
            ", ".join(g.edges[prev, pkg]["version"])
            if down_search
            else ", ".join(g.edges[pkg, prev]["version"])
        )
        r = "any" if requirement == "" else requirement
        br = "└─" if is_last else "├─"
        i = ""
        for x in range(indent):
            if x == 0:
                i += " " * 2
            elif x in empty_cols:
                i += " " * TABSIZE
            else:
                i += "│" + (" " * (TABSIZE - 1))
        if v is not None:
            s += f"{i}{br} {pkg}{Style.DIM} {v} [required: {r}]{Style.RESET_ALL}\n"
        else:
            s += f"{i}{br} {pkg}{Style.DIM} [required: {r}]{Style.RESET_ALL}\n"
        if dependencies_to_hide:
            state["hidden_dependencies"] = True
            will_create_subtree = False
            if pkg not in args.exclude:
                br2 = " " if is_last else "│"
                word = "dependencies" if down_search else "dependent packages"
                s += f"{i}{br2}  {Style.DIM}└─ {word} of {pkg} displayed above{Style.RESET_ALL}\n"
        else:
            if len(e) > 0:
                state["tree_exists"].add(pkg)

    if will_create_subtree:
        state["indent"] += 1
        for pack in e:
            if state["is_last"]:
                state["empty_cols"].append(indent)
            state["is_last"] = e[-1] == pack
            tree_str, state = print_dep_tree(g, pack, pkg, state)
            s += tree_str
    if is_last and indent != 0:
        state["indent"] -= 1
        if indent in empty_cols:
            state["empty_cols"].remove(indent)
        state["is_last"] = False
    return s, state


# ── File ownership ─────────────────────────────────────────────────────────────

def get_pkg_files(prefix: str) -> set:
    """Return the set of all relative file paths tracked by installed packages."""
    pkg_files = set()
    for p in PrefixData(prefix).iter_records():
        for f in p["files"]:
            pkg_files.add(f)
    return pkg_files


def is_internal_dir(prefix: str, path: str) -> bool:
    """Return True if path is a conda-internal directory that should be skipped."""
    for t in ["pkgs", "conda-bld", "conda-meta", "locks", "envs"]:
        if path.startswith(os.path.join(prefix, t)):
            return True
    return False


def find_who_owns_file(prefix: str, target_path: str) -> None:
    """Print which package(s) own a given file path or path fragment."""
    for p in PrefixData(prefix).iter_records():
        for f in p["files"]:
            if target_path in f or f in target_path:
                print(f'{p["name"]}\t{f}')


def find_unowned_files(prefix: str) -> None:
    """Walk the prefix and print all files not tracked by any package."""
    pkg_files = get_pkg_files(prefix)
    for root, dirs, files in os.walk(prefix):
        if is_internal_dir(prefix, root):
            continue
        for f in files:
            f0 = os.path.join(root, f)
            f1 = f0.replace(prefix, "", 1).lstrip(os.sep)
            if f1 not in pkg_files:
                print(f0)


# ── Graph traversal helpers ───────────────────────────────────────────────────

def is_node_reachable(
    graph: networkx.DiGraph, source: str | list, target: str
) -> bool:
    """Return True if target is reachable from source in graph."""
    if isinstance(source, list):
        return any(is_node_reachable(graph, s, target) for s in source)
    try:
        paths = networkx.shortest_path(graph, source, target)
        return len(paths) > 0
    except (networkx.NodeNotFound, networkx.NetworkXException):
        return False


def print_pkgs(pkgs: list, with_json: bool = False) -> None:
    """Print a list of package names, optionally as JSON."""
    if with_json:
        print(json.dumps(pkgs))
    else:
        for p in pkgs:
            print(p)


def find_reachable_pkgs(
    graph: networkx.DiGraph,
    pkg: str,
    down_search: bool = True,
    exclude_pkgs: set = set(),
) -> list:
    """Return all packages reachable from (or to) pkg, respecting exclusions."""
    if down_search:
        paths = networkx.shortest_path(graph, source=pkg)
    else:
        paths = networkx.shortest_path(graph, target=pkg)

    reachable_pkgs = []
    for k, v in paths.items():
        if len(exclude_pkgs.intersection(v)) > 0 and k not in exclude_pkgs:
            pass  # drop paths passing through excluded packages
        elif k != pkg:
            reachable_pkgs.append(k)
    return reachable_pkgs


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(args: list[str] | None = None) -> None:
    """Main CLI entry point. Accepts an optional args list for programmatic use."""
    parser = argparse.ArgumentParser(
        description="conda dependency tree helper"
    )
    parser.add_argument(
        "-p",
        "--prefix",
        help="full path to environment location (i.e. prefix)",
        default=None,
    )
    parser.add_argument(
        "-n",
        "--name",
        help="name of environment",
        default=None,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="%(prog)s " + __version__,
    )

    subparser = parser.add_subparsers(dest="subcmd")

    format_args = argparse.ArgumentParser(add_help=False)
    rec_or_tree = format_args.add_mutually_exclusive_group(required=False)
    rec_or_tree.add_argument(
        "-t",
        "--tree",
        help="show dependencies of dependencies in tree form",
        action="store_true",
        default=False,
    )
    rec_or_tree.add_argument(
        "--dot",
        help="print a graphviz dot graph notation",
        action="store_true",
        default=False,
    )
    rec_or_tree.add_argument(
        "--json",
        help="print packages in json format",
        default=False,
        action="store_true",
    )

    package_cmds = argparse.ArgumentParser(add_help=False, parents=[format_args])
    package_cmds.add_argument("package", help="the target package")
    package_cmds.add_argument(
        "-r",
        "--recursive",
        help="show dependencies of dependencies",
        action="store_true",
        default=False,
    )

    hiding_cmds = argparse.ArgumentParser(add_help=False)
    hiding_cmds.add_argument(
        "--exclude",
        help=(
            "comma separated list of packages to exclude dependencies from tree, "
            "can be specified multiple times"
        ),
        default=[],
        action="append",
    )
    hiding_cmds.add_argument(
        "--small",
        help="don't include dependencies for conda and python. alias for --exclude conda,python",
        default=False,
        action="store_true",
    )
    hiding_cmds.add_argument(
        "--full",
        help="shows the complete dependency tree, with all the redundancies that it entails",
        default=False,
        action="store_true",
    )

    lv_cmd = subparser.add_parser("leaves", help="shows leaf packages")
    lv_cmd.add_argument(
        "--export",
        help="export leaves dependencies",
        default=False,
        action="store_true",
    )
    lv_cmd.add_argument(
        "--with-cycles",
        help="include orphan cycles",
        default=False,
        action="store_true",
    )
    lv_cmd.add_argument(
        "--json",
        help="print packages in json format",
        default=False,
        action="store_true",
    )

    subparser.add_parser("cycles", help="shows dependency cycles")

    subparser.add_parser(
        "whoneeds",
        help="shows packages that depends on this package",
        parents=[package_cmds, hiding_cmds],
    )
    subparser.add_parser(
        "depends",
        help="shows this package dependencies",
        parents=[package_cmds, hiding_cmds],
    )
    subparser.add_parser(
        "deptree",
        help="shows the complete dependency tree",
        parents=[format_args, hiding_cmds],
    )
    subparser.add_parser(
        "unowned-files",
        help="shows files that are not owned by any package",
    )
    subparser.add_parser(
        "who-owns",
        help="find which package owns a given file",
    ).add_argument("file", help="a file path or substring of the target file")

    parsed_args = parser.parse_args(args)

    # Resolve the environment prefix
    if parsed_args.prefix is None:
        _conda = os.environ.get("CONDA_EXE", "conda")
        _info = json.loads(
            subprocess.check_output([_conda, "info", "--json"])
        )
        if parsed_args.name is None:
            if _info["active_prefix"] is not None:
                parsed_args.prefix = _info["active_prefix"]
            else:
                parsed_args.prefix = _info["default_prefix"]
        else:
            from conda.base.context import locate_prefix_by_name
            parsed_args.prefix = locate_prefix_by_name(
                name=parsed_args.name, envs_dirs=_info["envs_dirs"]
            )

    prefix_data = get_prefix_data(parsed_args.prefix)
    g = make_cache_graph(prefix_data.iter_records())

    # ── Inner helpers ──────────────────────────────────────────────────────────

    def get_leaves(graph: networkx.DiGraph) -> list:
        return [n for n, deg in graph.in_degree() if deg == 0]

    def get_leaves_plus_cycles(graph: networkx.DiGraph) -> list:
        lv = get_leaves(graph)
        for pks in networkx.simple_cycles(g):
            if not is_node_reachable(g, lv, pks[0]):
                lv.append(pks[0])
        return lv

    def get_cycles(graph: networkx.DiGraph) -> str:
        s = ""
        for i in networkx.simple_cycles(graph):
            s += " -> ".join(i) + " -> " + i[0] + "\n"
        return s

    def pkgs_with_cycles(graph: networkx.DiGraph) -> set:
        return set(sum(networkx.simple_cycles(graph), []))

    # Default state for the recursive tree renderer
    state = {
        "down_search": True,
        "args": parsed_args,
        "indent": 0,
        "empty_cols": [],
        "is_last": False,
        "tree_exists": set(),
        "hidden_dependencies": False,
        "pkgs_with_cycles": pkgs_with_cycles(g),
    }

    # Expand comma-separated excludes for tree subcommands
    if parsed_args.subcmd in ["depends", "whoneeds", "deptree"]:
        if len(parsed_args.exclude) > 0:
            ex = []
            for i in parsed_args.exclude:
                for j in i.split(","):
                    ex.append(j)
            parsed_args.exclude = ex
        if parsed_args.small:
            parsed_args.exclude.extend(["conda", "python"])

    # ── Subcommand dispatch ────────────────────────────────────────────────────

    if parsed_args.subcmd == "cycles":
        print(get_cycles(g), end="")

    elif parsed_args.subcmd in ["depends", "whoneeds"]:
        state["down_search"] = parsed_args.subcmd == "depends"
        if parsed_args.package not in g:
            print(
                f'warning: package "{parsed_args.package}" not found',
                file=sys.stderr,
            )
            sys.exit(1)
        elif parsed_args.dot:
            e = find_reachable_pkgs(
                g,
                parsed_args.package,
                exclude_pkgs=set(parsed_args.exclude),
                down_search=state["down_search"],
            )
            print_graph_dot(g.subgraph(e + [parsed_args.package]))
        elif parsed_args.tree:
            tree, state = print_dep_tree(g, parsed_args.package, None, state)
            print(tree, end="")
        elif parsed_args.recursive:
            e = find_reachable_pkgs(
                g,
                parsed_args.package,
                exclude_pkgs=set(parsed_args.exclude),
                down_search=state["down_search"],
            )
            print_pkgs(e, with_json=parsed_args.json)
        else:
            edges = (
                g.out_edges(parsed_args.package)
                if state["down_search"]
                else g.in_edges(parsed_args.package)
            )
            e = (
                [i[1] for i in edges]
                if state["down_search"]
                else [i[0] for i in edges]
            )
            print_pkgs(e, with_json=parsed_args.json)

    elif parsed_args.subcmd == "leaves":
        if parsed_args.with_cycles:
            lv = get_leaves_plus_cycles(g)
        else:
            lv = get_leaves(g)
        if parsed_args.export:
            for pkg_name in lv:
                record = prefix_data.get(pkg_name, None)
                if record is not None:
                    print(
                        f"{record.channel.channel_name}::"
                        f"{record.name}={record.version}={record.build}"
                    )
        else:
            print_pkgs(lv, with_json=parsed_args.json)

    elif parsed_args.subcmd == "deptree":
        if parsed_args.dot:
            print_graph_dot(g, exclude_pkgs=set(parsed_args.exclude))
        elif parsed_args.json:
            print_pkgs(list(g), with_json=True)
        else:
            complete_tree = ""
            for pk in get_leaves_plus_cycles(g):
                if pk not in parsed_args.exclude:
                    tree, state = print_dep_tree(g, pk, None, state)
                    complete_tree += tree
            print("".join(complete_tree), end="")

    elif parsed_args.subcmd == "unowned-files":
        find_unowned_files(parsed_args.prefix)

    elif parsed_args.subcmd == "who-owns":
        find_who_owns_file(parsed_args.prefix, parsed_args.file)

    else:
        parser.print_help()
        sys.exit(1)

    # ── End-of-run hint messages (tree subcommands only) ───────────────────────

    if state["hidden_dependencies"] and not getattr(parsed_args, "full", False):
        print(
            f"\n{Style.DIM}For the sake of clarity, some redundancies have been hidden.\n"
            f"Please use the '--full' option to display them anyway.{Style.RESET_ALL}"
        )
        if not getattr(parsed_args, "small", False):
            print(
                f"\n{Style.DIM}If you are tired of seeing 'conda' and 'python' everywhere,\n"
                f"you can use the '--small' option to hide their dependencies completely.{Style.RESET_ALL}"
            )

    if state["hidden_dependencies"] and getattr(parsed_args, "full", False):
        print(
            f"\n{Style.DIM}The full dependency tree shows dependencies of packages "
            f"with cycles only once.{Style.RESET_ALL}"
        )


if __name__ == "__main__":
    main()
