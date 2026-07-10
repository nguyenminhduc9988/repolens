"""Command-line interface: `repolens <path | owner/repo | github url>`."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .analyzer import analyze
from .htmlreport import render_html
from .terminal import render_terminal


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repolens",
        description="X-ray any codebase in one command: dependency graph, blast radius, "
                    "health grade, security scan, and hotspots — in a single HTML file.",
        epilog="examples:\n"
               "  repolens .                        analyze current directory\n"
               "  repolens ~/code/myapp             analyze a local project\n"
               "  repolens facebook/react           shallow-clone & analyze a GitHub repo\n"
               "  repolens . -o report.html --json  also dump the raw model as JSON\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("target", nargs="?", default=".",
                   help="local path, owner/repo shorthand, or GitHub URL (default: .)")
    p.add_argument("-o", "--output", metavar="FILE",
                   help="HTML report path (default: <name>-repolens.html in cwd)")
    p.add_argument("--json", nargs="?", const="-", metavar="FILE",
                   help="write the raw analysis model as JSON (to FILE, or stdout with no value)")
    p.add_argument("-x", "--exclude", action="append", default=[], metavar="PATTERN",
                   help="extra exclude glob (repeatable), e.g. -x 'docs/**' -x '*.gen.ts'")
    p.add_argument("--max-files", type=int, default=6000,
                   help="cap on number of analyzed files (default: 6000)")
    p.add_argument("--no-open", action="store_true",
                   help="do not open the HTML report in a browser")
    p.add_argument("--no-html", action="store_true",
                   help="terminal summary only, skip the HTML report")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the terminal summary")
    p.add_argument("--version", action="version", version=f"repolens {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        report = analyze(args.target, excludes=args.exclude, max_files=args.max_files)
    except FileNotFoundError as e:
        print(f"repolens: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"repolens: {e}", file=sys.stderr)
        return 1

    if report["repo"]["filesAnalyzed"] == 0:
        print("repolens: no supported source files found (check excludes?)", file=sys.stderr)
        return 1

    html_path = None
    if not args.no_html:
        name = report["repo"]["name"].replace("/", "-")
        html_path = Path(args.output or f"{name}-repolens.html").resolve()
        html_path.write_text(render_html(report), encoding="utf-8")

    if not args.quiet:
        render_terminal(report, html_path)

    if args.json:
        payload = json.dumps(report, indent=2)
        if args.json == "-":
            print(payload)
        else:
            Path(args.json).write_text(payload, encoding="utf-8")

    if html_path and not args.no_open:
        try:
            webbrowser.open(html_path.as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
