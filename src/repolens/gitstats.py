"""Git history mining: per-file churn, ownership, and recency. Degrades to empty stats."""

from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

MAX_COMMITS = 3000


@dataclass
class FileHistory:
    commits: int = 0
    authors: Counter = field(default_factory=Counter)
    last_touched: Optional[str] = None  # ISO date

    def top_authors(self, n: int = 3) -> List[str]:
        return [a for a, _ in self.authors.most_common(n)]


@dataclass
class GitStats:
    available: bool = False
    total_commits: int = 0
    contributors: int = 0
    first_commit: Optional[str] = None
    last_commit: Optional[str] = None
    per_file: Dict[str, FileHistory] = field(default_factory=dict)


def collect_git_stats(root: Path) -> GitStats:
    stats = GitStats()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", f"--max-count={MAX_COMMITS}",
             "--name-only", "--no-renames", "--date=short",
             "--format=%x01%an%x02%ad"],
            capture_output=True, text=True, timeout=120, errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return stats
    if proc.returncode != 0 or not proc.stdout.strip():
        return stats

    stats.available = True
    per_file: Dict[str, FileHistory] = defaultdict(FileHistory)
    all_authors: set = set()
    author = date = None

    for line in proc.stdout.splitlines():
        if line.startswith("\x01"):
            author, _, date = line[1:].partition("\x02")
            stats.total_commits += 1
            all_authors.add(author)
            if stats.last_commit is None:
                stats.last_commit = date
            stats.first_commit = date
        elif line.strip() and author is not None:
            h = per_file[line.strip()]
            h.commits += 1
            h.authors[author] += 1
            if h.last_touched is None:
                h.last_touched = date

    stats.per_file = dict(per_file)
    stats.contributors = len(all_authors)
    return stats
