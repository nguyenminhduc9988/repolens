"""Orchestrates a full analysis and produces the report model (plain dict, JSON-ready)."""

from __future__ import annotations

import shutil
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import __version__
from .gitstats import GitStats, collect_git_stats
from .graph import build_graph
from .health import compute_health
from .languages import extract_functions, extract_imports
from .scanner import ScanResult, scan
from .security import DEMOTED_PATHS, scan_security

HUB_THRESHOLD = 12
GIANT_LOC = 600


def analyze(target: str, excludes: Optional[List[str]] = None,
            max_files: int = 6000, keep_clone: bool = False,
            prefer_tarball: bool = False) -> Dict:
    """Analyze *target* and return the full report model."""
    scanned = scan(target, excludes=excludes, max_files=max_files,
                   prefer_tarball=prefer_tarball)
    try:
        return _build_report(scanned)
    finally:
        if scanned.cloned and not keep_clone:
            shutil.rmtree(scanned.root.parent, ignore_errors=True)


def _build_report(scanned: ScanResult) -> Dict:
    files = scanned.files
    imports = {i: extract_imports(f.language, f.text) for i, f in enumerate(files)}
    graph = build_graph(files, imports)
    findings = scan_security(files)
    # snapshot mode has no checkout on disk — churn/ownership degrade gracefully
    git = GitStats() if scanned.remote_snapshot else collect_git_stats(scanned.root)

    file_records = []
    total_functions = 0
    for i, f in enumerate(files):
        funcs = extract_functions(f.language, f.text)
        total_functions += len(funcs)
        hist = git.per_file.get(f.path)
        deps = sorted(graph.dependencies.get(i, ()))
        rdeps = sorted(graph.dependents.get(i, ()))
        file_records.append({
            "id": i,
            "path": f.path,
            "language": f.language,
            "loc": f.loc,
            "layer": graph.layers[i],
            "functions": [{"name": n, "line": ln} for n, ln in funcs[:200]],
            "imports": deps,
            "importedBy": rdeps,
            "external": graph.external.get(i, []),
            "blast": graph.blast.get(i, 0),
            "churn": hist.commits if hist else 0,
            "authors": hist.top_authors() if hist else [],
            "lastTouched": hist.last_touched if hist else None,
        })

    n = len(files)
    # orphan metric: only substantive first-party code counts — markup/data files,
    # near-empty package markers, and docs/example snippets are expected standalones
    non_graph = {"HTML", "SQL", "Shell", "PowerShell"}
    code_records = [r for r in file_records
                    if r["language"] not in non_graph and r["loc"] >= 3
                    and not DEMOTED_PATHS.search(r["path"])]
    orphans = [r for r in code_records if not r["imports"] and not r["importedBy"]]
    hubs = [r for r in file_records if len(r["imports"]) + len(r["importedBy"]) >= HUB_THRESHOLD]
    giants = [r for r in file_records if r["loc"] > GIANT_LOC]
    sev_counts = Counter(x.severity for x in findings)

    health = compute_health(
        n_files=n,
        cycles=graph.cycles,
        orphan_ratio=len(orphans) / len(code_records) if code_records else 0.0,
        hub_ratio=len(hubs) / n if n else 0.0,
        giant_ratio=len(giants) / n if n else 0.0,
        security_counts=dict(sev_counts),
    )

    languages = Counter()
    lang_loc: Counter = Counter()
    for f in files:
        languages[f.language] += 1
        lang_loc[f.language] += f.loc

    return {
        "tool": {"name": "repolens", "version": __version__},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "repo": {
            "name": scanned.name,
            "origin": scanned.origin,
            "root": None if scanned.remote_snapshot else str(scanned.root),
            "filesAnalyzed": n,
            "filesSkipped": scanned.skipped,
            "totalLoc": sum(f.loc for f in files),
            "totalFunctions": total_functions,
            "edges": len(graph.edges),
        },
        "health": {
            "score": health.score,
            "grade": health.grade,
            "penalties": health.penalties,
        },
        "languages": [
            {"name": lang, "files": cnt, "loc": lang_loc[lang]}
            for lang, cnt in languages.most_common()
        ],
        "files": file_records,
        "edges": [{"source": a, "target": b} for a, b in graph.edges],
        "cycles": [[files[i].path for i in comp] for comp in graph.cycles[:25]],
        "hubs": sorted(
            ({"path": r["path"], "in": len(r["importedBy"]), "out": len(r["imports"]),
              "blast": r["blast"]} for r in hubs),
            key=lambda x: x["in"] + x["out"], reverse=True)[:25],
        "security": [
            {"file": x.file, "line": x.line, "severity": x.severity,
             "kind": x.kind, "detail": x.detail} for x in findings[:400]
        ],
        "securitySummary": dict(sev_counts),
        "git": {
            "available": git.available,
            "commits": git.total_commits,
            "contributors": git.contributors,
            "firstCommit": git.first_commit,
            "lastCommit": git.last_commit,
        },
    }
