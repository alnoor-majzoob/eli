#!/usr/bin/env python3
"""Security scan for EIL (plan Phase 9, T9.2).

Checks (fail-closed on findings):

1. Secret-pattern scan across the repository (excluding generated/vendor dirs).
2. Dev JWT default-secret flag when auth is not running in dev mode.
3. Dependency audit via ``pip-audit`` when installed.

Exit code: 1 when findings or audit failures exist, else 0.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps/api"

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".data",
    "node_modules",
    "dist",
    "coverage",
    "playwright-report",
    "test-results",
}
EXCLUDE_SUFFIXES = {".pyc", ".db", ".whl", ".gz", ".zip", ".tar"}
MAX_FILE_BYTES = 2_000_000

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "AWS secret access key",
        re.compile(
            r"\b(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[:=]\s*['\"][0-9A-Za-z/+]{16,}['\"]"
        ),
    ),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b")),
    ("GitHub PAT (new format)", re.compile(r"github_pat_[0-9A-Za-z]{22}_[0-9A-Za-z]{59}")),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[0-9A-Za-z_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Stripe key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Twilio account SID", re.compile(r"\bAC[0-9a-f]{32}\b")),
]


@dataclass
class Finding:
    location: str
    line: int
    check: str
    detail: str


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if any(name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
                continue
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def _snippet(line: str) -> str:
    text = line.strip()
    return text[:90] + ("…" if len(text) > 90 else "")


def scan_repo() -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_files(ROOT):
        rel = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for check, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(str(rel), lineno, check, _snippet(line)))
    return findings


def check_dev_jwt_default() -> list[Finding]:
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    try:
        from eil.core.config import DEFAULT_DEV_JWT_SECRET, Settings
    except Exception as exc:
        return [Finding("eil/core/config.py", 0, "config-import", f"cannot import Settings: {exc}")]
    settings = Settings()
    if settings.auth_mode == "oidc" and settings.dev_jwt_secret == DEFAULT_DEV_JWT_SECRET:
        return [
            Finding(
                "eil/core/config.py",
                0,
                "dev_jwt_default_secret",
                "auth_mode=oidc runs with the default dev JWT secret",
            )
        ]
    return []


def run_dependency_audit() -> tuple[int, list[str]]:
    """Dependency audit: ``uv export`` the frozen set + ``pip-audit -r`` (T9.2).

    The local project itself is not exported (``--no-emit-project``) since it
    is not on PyPI and pip-audit cannot audit it.
    """
    if importlib.util.find_spec("pip_audit") is None:
        return 0, ["pip-audit: not installed (skipped)"]
    fd, reqs_name = tempfile.mkstemp(prefix="eil-requirements-", suffix=".txt")
    requirements = Path(reqs_name)
    os.close(fd)
    try:
        export = subprocess.run(
            [
                "uv",
                "export",
                "--frozen",
                "--format",
                "requirements.txt",
                "--no-emit-project",
                "-o",
                str(requirements),
            ],
            cwd=str(API_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if export.returncode != 0 or not requirements.exists():
            return 1, [f"uv export failed: {export.stderr.strip()[:500]}"]
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", str(requirements), "--disable-pip", "--strict"],
            cwd=str(API_DIR),
            capture_output=True,
            text=True,
            timeout=900,
        )
        output = result.stdout + result.stderr
        lines = [line for line in output.splitlines() if line.strip()][-25:]
        if result.returncode != 0:
            return result.returncode, [f"pip-audit: exited {result.returncode}", *lines]
        return 0, ["pip-audit: clean", *lines]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, [f"dependency audit: failed to run ({exc})"]
    finally:
        requirements.unlink(missing_ok=True)


def main() -> int:
    findings = scan_repo() + check_dev_jwt_default()
    print("== secret-pattern scan ==")
    for finding in findings:
        print(f"  [{finding.check}] {finding.location}:{finding.line}: {finding.detail}")
    print(f"  -> {len(findings)} finding(s)")

    print("== dependency audit ==")
    audit_rc, audit_lines = run_dependency_audit()
    for line in audit_lines:
        print(f"  {line}")

    if findings:
        print(f"security-scan: FAIL — {len(findings)} finding(s)")
        return 1
    if audit_rc != 0:
        print("security-scan: FAIL — dependency audit failed")
        return 1
    print("security-scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
