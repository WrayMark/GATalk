from __future__ import annotations

import re
import shutil
import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GIT = os.environ.get("GATALK_GIT") or shutil.which("git") or "git"

SECRET_PATTERNS = {
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "OpenAI-style key": re.compile(rb"sk-(?:proj-)?[0-9A-Za-z_-]{20,}"),
    "GitHub token": re.compile(rb"gh[opusr]_[0-9A-Za-z]{30,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "Private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

PRIVATE_PATH_PATTERNS = (
    re.compile(rb"[A-Za-z]:\\Users\\[^\\\r\n]+", re.IGNORECASE),
    re.compile(rb"/Users/[^/\r\n]+", re.IGNORECASE),
    re.compile(rb"/home/[^/\r\n]+", re.IGNORECASE),
)

ALLOWED_FIXTURES = (
    b"sk-never-log-this",
    b"sk-abcdefghijk",
)


def _git(*args: str, text: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GIT, "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        capture_output=True,
        text=text,
        check=True,
    )


def _tracked_blobs() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in _git("rev-list", "--objects", "--all", text=True).stdout.splitlines():
        object_id, separator, path = line.partition(" ")
        if separator and path:
            rows.append((object_id, path))
    return rows


def _historical_archive() -> bytes:
    process = _git("archive", "--format=tar", "--prefix=gatalk-head/", "HEAD")
    return process.stdout


def _scan_data(findings: list[str], label: str, data: bytes) -> None:
    scrubbed = data
    for fixture in ALLOWED_FIXTURES:
        scrubbed = scrubbed.replace(fixture, b"")
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(scrubbed):
            findings.append(f"{name}: {label}")
    if "scripts/audit_public_release.py" not in label.replace("\\", "/") and Path(label.split(" (")[0]).suffix.lower() in {".py", ".md", ".json", ".toml", ".txt", ".ps1", ".cmd", ".yml", ".yaml"}:
        for pattern in PRIVATE_PATH_PATTERNS:
            if pattern.search(data):
                findings.append(f"Local absolute path: {label}")
                break


def audit() -> list[str]:
    findings: list[str] = []
    history = _git(
        "log",
        "-p",
        "--all",
        "--full-history",
        "--no-textconv",
        "--",
        "*.py",
        "*.md",
        "*.json",
        "*.toml",
        "*.txt",
        "*.ps1",
        "*.cmd",
        "*.yml",
        "*.yaml",
    ).stdout
    _scan_data(findings, "complete textual Git history", history)
    _scan_data(findings, "HEAD source archive", _historical_archive())

    tracked = set(_git("ls-files", text=True).stdout.splitlines())
    forbidden = {
        path
        for path in tracked
        if path.startswith(("dist/", "build/", ".venv/", ".artifacts/", ".qa/"))
        or path.endswith((".log", ".pfx", ".p12", ".pem", ".key"))
    }
    findings.extend(f"Forbidden tracked path: {path}" for path in sorted(forbidden))
    visible = _git("ls-files", "--cached", "--others", "--exclude-standard", text=True).stdout
    for path in visible.splitlines():
        source = ROOT / path
        if source.is_file():
            _scan_data(findings, f"working tree {path}", source.read_bytes())
    status = _git("status", "--porcelain", "--untracked-files=all", text=True).stdout
    for line in status.splitlines():
        path = line[3:].replace("\\", "/")
        if path.startswith(("dist/", "build/", ".venv/", ".artifacts/", ".qa/")):
            findings.append(f"Ignored build path unexpectedly visible to Git: {path}")
    return findings


if __name__ == "__main__":
    problems = audit()
    if problems:
        print("Public-release audit failed:")
        print("\n".join(f"- {problem}" for problem in problems))
        raise SystemExit(1)
    print("Public-release audit passed: no known credential, private-path, or forbidden tracked-file pattern found.")
