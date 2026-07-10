"""Dependency graph: import resolution, cycles, blast radius, layers."""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .languages import RESOLVE_SUFFIXES
from .scanner import SourceFile

LAYER_RULES = [
    ("Tests", ("test", "tests", "spec", "specs", "__tests__", "fixtures")),
    ("UI", ("components", "component", "views", "pages", "screens", "ui", "widgets",
            "templates", "layouts", "frontend")),
    ("API", ("api", "routes", "controllers", "endpoints", "handlers", "graphql", "rest")),
    ("Services", ("services", "service", "usecases", "workers", "jobs", "tasks",
                  "managers", "core", "engine", "backend")),
    ("Data", ("models", "model", "schemas", "schema", "entities", "db", "database",
              "migrations", "repositories", "store", "stores", "state")),
    ("Utils", ("utils", "util", "helpers", "helper", "lib", "libs", "common",
               "shared", "tools", "misc")),
    ("Config", ("config", "configs", "settings", "env", "scripts", "ci", "deploy",
                "infra", "docker")),
]


def classify_layer(path: str) -> str:
    parts = [p.lower() for p in path.split("/")]
    stem = parts[-1].rsplit(".", 1)[0]
    for layer, keywords in LAYER_RULES:
        for kw in keywords:
            if kw in parts[:-1] or stem == kw or stem.endswith("_" + kw) or stem.endswith("." + kw):
                return layer
    if "test" in parts[-1] or parts[-1].startswith("test_") or ".test." in parts[-1] or ".spec." in parts[-1]:
        return "Tests"
    return "Core"


@dataclass
class GraphResult:
    edges: List[Tuple[int, int]] = field(default_factory=list)        # (from, to) file indices
    external: Dict[int, List[str]] = field(default_factory=dict)      # unresolved imports per file
    dependents: Dict[int, Set[int]] = field(default_factory=dict)     # reverse adjacency
    dependencies: Dict[int, Set[int]] = field(default_factory=dict)   # forward adjacency
    cycles: List[List[int]] = field(default_factory=list)             # SCCs with len > 1
    blast: Dict[int, int] = field(default_factory=dict)               # transitive dependent count
    layers: Dict[int, str] = field(default_factory=dict)


def _index_files(files: List[SourceFile]) -> Dict[str, int]:
    return {f.path: i for i, f in enumerate(files)}


_STRIP_PREFIXES = ("src/", "lib/", "source/", "packages/")


def _module_index(files: List[SourceFile]) -> Dict[str, List[int]]:
    """Map dotted/slashed module names (and basenames) to candidate file indices."""
    idx: Dict[str, List[int]] = defaultdict(list)
    for i, f in enumerate(files):
        no_ext = f.path.rsplit(".", 1)[0]
        variants = {no_ext}
        for prefix in _STRIP_PREFIXES:
            if no_ext.startswith(prefix):
                variants.add(no_ext[len(prefix):])  # src-layout: src/pkg/x → pkg/x
        keys = set()
        for v in variants:
            keys.add(v)
            keys.add(v.replace("/", "."))
            base = v.split("/")[-1]
            if base == "__init__":
                pkg = v.rsplit("/", 1)[0] if "/" in v else v
                keys.add(pkg)
                keys.add(pkg.replace("/", "."))
            elif base in ("index", "mod", "init"):
                if "/" in v:
                    keys.add(v.rsplit("/", 1)[0])
            else:
                # every trailing path suffix, so fully-qualified names
                # (java/kotlin/c#/go module paths) match at directory boundaries:
                # a/b/c/D → D, c/D, b/c/D, …
                parts = v.split("/")
                for k in range(1, min(len(parts), 10) + 1):
                    keys.add("/".join(parts[-k:]))
        for k in keys:
            idx[k].append(i)
    return idx


_TESTY_PART = re.compile(r"(^|/)(tests?|__tests__|specs?|fixtures|examples?|mocks?|docs?)(/|$)")

# languages whose imports are fully-qualified names ending in the unit itself
# (class/module) — resolved by matching path suffixes, not by trimming the tail
FQN_LANGS = {"Java", "Kotlin", "Scala", "Groovy", "C#", "Swift", "PHP",
             "Haskell", "Julia", "Perl", "Elixir"}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _snake(segment: str) -> str:
    return _CAMEL.sub("_", segment).lower()


def _pick(cands: List[int], files: List[SourceFile], src_id: Optional[int]) -> Optional[int]:
    """Choose among ambiguous candidates; None when no clear winner."""
    cands = [c for c in set(cands) if c != src_id]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]

    def score(j: int) -> int:
        path = files[j].path
        base = path.rsplit("/", 1)[-1]
        s = 0
        if base.startswith(("__init__.", "index.", "mod.")):
            s += 4  # a package/module root beats a stray same-named file
        if path.startswith(_STRIP_PREFIXES):
            s += 2  # src-layout roots are the installable package
        if _TESTY_PART.search(path):
            s -= 3  # fixtures/examples rarely the target of absolute imports
        return s

    ranked = sorted(cands, key=score, reverse=True)
    if score(ranked[0]) > score(ranked[1]):
        return ranked[0]
    return None


