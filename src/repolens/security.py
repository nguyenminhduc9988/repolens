"""Lightweight security & hygiene scanner (heuristic, favors precision over recall)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .scanner import SourceFile


@dataclass
class Finding:
    file: str
    line: int
    severity: str  # critical | serious | warning | info
    kind: str
    detail: str


_RULES = [
    # (kind, severity, regex, detail)
    ("Private key", "critical",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
     "Private key material committed to the repo"),
    ("AWS access key", "critical",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
     "String matches an AWS access key ID"),
    ("Hardcoded secret", "critical",
     re.compile(r"""(?i)\b(?:api[_-]?key|apikey|secret[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret|password|passwd)\b\s*[:=]\s*["'][A-Za-z0-9+/_\-.]{12,}["']"""),
     "Credential-looking literal assigned to a secret-named variable"),
    ("Slack token", "critical",
     re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
     "String matches a Slack token"),
    ("GitHub token", "critical",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
     "String matches a GitHub token"),
    ("SQL injection risk", "serious",
     re.compile(r"""(?i)(?:execute|query|cursor\.execute|db\.query)\s*\(\s*(?:f["']|["'][^"']*(?:SELECT|INSERT|UPDATE|DELETE)[^"']*["']\s*(?:\+|%|\|\|)\s*\w)"""),
     "SQL built by string concatenation/interpolation"),
    ("eval() usage", "serious",
     re.compile(r"(?<![\w.])eval\s*\("),
     "Dynamic code evaluation"),
    ("exec() usage", "serious",
     re.compile(r"(?<![\w.])exec\s*\(\s*[^)]"),
     "Dynamic code execution"),
    ("Unsafe deserialization", "serious",
     re.compile(r"\b(?:pickle\.loads?|yaml\.load\s*\((?![^)]*Loader)|Marshal\.load|unserialize)\s*\("),
     "Deserializing untrusted data can execute code"),
    ("innerHTML assignment", "warning",
     re.compile(r"\.innerHTML\s*=(?!=)"),
     "Possible XSS sink; prefer textContent or sanitize"),
    ("Insecure HTTP URL", "info",
     re.compile(r"""["']http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|\{|<|%s)[\w.-]+"""),
     "Plaintext HTTP endpoint"),
    ("TLS verification off", "serious",
     re.compile(r"(?i)\bverify\s*=\s*False\b|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true"),
     "Certificate verification disabled"),
    ("Debug statement", "info",
     re.compile(r"^\s*(?:console\.log|print|puts|var_dump|dd|println!|fmt\.Println|System\.out\.println)\s*\(", re.M),
     "Debug output left in code"),
]

# test/docs/example content: findings are demoted, disconnection is expected
DEMOTED_PATHS = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|fixtures|examples?|mocks?|docs?|docs_src|"
    r"samples?|demos?|tutorials?|benchmarks?|scripts?)(/|$)|\.(test|spec)\.")
_TESTY = DEMOTED_PATHS
MAX_PER_RULE_PER_FILE = 5


def scan_security(files: List[SourceFile]) -> List[Finding]:
    findings: List[Finding] = []
    for f in files:
        is_testy = bool(_TESTY.search(f.path))
        for kind, severity, rx, detail in _RULES:
            if kind == "Debug statement" and f.language in ("Shell", "PowerShell", "SQL", "HTML"):
                continue
            hits = 0
            for m in rx.finditer(f.text):
                line = f.text.count("\n", 0, m.start()) + 1
                sev = severity
                # demote findings inside test/example paths — still shown, less alarming
                if is_testy and severity in ("critical", "serious"):
                    sev = "warning"
                findings.append(Finding(file=f.path, line=line, severity=sev,
                                        kind=kind, detail=detail))
                hits += 1
                if hits >= MAX_PER_RULE_PER_FILE:
                    break
    order = {"critical": 0, "serious": 1, "warning": 2, "info": 3}
    findings.sort(key=lambda x: (order[x.severity], x.file, x.line))
    return findings
