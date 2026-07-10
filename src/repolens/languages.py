"""Language registry: extension mapping plus per-language import and function extraction."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

EXTENSIONS: Dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".lua": "Lua",
    ".r": "R",
    ".R": "R",
    ".jl": "Julia",
    ".dart": "Dart",
    ".pl": "Perl",
    ".pm": "Perl",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".fs": "F#",
    ".fsx": "F#",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".cljc": "Clojure",
    ".elm": "Elm",
    ".zig": "Zig",
    ".nim": "Nim",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
}

# Extensions a bare module specifier may resolve to, tried in order.
RESOLVE_SUFFIXES: Dict[str, List[str]] = {
    "Python": [".py", "/__init__.py"],
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", "/index.js", "/index.jsx",
                   "/index.ts", "/index.tsx", ".vue", ".svelte", ".json"],
    "TypeScript": [".ts", ".tsx", ".js", ".jsx", ".mts", "/index.ts", "/index.tsx",
                   "/index.js", ".vue", ".svelte", ".json"],
    "Vue": [".js", ".ts", ".vue", "/index.js", "/index.ts"],
    "Svelte": [".js", ".ts", ".svelte", "/index.js", "/index.ts"],
    "Ruby": [".rb"],
    "PHP": [".php"],
    "C": [".h", ".c"],
    "C++": [".hpp", ".hh", ".hxx", ".h", ".cpp"],
    "Rust": [".rs", "/mod.rs"],
    "Go": [".go"],
    "Shell": [".sh", ".bash"],
    "Lua": [".lua", "/init.lua"],
}

# --- Import extraction -------------------------------------------------------
# Each entry: list of regexes whose first non-None group is the raw import specifier.

IMPORT_PATTERNS: Dict[str, List[re.Pattern]] = {
    "Python": [],  # handled by _python_imports (needs from-import name expansion)
    "JavaScript": [
        re.compile(r"""import\s+(?:[\w${},*\s]+\s+from\s+)?['"]([^'"]+)['"]"""),
        re.compile(r"""export\s+(?:[\w${},*\s]+\s+)?from\s+['"]([^'"]+)['"]"""),
        re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
        re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    ],
    "Java": [re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)],
    "Go": [
        re.compile(r'^\s*import\s+(?:\w+\s+)?"([^"]+)"', re.M),
        re.compile(r'^\s*(?:\w+\s+)?"([^"]+)"\s*$', re.M),  # inside import ( ... ) blocks
    ],
    "Ruby": [
        re.compile(r"""^\s*require_relative\s+['"]([^'"]+)['"]""", re.M),
        re.compile(r"""^\s*require\s+['"]([^'"]+)['"]""", re.M),
    ],
    "PHP": [
        re.compile(r"^\s*use\s+([\w\\]+)", re.M),
        re.compile(r"""(?:include|require)(?:_once)?\s*\(?\s*['"]([^'"]+)['"]""", re.M),
    ],
    "Rust": [
        re.compile(r"^\s*use\s+((?:crate|super|self)(?:::[\w{}*, ]+)+)", re.M),
        re.compile(r"^\s*mod\s+(\w+)\s*;", re.M),
    ],
    "C": [re.compile(r'^\s*#include\s+"([^"]+)"', re.M)],
    "C++": [re.compile(r'^\s*#include\s+"([^"]+)"', re.M)],
    "C#": [re.compile(r"^\s*using\s+([\w.]+)\s*;", re.M)],
    "Swift": [re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    "Kotlin": [re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    "Scala": [re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    "Elixir": [re.compile(r"^\s*(?:import|alias|use)\s+([\w.]+)", re.M)],
    "Haskell": [re.compile(r"^\s*import\s+(?:qualified\s+)?([\w.]+)", re.M)],
    "Lua": [re.compile(r"""require\s*\(?\s*['"]([^'"]+)['"]""")],
    "Julia": [re.compile(r"^\s*(?:using|import)\s+([\w.]+)", re.M)],
    "Dart": [re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.M)],
    "Perl": [re.compile(r"^\s*use\s+([\w:]+)", re.M)],
    "Shell": [re.compile(r"""^\s*(?:source|\.)\s+['"]?([^\s'"]+)""", re.M)],
    "Elm": [re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    "OCaml": [re.compile(r"^\s*open\s+([\w.]+)", re.M)],
    "Zig": [re.compile(r"""@import\s*\(\s*"([^"]+)"\s*\)""")],
    "Nim": [re.compile(r"^\s*(?:import|include)\s+([\w./]+)", re.M)],
    "Vue": [],  # filled from JavaScript below
    "Svelte": [],
    "HTML": [re.compile(r"""<script[^>]+src=['"]([^'"]+)['"]""")],
}
IMPORT_PATTERNS["Vue"] = IMPORT_PATTERNS["JavaScript"]
IMPORT_PATTERNS["Svelte"] = IMPORT_PATTERNS["JavaScript"]
IMPORT_PATTERNS["TypeScript"] = IMPORT_PATTERNS["JavaScript"]

# --- Function extraction ------------------------------------------------------
# Each entry: list of regexes with a named group 'name'.

_JS_FUNCS = [
    re.compile(r"\bfunction\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("),
    re.compile(r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[\w$]+\s*=>)"),
    re.compile(r"^\s*(?:public|private|protected|static|async|\*)*\s*(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M),
]

FUNCTION_PATTERNS: Dict[str, List[re.Pattern]] = {
    "Python": [re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>\w+)\s*\(", re.M),
               re.compile(r"^\s*class\s+(?P<name>\w+)\s*[(:]", re.M)],
    "JavaScript": _JS_FUNCS,
    "TypeScript": _JS_FUNCS,
    "Vue": _JS_FUNCS,
    "Svelte": _JS_FUNCS,
    "Java": [re.compile(r"^\s*(?:public|private|protected|static|final|abstract|synchronized|\s)+[\w<>\[\],\s]+\s+(?P<name>\w+)\s*\([^)]*\)\s*(?:throws[\w\s,]+)?\{", re.M)],
    "Go": [re.compile(r"^func\s+(?:\([^)]+\)\s+)?(?P<name>\w+)\s*\(", re.M)],
    "Ruby": [re.compile(r"^\s*def\s+(?:self\.)?(?P<name>[\w?!]+)", re.M),
             re.compile(r"^\s*class\s+(?P<name>\w+)", re.M)],
    "PHP": [re.compile(r"function\s+(?P<name>\w+)\s*\(")],
    "Rust": [re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(?P<name>\w+)", re.M),
             re.compile(r"^\s*(?:pub\s+)?struct\s+(?P<name>\w+)", re.M)],
    "C": [re.compile(r"^[\w*]+[\w\s*]*?\b(?P<name>\w+)\s*\([^;]*\)\s*\{", re.M)],
    "C++": [re.compile(r"^[\w:<>~*&]+[\w\s:<>~*&,]*?\b(?P<name>[\w~]+)\s*\([^;{]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{", re.M)],
    "C#": [re.compile(r"^\s*(?:public|private|protected|internal|static|virtual|override|async|\s)+[\w<>\[\],?\s]+\s+(?P<name>\w+)\s*\([^)]*\)\s*\{", re.M)],
    "Swift": [re.compile(r"\bfunc\s+(?P<name>\w+)\s*[(<]")],
    "Kotlin": [re.compile(r"\bfun\s+(?:<[^>]+>\s+)?(?P<name>\w+)\s*\(")],
    "Scala": [re.compile(r"\bdef\s+(?P<name>\w+)")],
    "Elixir": [re.compile(r"^\s*defp?\s+(?P<name>[\w?!]+)", re.M)],
    "Erlang": [re.compile(r"^(?P<name>[a-z]\w*)\s*\([^)]*\)\s*->", re.M)],
    "Haskell": [re.compile(r"^(?P<name>[a-z]\w*)\s*::", re.M)],
    "Lua": [re.compile(r"\bfunction\s+(?P<name>[\w.:]+)\s*\(")],
    "R": [re.compile(r"(?P<name>[\w.]+)\s*(?:<-|=)\s*function\s*\(")],
    "Julia": [re.compile(r"^\s*function\s+(?P<name>[\w.!]+)", re.M)],
    "Dart": [re.compile(r"^\s*[\w<>?\[\]]+\s+(?P<name>\w+)\s*\([^)]*\)\s*(?:async\s*)?\{", re.M)],
    "Perl": [re.compile(r"^\s*sub\s+(?P<name>\w+)", re.M)],
    "Shell": [re.compile(r"^\s*(?:function\s+)?(?P<name>[\w-]+)\s*\(\)\s*\{?", re.M)],
    "PowerShell": [re.compile(r"^\s*function\s+(?P<name>[\w-]+)", re.M)],
    "F#": [re.compile(r"^\s*let\s+(?:rec\s+)?(?P<name>\w+)", re.M)],
    "OCaml": [re.compile(r"^\s*let\s+(?:rec\s+)?(?P<name>\w+)", re.M)],
    "Clojure": [re.compile(r"\(defn-?\s+(?P<name>[\w!?-]+)")],
    "Elm": [re.compile(r"^(?P<name>[a-z]\w*)\s*:", re.M)],
    "Zig": [re.compile(r"\bfn\s+(?P<name>\w+)\s*\(")],
    "Nim": [re.compile(r"^\s*(?:proc|func|method)\s+(?P<name>\w+)", re.M)],
}

_KEYWORD_BLOCKLIST = {
    "if", "for", "while", "switch", "catch", "return", "new", "else", "do",
    "try", "with", "not", "and", "or", "in", "assert", "yield", "match",
    "case", "when", "unless", "elsif", "constructor", "super", "this",
    "typeof", "await", "async", "function", "sizeof", "defined",
}


def language_for(path: str) -> Optional[str]:
    """Map a file path to a language name, or None if unsupported."""
    dot = path.rfind(".")
    if dot == -1:
        return None
    ext = path[dot:]
    return EXTENSIONS.get(ext) or EXTENSIONS.get(ext.lower())


_TYPE_CHECKING_BLOCK = re.compile(
    r"^(?P<indent>[ \t]*)if\s+(?:typing\.)?TYPE_CHECKING\s*:\s*\n"
    r"(?:(?P=indent)[ \t]+.*\n?|[ \t]*\n)+",
    re.M,
)
# column-0 only: indented imports are deferred (function-body) or guarded —
# they don't create module-load-time dependency edges
_PY_FROM = re.compile(r"^from\s+([\w.]+)\s+import\s+(.+)$", re.M)
_PY_IMPORT = re.compile(r"^import\s+([\w.]+(?:\s*,\s*[\w.]+)*)", re.M)
_IDENT = re.compile(r"^\w+$")


def _python_imports(text: str) -> List[str]:
    """Expand `from X import a, b` into X.a / X.b so submodules resolve to files."""
    if "TYPE_CHECKING" in text:
        # imports guarded by `if TYPE_CHECKING:` never execute — don't count as edges
        text = _TYPE_CHECKING_BLOCK.sub("", text)
    specs: List[str] = []
    for m in _PY_FROM.finditer(text):
        mod, names = m.group(1), m.group(2).split("#")[0].strip("() \t\\")
        emitted = False
        for raw in names.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if _IDENT.match(name):
                sep = "" if mod.endswith(".") else "."
                specs.append(f"{mod}{sep}{name}")
                emitted = True
        if not emitted:
            specs.append(mod)
    for m in _PY_IMPORT.finditer(text):
        for mod in m.group(1).split(","):
            specs.append(mod.strip())
    return specs


def extract_imports(language: str, text: str) -> List[str]:
    """Return raw import specifiers found in *text*."""
    if language == "Python":
        return _python_imports(text)
    specs: List[str] = []
    for pattern in IMPORT_PATTERNS.get(language, []):
        for match in pattern.finditer(text):
            spec = next((g for g in match.groups() if g), None)
            if spec:
                specs.append(spec.strip())
    return specs


def extract_functions(language: str, text: str) -> List[Tuple[str, int]]:
    """Return (name, line_number) pairs for functions/classes defined in *text*."""
    found: List[Tuple[str, int]] = []
    seen = set()
    for pattern in FUNCTION_PATTERNS.get(language, []):
        for match in pattern.finditer(text):
            name = match.group("name")
            if not name or name in _KEYWORD_BLOCKLIST or name in seen:
                continue
            seen.add(name)
            line = text.count("\n", 0, match.start()) + 1
            found.append((name, line))
    found.sort(key=lambda item: item[1])
    return found