def _resolve(spec: str, src: SourceFile, files: List[SourceFile], path_index: Dict[str, int],
             module_index: Dict[str, List[int]]) -> Optional[int]:
    """Resolve an import specifier to a file index within the repo, else None."""
    spec = spec.strip().strip(";")
    src_id = path_index.get(src.path)
    src_dir = posixpath.dirname(src.path)
    suffixes = RESOLVE_SUFFIXES.get(src.language, [""])

    def try_path(candidate: str) -> Optional[int]:
        candidate = posixpath.normpath(candidate).lstrip("./")
        if candidate in path_index:
            return path_index[candidate]
        for suf in suffixes:
            hit = path_index.get(posixpath.normpath(candidate + suf))
            if hit is not None:
                return hit
        return None

    # 1. Relative path imports ('./x', '../y', 'sub/z.h', require_relative)
    if spec.startswith("."):
        if src.language == "Python":
            # from .a.b import c  → dots then dotted path
            stripped = spec.lstrip(".")
            up = len(spec) - len(stripped) - 1
            base = src_dir
            for _ in range(up):
                base = posixpath.dirname(base)
            # `from .core import run` arrives as ".core.run" — walk segments back
            # until something resolves (submodule first, then parent package)
            parts = stripped.split(".") if stripped else []
            while True:
                rel = "/".join(parts)
                hit = try_path(posixpath.join(base, rel) if rel else base)
                if hit is not None or not parts:
                    return hit
                parts = parts[:-1]
        return try_path(posixpath.join(src_dir, spec))
    def suffix_probe(slashed: str) -> Optional[int]:
        # longest path-suffix match first: a/b/C → b/C → C
        parts = [p for p in slashed.split("/") if p]
        for start in range(len(parts)):
            hit = _pick(module_index.get("/".join(parts[start:]), []), files, src_id)
            if hit is not None:
                return hit
        return None

    if "/" in spec and not spec.startswith(("@", "http")):
        hit = try_path(posixpath.join(src_dir, spec)) or try_path(spec)
        if hit is not None:
            return hit
        # go module paths / monorepo absolute imports: longest suffix wins
        return suffix_probe(spec)

    # 2. Dotted module names (python, java, kotlin, c#, php namespaces, perl)
    dotted = spec.replace("\\", ".").replace("::", ".").strip(".")
    if dotted.endswith(".*"):                    # java/kotlin wildcard → the package
        dotted = dotted[:-2]
    for probe in (dotted, dotted.replace(".", "/")):
        hit = _pick(module_index.get(probe, []), files, src_id)
        if hit is not None:
            return hit

    if src.language in FQN_LANGS:
        # fully-qualified name: the unit is the LAST segment — match path
        # suffixes, dropping leading namespace segments that aren't on disk
        hit = suffix_probe(dotted.replace(".", "/"))
        if hit is None and "." in dotted:              # static import: com.x.Z.member → com.x.Z
            hit = suffix_probe(dotted.rsplit(".", 1)[0].replace(".", "/"))
        if hit is None and src.language == "Elixir":   # MyApp.Repo → my_app/repo
            hit = suffix_probe("/".join(_snake(p) for p in dotted.split(".")))
        return hit

    # python-style: progressively drop trailing segments: a.b.c → a/b/c.py, a/b.py
    parts = dotted.split(".")
    while len(parts) > 1:
        parts = parts[:-1]
        cands = module_index.get("/".join(parts), []) or module_index.get(".".join(parts), [])
        hit = _pick(cands, files, src_id)
        if hit is not None:
            return hit
    return None


def build_graph(files: List[SourceFile], imports: Dict[int, List[str]]) -> GraphResult:
    """Resolve *imports* (file index → raw specifiers) into a dependency graph."""
    g = GraphResult()
    path_index = _index_files(files)
    module_index = _module_index(files)

    seen_edges: Set[Tuple[int, int]] = set()
    for i, f in enumerate(files):
        g.dependencies.setdefault(i, set())
        g.dependents.setdefault(i, set())
        g.layers[i] = classify_layer(f.path)
        ext: List[str] = []
        for spec in imports.get(i, []):
            j = _resolve(spec, f, files, path_index, module_index)
            if j is None or j == i:
                if j is None:
                    ext.append(spec)
                continue
            if (i, j) not in seen_edges:
                seen_edges.add((i, j))
                g.edges.append((i, j))
                g.dependencies[i].add(j)
                g.dependents.setdefault(j, set()).add(i)
        if ext:
            g.external[i] = sorted(set(ext))[:30]

    g.cycles = _sccs(len(files), g.dependencies)
    g.blast = _blast_radius(len(files), g.dependents)
    return g


def _sccs(n: int, adj: Dict[int, Set[int]]) -> List[List[int]]:
    """Iterative Tarjan; return strongly connected components of size > 1."""
    index = [0]
    idx = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack: List[int] = []
    result: List[List[int]] = []

    for root in range(n):
        if idx[root] != -1:
            continue
        work = [(root, iter(sorted(adj.get(root, ()))))]
        idx[root] = low[root] = index[0]
        index[0] += 1
        stack.append(root)
        on_stack[root] = True
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if idx[w] == -1:
                    idx[w] = low[w] = index[0]
                    index[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, iter(sorted(adj.get(w, ())))))
                    advanced = True
                    break
                elif on_stack[w]:
                    low[v] = min(low[v], idx[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
            if low[v] == idx[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    result.append(sorted(comp))
    result.sort(key=len, reverse=True)
    return result


def _blast_radius(n: int, dependents: Dict[int, Set[int]]) -> Dict[int, int]:
    """For each node, count transitive dependents (files that would feel a change)."""
    blast: Dict[int, int] = {}
    for start in range(n):
        seen: Set[int] = set()
        frontier = list(dependents.get(start, ()))
        while frontier:
            v = frontier.pop()
            if v in seen or v == start:
                continue
            seen.add(v)
            frontier.extend(dependents.get(v, ()))
        blast[start] = len(seen)
    return blast
