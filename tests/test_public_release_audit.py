from __future__ import annotations

import io
import zipfile

from scripts import audit_public_release


def test_private_markers_cover_utf8_and_utf16(monkeypatch) -> None:
    monkeypatch.setenv("GATALK_PRIVATE_MARKERS", "PrivateAlias;private@example.test")
    findings: list[str] = []

    audit_public_release._scan_data(
        findings,
        "utf8 fixture",
        b"owner=PrivateAlias",
        is_text=True,
    )
    audit_public_release._scan_data(
        findings,
        "utf16 fixture",
        "private@example.test".encode("utf-16le"),
    )

    assert findings == [
        "Private marker: utf8 fixture",
        "Private marker: utf16 fixture",
    ]


def test_forbidden_project_and_credential_paths() -> None:
    assert audit_public_release._is_forbidden_tracked_path("sample/project.db")
    assert audit_public_release._is_forbidden_tracked_path("private/settings.json")
    assert audit_public_release._is_forbidden_tracked_path("release/GATalk.zip")
    assert audit_public_release._is_forbidden_tracked_path("keys/service.pem")
    assert not audit_public_release._is_forbidden_tracked_path(".env.example")
    assert not audit_public_release._is_forbidden_tracked_path("docs/sample-project.json.md")


def test_docx_internal_metadata_is_scanned(monkeypatch) -> None:
    monkeypatch.setenv("GATALK_PRIVATE_MARKERS", "PrivateAuthor")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "docProps/core.xml",
            "<cp:coreProperties><dc:creator>PrivateAuthor</dc:creator></cp:coreProperties>",
        )
    findings: list[str] = []

    audit_public_release._scan_docx(findings, "manual.docx", buffer.getvalue())

    assert findings == ["Private marker: manual.docx (docProps/core.xml)"]


def test_known_secret_is_reported_but_short_test_fixture_is_allowed() -> None:
    findings: list[str] = []
    audit_public_release._scan_data(
        findings,
        "fixture",
        b"AIza" + (b"0" * 36) + b" and sk-never-log-this",
        is_text=True,
    )

    assert findings == ["Google API key: fixture"]
