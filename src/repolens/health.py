"""Health score: 0-100 plus an A-F grade, with a transparent penalty breakdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Health:
    score: int = 100
    grade: str = "A"
    penalties: List[Dict] = field(default_factory=list)  # {label, points, detail}


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def compute_health(*, n_files: int, cycles: List[List[int]], orphan_ratio: float,
                   hub_ratio: float, giant_ratio: float,
                   security_counts: Dict[str, int]) -> Health:
    h = Health()
    if n_files == 0:
        return h

    def penalize(points: float, label: str, detail: str) -> None:
        pts = round(points)
        if pts <= 0:
            return
        h.penalties.append({"label": label, "points": pts, "detail": detail})
        h.score -= pts

    in_cycles = sum(len(c) for c in cycles)
    penalize(min(15, len(cycles) * 4 + in_cycles * 0.4),
             "Circular dependencies",
             f"{len(cycles)} cycle group(s) touching {in_cycles} files")
    penalize(min(12, orphan_ratio * 30),
             "Disconnected files",
             f"{orphan_ratio:.0%} of code files have no resolved imports in either direction")
    penalize(min(10, hub_ratio * 50),
             "High coupling",
             f"{hub_ratio:.0%} of files are hubs (fan-in + fan-out ≥ 12)")
    penalize(min(12, giant_ratio * 60),
             "Oversized files",
             f"{giant_ratio:.0%} of files exceed 600 lines of code")
    crit = security_counts.get("critical", 0)
    ser = security_counts.get("serious", 0)
    warn = security_counts.get("warning", 0)
    penalize(min(25, crit * 8 + ser * 3 + warn * 1),
             "Security findings",
             f"{crit} critical, {ser} serious, {warn} warnings")

    h.score = max(0, min(100, h.score))
    h.grade = _grade(h.score)
    return h
