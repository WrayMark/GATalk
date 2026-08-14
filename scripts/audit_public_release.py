from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GIT = os.environ.get("GATALK_GIT") or shutil.which("git") or "git"

SECRET_PATTERNS = {
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "OpenAI-style key": re.compile(rb"sk-(?:proj-)?[0-9A-Za-z_-]{20,}"),
    "Anthropic API key": re.compile(rb"sk-ant-[0-9A-Za-z_-]{20,}"),
    "xAI API key": re.compile(rb"xai-[0-9A-Za-z_-]{20,}"),
    "Hugging Face token": re.compile(rb"hf_[0-9A-Za-z]{30,}"),
    "GitHub token": re.compile(rb"gh[opusr]_[0-9A-Za-z]{30,}"),
    "GitLab token": re.compile(rb"glpat-[0-9A-Za-z_-]{20,}"),
    "Slack token": re.compile(rb"xox[baprs]-[0-9A-Za-z-]{20,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "Private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

PRIVATE_PATH_PATTERNS = (
    re.compile(rb"[A-Za-z]:[\\/]Users[\\/][^\\/\r\n]+", re.IGNORECASE),
    re.compile(rb"/Users/[^/\r\n]+", re.IGNORECASE),
    re.compile(rb"/home/[^/\r\n]+", re.IGNORECASE),
)

TEXT_SUFFIXES = {
    ".cfg",
    ".cmd",
    ".csv",
    ".ini",
    ".json",
    ".md",
    ".po",
    ".pot",
    ".ps1",
    ".py",
    ".rst",
    ".spec",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}

ALLOWED_FIXTURES = (
    b"sk-never-log-this",
    b"sk-abcdefghijk",
)

FORBIDDEN_EXACT_NAMES = {
    ".env",
    "project.db",
    "project.json",
    "recent-projects.json",
    "settings.json",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}


def _git(
    *args: str,
    text: bool = False,
    input_data: bytes | str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GIT, "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        capture_output=True,
        text=text,
        input=input_data,
        check=True,
    )


def _private_markers() -> tuple[bytes, ...]:
    """Return optional local-only markers without storing them in the repository."""

    raw = os.environ.get("GATALK_PRIVATE_MARKERS", "")
    markers: list[bytes] = []
    for value in raw.replace("\r", "\n").replace(";", "\n").splitlines():
        value = value.strip()
        if not value:
            continue
        markers.extend((value.encode("utf-8"), value.encode("utf-16le")))
    return tuple(markers)


def _historical_blobs() -> list[tuple[str, bytes]]:
    rows = _git("rev-list", "--objects", "--all", text=True).stdout.splitlines()
    path_by_object: dict[str, str] = {}
    for row in rows:
        object_id, separator, path = row.partition(" ")
        if separator and path:
            path_by_object.setdefault(object_id, path)

    object_ids = list(path_by_object)
    if not object_ids:
        return []
    request = ("\n".join(object_ids) + "\n").encode("ascii")
    checks = _git(
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_data=request,
    ).stdout.decode("ascii", "replace")
    blob_ids = [
        fields[0]
        for line in checks.splitlines()
        if len(fields := line.split()) >= 3 and fields[1] == "blob"
    ]
    if not blob_ids:
        return []

    batch = _git(
        "cat-file",
        "--batch",
        input_data=("\n".join(blob_ids) + "\n").encode("ascii"),
    ).stdout
    position = 0
    blobs: list[tuple[str, bytes]] = []
    for expected_id in blob_ids:
        header_end = batch.index(b"\n", position)
        object_id, object_type, size_text = batch[position:header_end].decode("ascii").split()
        if object_id != expected_id or object_type != "blob":
            raise RuntimeError(f"Unexpected git cat-file response for {expected_id}")
        position = header_end + 1
        size = int(size_text)
        data = batch[position : position + size]
        position += size + 1
        blobs.append((path_by_object[object_id], data))
    return blobs


def _historical_archive() -> bytes:
    return _git("archive", "--format=tar", "--prefix=gatalk-head/", "HEAD").stdout


def _scan_data(
    findings: list[str],
    label: str,
    data: bytes,
    *,
    is_text: bool = False,
) -> None:
    scrubbed = data
    for fixture in ALLOWED_FIXTURES:
        scrubbed = scrubbed.replace(fixture, b"")
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(scrubbed):
            findings.append(f"{name}: {label}")

    lowered = data.lower()
    if any(marker.lower() in lowered for marker in _private_markers()):
        findings.append(f"Private marker: {label}")

    if is_text and "scripts/audit_public_release.py" not in label.replace("\\", "/"):
        if any(pattern.search(data) for pattern in PRIVATE_PATH_PATTERNS):
            findings.append(f"Local absolute path: {label}")


def _scan_docx(findings: list[str], path: str, data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.namelist():
                if member.startswith(("docProps/", "word/")) and member.endswith((".xml", ".rels")):
                    _scan_data(
                        findings,
                        f"{path} ({member})",
                        archive.read(member),
                        is_text=True,
                    )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        findings.append(f"Unreadable DOCX: {path} ({type(exc).__name__})")


def _scan_image_metadata(findings: list[str], path: str, data: bytes) -> None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            metadata = {
                key: value
                for key, value in image.info.items()
                if key.lower() != "icc_profile"
            }
            if hasattr(image, "getexif"):
                metadata.update({str(key): value for key, value in image.getexif().items()})
        text = "\n".join(f"{key}={value}" for key, value in metadata.items()).encode(
            "utf-8", "replace"
        )
        _scan_data(findings, f"{path} (image metadata)", text, is_text=True)
    except (OSError, ValueError):
        findings.append(f"Unreadable image metadata: {path}")


def _is_forbidden_tracked_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    lowered = normalized.lower()
    name = Path(normalized).name.lower()
    suffix = Path(normalized).suffix.lower()
    return (
        lowered.startswith(
            ("dist/", "build/", ".venv/", ".artifacts/", ".qa/", "release/")
        )
        or name in FORBIDDEN_EXACT_NAMES
        or suffix in FORBIDDEN_SUFFIXES
        or any(
            part.endswith(
                (
                    ".scenelens",
                    ".scenelens-assets",
                    ".scenelens-study",
                    ".gatalk-library",
                    ".gatalk-comparison",
                )
            )
            for part in lowered.split("/")
        )
    )


def audit() -> list[str]:
    findings: list[str] = []
    history = _git("log", "-p", "--all", "--full-history", "--no-textconv").stdout
    _scan_data(findings, "complete Git history", history)
    commit_metadata = _git(
        "log",
        "--all",
        "--format=%H%n%an%n%ae%n%cn%n%ce%n%s%n%b",
    ).stdout
    _scan_data(findings, "commit metadata", commit_metadata, is_text=True)
    _scan_data(findings, "HEAD source archive", _historical_archive())

    for path, data in _historical_blobs():
        suffix = Path(path).suffix.lower()
        _scan_data(findings, f"Git blob {path}", data, is_text=suffix in TEXT_SUFFIXES)
        if suffix == ".docx":
            _scan_docx(findings, path, data)
        elif suffix in IMAGE_SUFFIXES:
            _scan_image_metadata(findings, path, data)

    tracked = set(_git("ls-files", text=True).stdout.splitlines())
    findings.extend(
        f"Forbidden tracked path: {path}"
        for path in sorted(path for path in tracked if _is_forbidden_tracked_path(path))
    )

    visible = _git("ls-files", "--cached", "--others", "--exclude-standard", text=True).stdout
    for path in visible.splitlines():
        source = ROOT / path
        if source.is_file():
            suffix = source.suffix.lower()
            data = source.read_bytes()
            _scan_data(findings, f"working tree {path}", data, is_text=suffix in TEXT_SUFFIXES)
            if suffix == ".docx":
                _scan_docx(findings, path, data)
            elif suffix in IMAGE_SUFFIXES:
                _scan_image_metadata(findings, path, data)

    status = _git("status", "--porcelain", "--untracked-files=all", text=True).stdout
    for line in status.splitlines():
        path = line[3:].replace("\\", "/")
        if path.startswith(("dist/", "build/", ".venv/", ".artifacts/", ".qa/", "release/")):
            findings.append(f"Ignored build path unexpectedly visible to Git: {path}")
    return sorted(set(findings))


if __name__ == "__main__":
    problems = audit()
    if problems:
        print("Public-release audit failed:")
        print("\n".join(f"- {problem}" for problem in problems))
        raise SystemExit(1)
    print(
        "Public-release audit passed: all reachable Git blobs, document/image metadata, "
        "and visible files contain no known credential, private-path, private-marker, "
        "or forbidden tracked-file pattern."
    )
