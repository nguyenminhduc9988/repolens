"""Render the report model into a single self-contained HTML file."""

from __future__ import annotations

import html as htmlmod
import json
from importlib import resources
from typing import Dict


def _asset(name: str) -> str:
    return (resources.files("repolens") / "assets" / name).read_text(encoding="utf-8")


def render_html(report: Dict) -> str:
    template = _asset("template.html")
    d3 = _asset("d3.v7.min.js")
    # `</script>`-safe JSON embedding
    data = json.dumps(report, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("__TITLE__", htmlmod.escape(report["repo"]["name"]))
    html = html.replace("<script>/*__D3__*/</script>", f"<script>{d3}</script>")
    html = html.replace("__DATA__", data)
    return html
