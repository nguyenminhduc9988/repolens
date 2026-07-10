"""Rich terminal rendering of a report model."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

GRADE_STYLE = {
    "A": "bold white on green4",
    "B": "bold white on dark_cyan",
    "C": "bold black on yellow3",
    "D": "bold white on dark_orange3",
    "F": "bold white on red3",
}
SEV_STYLE = {"critical": "red3", "serious": "dark_orange3", "warning": "yellow3", "info": "grey58"}

BAR_CHARS = 24


def _bar(fraction: float, color: str) -> Text:
    filled = round(max(0.0, min(1.0, fraction)) * BAR_CHARS)
    t = Text()
    t.append("█" * filled, style=color)
    t.append("░" * (BAR_CHARS - filled), style="grey35")
    return t


def render_terminal(report: Dict, html_path: Optional[Path] = None) -> None:
    console = Console()
    repo, health = report["repo"], report["health"]

    # ── header ────────────────────────────────────────────────────────────
    grade = health["grade"]
    title = Text()
    title.append("  repolens ", style="bold bright_magenta")
    title.append("· ", style="grey58")
    title.append(repo["name"], style="bold white")
    badge = Text(f"  {grade}  ", style=GRADE_STYLE.get(grade, "bold"))
    head = Table.grid(expand=True)
    head.add_column(justify="left")
    head.add_column(justify="right")
    head.add_row(title, Text.assemble(badge, (f"  {health['score']}/100 ", "bold")))
    console.print()
    console.print(Panel(head, box=box.HEAVY, border_style="bright_magenta"))

    # ── stat tiles ────────────────────────────────────────────────────────
    def tile(label: str, value: str) -> Panel:
        return Panel(Text.assemble((value + "\n", "bold bright_white"), (label, "grey62")),
                     box=box.ROUNDED, border_style="grey35", padding=(0, 2))

    git = report["git"]
    tiles = [
        tile("files", f"{repo['filesAnalyzed']:,}"),
        tile("lines of code", f"{repo['totalLoc']:,}"),
        tile("functions", f"{repo['totalFunctions']:,}"),
        tile("dependency edges", f"{repo['edges']:,}"),
        tile("cycles", f"{len(report['cycles']):,}"),
    ]
    if git["available"]:
        tiles.append(tile("contributors", f"{git['contributors']:,}"))
    console.print(Columns(tiles, equal=False, expand=False))

    # ── languages ─────────────────────────────────────────────────────────
    langs = report["languages"][:8]
    if langs:
        total_loc = sum(x["loc"] for x in report["languages"]) or 1
        lt = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        lt.add_column(style="bold", min_width=12)
        lt.add_column(min_width=BAR_CHARS)
        lt.add_column(justify="right", style="grey62")
        palette = ["dodger_blue2", "spring_green3", "orange3", "green4",
                   "medium_purple2", "indian_red", "hot_pink3", "dark_orange3"]
        for i, lang in enumerate(langs):
            frac = lang["loc"] / total_loc
            lt.add_row(lang["name"], _bar(frac, palette[i % len(palette)]),
                       f"{lang['loc']:,} loc · {lang['files']} files")
        console.print(Panel(lt, title="[bold]Languages", border_style="grey35", box=box.ROUNDED))

    # ── health breakdown ──────────────────────────────────────────────────
    if health["penalties"]:
        ht = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        ht.add_column(style="bold", min_width=24)
        ht.add_column(justify="right", style="red3", min_width=5)
        ht.add_column(style="grey62")
        for p in health["penalties"]:
            ht.add_row(p["label"], f"-{p['points']}", p["detail"])
        console.print(Panel(ht, title="[bold]Health breakdown",
                            border_style="grey35", box=box.ROUNDED))

    # ── blast radius / hubs ───────────────────────────────────────────────
    top_blast = sorted(report["files"], key=lambda r: r["blast"], reverse=True)[:8]
    if top_blast and top_blast[0]["blast"] > 0:
        n = repo["filesAnalyzed"] or 1
        bt = Table(box=box.SIMPLE, padding=(0, 1))
        bt.add_column("file", style="bold", overflow="fold")
        bt.add_column("blast", min_width=BAR_CHARS)
        bt.add_column("impact", justify="right", style="grey62")
        for r in top_blast:
            if r["blast"] == 0:
                continue
            bt.add_row(r["path"], _bar(r["blast"] / n, "dark_orange3"),
                       f"{r['blast']} files ({r['blast'] / n:.0%})")
        console.print(Panel(bt, title="[bold]Blast radius — change these, feel it everywhere",
                            border_style="grey35", box=box.ROUNDED))

    # ── hotspots (churn) ──────────────────────────────────────────────────
    if git["available"]:
        hot = sorted((r for r in report["files"] if r["churn"]),
                     key=lambda r: r["churn"], reverse=True)[:8]
        if hot:
            peak = hot[0]["churn"] or 1
            ct = Table(box=box.SIMPLE, padding=(0, 1))
            ct.add_column("file", style="bold", overflow="fold")
            ct.add_column("churn", min_width=BAR_CHARS)
            ct.add_column("commits", justify="right", style="grey62")
            for r in hot:
                owners = ", ".join(r["authors"][:2])
                ct.add_row(r["path"], _bar(r["churn"] / peak, "hot_pink3"),
                           f"{r['churn']}  ·  {owners}")
            console.print(Panel(ct, title="[bold]Hotspots — most-changed files",
                                border_style="grey35", box=box.ROUNDED))

    # ── security ──────────────────────────────────────────────────────────
    sev = report["securitySummary"]
    if sev:
        st = Table(box=box.SIMPLE, padding=(0, 1))
        st.add_column("sev", min_width=8)
        st.add_column("finding", style="bold")
        st.add_column("where", style="grey62", overflow="fold")
        shown = 0
        for x in report["security"]:
            if x["severity"] == "info":
                continue
            st.add_row(Text(x["severity"], style=SEV_STYLE[x["severity"]]),
                       x["kind"], f"{x['file']}:{x['line']}")
            shown += 1
            if shown >= 10:
                break
        info_n = sev.get("info", 0)
        subtitle = f"{info_n} info-level findings not shown" if info_n else None
        if shown:
            console.print(Panel(st, title="[bold]Security scan", subtitle=subtitle,
                                border_style="grey35", box=box.ROUNDED))
        elif info_n:
            console.print(Text(f"  security: only {info_n} info-level findings (debug statements)",
                               style="grey62"))

    # ── cycles ────────────────────────────────────────────────────────────
    if report["cycles"]:
        body = Text()
        for comp in report["cycles"][:5]:
            body.append("  ⟳ ", style="red3")
            body.append("  →  ".join(comp[:6]) + ("  → …" if len(comp) > 6 else ""), style="white")
            body.append("\n")
        console.print(Panel(body, title=f"[bold]Circular dependencies ({len(report['cycles'])})",
                            border_style="red3", box=box.ROUNDED))

    # ── footer ────────────────────────────────────────────────────────────
    if html_path:
        console.print(Panel(
            Text.assemble(("Interactive report → ", "grey62"),
                          (str(html_path), "bold bright_cyan underline")),
            box=box.HEAVY, border_style="bright_cyan"))
    console.print()
