"""End-to-end and unit tests over a synthetic fixture repo."""

import json
import subprocess
import sys

import pytest

from repolens import analyze
from repolens.graph import build_graph, classify_layer
from repolens.health import compute_health
from repolens.languages import extract_functions, extract_imports
from repolens.scanner import SourceFile, resolve_target, scan
from repolens.security import scan_security


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory):
    """A tiny polyglot project with known structure: a cycle, a hub, a secret."""
    root = tmp_path_factory.mktemp("proj")
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "app" / "__init__.py").write_text("from .core import run\n")
    (root / "src" / "app" / "core.py").write_text(
        "import os\nfrom .util import helper\nfrom . import cycle_a\n\n"
        "def run():\n    return helper()\n\nclass Engine:\n    pass\n"
    )
    (root / "src" / "app" / "util.py").write_text(
        "def helper():\n    return 1\n\ndef unused():\n    pass\n"
    )
    (root / "src" / "app" / "cycle_a.py").write_text("from . import cycle_b\n")
    (root / "src" / "app" / "cycle_b.py").write_text("from . import cycle_a\n")
    (root / "src" / "app" / "settings.py").write_text(
        'API_KEY = "sk_live_abcdefgh12345678"\npassword = "supersecret12345"\n'
    )
    (root / "web").mkdir()
    (root / "web" / "index.js").write_text(
        "import { helper } from './lib/helper.js';\nconst x = require('./lib/other');\n"
        "function main() { helper(); }\nconst arrow = () => 2;\n"
    )
    (root / "web" / "lib").mkdir()
    (root / "web" / "lib" / "helper.js").write_text(
        "export function helper() { return eval('1+1'); }\n"
    )
    (root / "web" / "lib" / "other.js").write_text(
        "module.exports = () => { document.body.innerHTML = window.location.hash; };\n"
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text(
        "from app.core import run\n\ndef test_run():\n    assert run() == 1\n"
    )
    return root


@pytest.fixture(scope="session")
def report(fixture_repo):
    return analyze(str(fixture_repo))


# ---------- scanner ----------

def test_scan_finds_all_supported_files(fixture_repo):
    result = scan(str(fixture_repo))
    paths = {f.path for f in result.files}
    assert "src/app/core.py" in paths
    assert "web/lib/helper.js" in paths
    assert len(paths) == 10


def test_scan_respects_excludes(fixture_repo):
    result = scan(str(fixture_repo), excludes=["web/**"])
    assert not any(f.path.startswith("web/") for f in result.files)


def test_resolve_target_rejects_garbage():
    with pytest.raises(FileNotFoundError):
        resolve_target("no/such/dir/exists/here!!")


def test_resolve_target_github_shorthand():
    _, url, name = resolve_target("octocat/Hello-World")
    assert url == "https://github.com/octocat/Hello-World"
    assert name == "octocat/Hello-World"


# ---------- language extraction ----------

def test_python_functions_and_classes():
    text = "def foo():\n    pass\n\nasync def bar():\n    pass\n\nclass Baz:\n    pass\n"
    names = [n for n, _ in extract_functions("Python", text)]
    assert names == ["foo", "bar", "Baz"]


def test_js_function_variants():
    text = ("function classic() {}\nconst arrow = () => 1;\n"
            "let fn = async function() {};\nvar single = x => x;\n")
    names = {n for n, _ in extract_functions("JavaScript", text)}
    assert {"classic", "arrow", "single"} <= names


def test_python_type_checking_imports_ignored():
    text = ("from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    from app.core import Engine\n"
            "import os\n")
    specs = extract_imports("Python", text)
    assert "os" in specs and "typing.TYPE_CHECKING" in specs
    assert not any(s.startswith("app.core") for s in specs)


def test_python_function_body_imports_ignored():
    text = "def lazy():\n    import json\n    return json\nimport sys\n"
    assert extract_imports("Python", text) == ["sys"]


# ---------- graph ----------

def test_graph_edges_and_cycle(report):
    by_path = {f["path"]: f for f in report["files"]}
    core = by_path["src/app/core.py"]
    util = by_path["src/app/util.py"]
    assert util["id"] in core["imports"]
    assert len(report["cycles"]) == 1
    assert set(report["cycles"][0]) == {"src/app/cycle_a.py", "src/app/cycle_b.py"}


def test_src_layout_resolution(report):
    """tests/test_core.py imports app.core → must resolve through src/ prefix."""
    by_path = {f["path"]: f for f in report["files"]}
    test_file = by_path["tests/test_core.py"]
    core = by_path["src/app/core.py"]
    assert core["id"] in test_file["imports"]


def test_js_relative_and_index_resolution(report):
    by_path = {f["path"]: f for f in report["files"]}
    index = by_path["web/index.js"]
    assert by_path["web/lib/helper.js"]["id"] in index["imports"]
    assert by_path["web/lib/other.js"]["id"] in index["imports"]


def test_blast_radius(report):
    by_path = {f["path"]: f for f in report["files"]}
    util = by_path["src/app/util.py"]
    # util ← core ← __init__, and core ← test_core: blast ≥ 3
    assert util["blast"] >= 3


def test_layers():
    assert classify_layer("src/components/Button.tsx") == "UI"
    assert classify_layer("tests/test_x.py") == "Tests"
    assert classify_layer("app/models/user.py") == "Data"
    assert classify_layer("anything/else.py") in ("Core", "Services")


def test_empty_graph():
    g = build_graph([], {})
    assert g.edges == [] and g.cycles == []


# ---------- security ----------

def test_security_findings(report):
    kinds = {(s["kind"], s["file"]) for s in report["security"]}
    assert ("Hardcoded secret", "src/app/settings.py") in kinds
    assert ("eval() usage", "web/lib/helper.js") in kinds
    assert ("innerHTML assignment", "web/lib/other.js") in kinds


def test_security_demotes_test_paths():
    f = SourceFile(path="tests/fixtures/x.py", language="Python",
                   text='password = "hunter2hunter2ha"\n', loc=1)
    findings = scan_security([f])
    assert findings and findings[0].severity == "warning"


# ---------- health ----------

def test_health_perfect():
    h = compute_health(n_files=10, cycles=[], orphan_ratio=0, hub_ratio=0,
                       giant_ratio=0, security_counts={})
    assert h.score == 100 and h.grade == "A" and not h.penalties


def test_health_bounded():
    h = compute_health(n_files=10, cycles=[[1, 2]] * 20, orphan_ratio=1.0,
                       hub_ratio=1.0, giant_ratio=1.0,
                       security_counts={"critical": 99, "serious": 99, "warning": 99})
    assert 0 <= h.score < 40 and h.grade == "F"


def test_report_grade_reflects_problems(report):
    assert report["health"]["score"] < 100
    labels = {p["label"] for p in report["health"]["penalties"]}
    assert "Circular dependencies" in labels
    assert "Security findings" in labels


# ---------- html + cli ----------

def test_html_report_self_contained(report):
    from repolens.htmlreport import render_html
    html = render_html(report)
    assert "d3.v7" in html or "d3js.org" in html  # d3 inlined
    assert report["repo"]["name"] in html
    assert "https://cdn" not in html  # no external requests
    # embedded data survives round-trip
    import re as _re
    blob = _re.search(r'application/json">(.*?)</script>', html, _re.S).group(1)
    assert json.loads(blob.replace("<\\/", "</"))["repo"]["name"] == report["repo"]["name"]


def test_cli_end_to_end(fixture_repo, tmp_path):
    out = tmp_path / "r.html"
    jout = tmp_path / "r.json"
    proc = subprocess.run(
        [sys.executable, "-m", "repolens", str(fixture_repo), "-o", str(out),
         "--json", str(jout), "--no-open", "-q"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.stat().st_size > 100_000
    data = json.loads(jout.read_text())
    assert data["repo"]["filesAnalyzed"] == 10


def test_cli_bad_target():
    proc = subprocess.run(
        [sys.executable, "-m", "repolens", "definitely/not@a$repo", "--no-open", "-q"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    assert "neither" in proc.stderr


def test_tar_stream_scan():
    import io
    import tarfile

    from repolens.scanner import DEFAULT_EXCLUDES, MAX_FILE_BYTES, _scan_tar_stream

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        def add(name, data):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        add("repo-abc123/src/app.py", b"import os\nx = 1\n")
        add("repo-abc123/src/util.py", b"from . import app\n")
        add("repo-abc123/node_modules/dep/index.js", b"module.exports = 1\n")  # excluded dir
        add("repo-abc123/README.md", b"# hi\n")                                # unsupported lang
        add("repo-abc123/big.py", b"x" * (MAX_FILE_BYTES + 1))                 # over per-file cap
    buf.seek(0)

    result = _scan_tar_stream(buf, "repo", "https://github.com/o/repo",
                              list(DEFAULT_EXCLUDES), max_files=100)
    paths = sorted(f.path for f in result.files)
    assert paths == ["src/app.py", "src/util.py"]
    assert result.skipped == 1          # the oversized file
    assert result.remote_snapshot and not result.cloned


def test_tar_stream_max_files_cap():
    import io
    import tarfile

    from repolens.scanner import _scan_tar_stream

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for i in range(10):
            data = b"x = 1\n"
            info = tarfile.TarInfo(name=f"r-sha/{i}.py")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    buf.seek(0)
    result = _scan_tar_stream(buf, "r", None, [], max_files=3)
    assert len(result.files) == 3
