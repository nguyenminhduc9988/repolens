"""Collect source files from a local directory or a freshly cloned GitHub repo."""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .languages import language_for

DEFAULT_EXCLUDES = [
    ".git", "node_modules", "vendor", "dist", "build", "out", "target",
    "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", "coverage", ".next", ".nuxt", ".svelte-kit", ".cache",
    "site-packages", "bower_components", ".idea", ".vscode", "*.min.js",
    "*.min.css", "*.map", "*.lock", "*.svg", "*.snap", ".terraform",
    "Pods", "DerivedData", "cmake-build-*", "*.bundle.js", "*.chunk.js",
]

MAX_FILE_BYTES = 1_500_000  # skip generated monsters
GITHUB_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"
)


@dataclass
class SourceFile:
    path: str            # repo-relative, forward slashes
    language: str
    text: str
    loc: int = 0


@dataclass
class ScanResult:
    root: Path
    name: str
    files: List[SourceFile] = field(default_factory=list)
    skipped: int = 0
    cloned: bool = False
    origin: Optional[str] = None   # github url when cloned


def _is_excluded(rel_path: str, patterns: List[str]) -> bool:
    parts = rel_path.split("/")
    base = parts[-1]
    for pat in patterns:
        if "/" in pat or "*" in pat:
            if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(base, pat):
                return True
            # allow dir-style patterns like "docs/**"
            if pat.endswith("/**") and rel_path.startswith(pat[:-3].rstrip("/") + "/"):
                return True
        if pat in parts:
            return True
    return False


def resolve_target(target: str) -> "tuple[Path, Optional[str], str]":
    """Turn CLI target into (local_path, github_url, display_name).

    Accepts a local path, ``owner/repo`` shorthand, or a full GitHub URL.
    """
    p = Path(target).expanduser()
    if p.exists():
        root = p.resolve()
        return root, None, root.name or str(root)
    m = GITHUB_RE.match(target.strip())
    if m and target not in (".", ".."):
        owner, repo = m.group("owner"), m.group("repo")
        return Path(), f"https://github.com/{owner}/{repo}", f"{owner}/{repo}"
    raise FileNotFoundError(
        f"'{target}' is neither an existing path nor a GitHub repo (owner/repo or URL)"
    )


def clone_github(url: str) -> Path:
    """Shallow-clone *url* into a temp dir and return the checkout path."""
    tmp = Path(tempfile.mkdtemp(prefix="repolens-"))
    cmd = ["git", "clone", "--depth", "200", "--single-branch", url, str(tmp / "repo")]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("git is required to clone GitHub repos but was not found in PATH")
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"git clone of {url} timed out after 600s")
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {proc.stderr.strip().splitlines()[-1:] or 'unknown error'}")
    return tmp / "repo"


def scan(target: str, excludes: Optional[List[str]] = None, max_files: int = 6000) -> ScanResult:
    """Scan *target* (path, owner/repo, or GitHub URL) and load supported source files."""
    root, github_url, name = resolve_target(target)
    cloned = False
    if github_url:
        root = clone_github(github_url)
        cloned = True

    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    result = ScanResult(root=root, name=name, cloned=cloned, origin=github_url)

    if root.is_file():
        candidates = [root]
        base = root.parent
    else:
        base = root
        candidates = []
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = [
                d for d in sorted(dirnames)
                if not _is_excluded((rel_dir + "/" + d).lstrip("/"), patterns)
            ]
            for fn in sorted(filenames):
                candidates.append(Path(dirpath) / fn)

    for idx, fp in enumerate(candidates):
        rel = fp.relative_to(base).as_posix()
        if _is_excluded(rel, patterns):
            continue
        lang = language_for(rel)
        if not lang:
            continue
        try:
            size = fp.stat().st_size
            if size > MAX_FILE_BYTES:
                result.skipped += 1
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            result.skipped += 1
            continue
        loc = sum(1 for line in text.splitlines() if line.strip())
        result.files.append(SourceFile(path=rel, language=lang, text=text, loc=loc))
        if len(result.files) >= max_files:
            result.skipped += max(0, len(candidates) - idx - 1)
            break

    return result
