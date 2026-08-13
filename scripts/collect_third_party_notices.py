from __future__ import annotations

from importlib import metadata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "THIRD_PARTY_NOTICES.txt"

RUNTIME_DISTRIBUTIONS = (
    "Pillow",
    "numpy",
    "opencv-python-headless",
    "colour-science",
    "typing_extensions",
    "PyInstaller",
)


def _license_files(distribution_name: str) -> list[Path]:
    distribution = metadata.distribution(distribution_name)
    selected: list[Path] = []
    for record in distribution.files or ():
        lowered = str(record).lower()
        if not any(token in lowered for token in ("license", "copying", "notice")):
            continue
        path = Path(distribution.locate_file(record))
        if path.is_file() and path.suffix.lower() not in {".xml", ".json"}:
            selected.append(path)
    return sorted(set(selected), key=lambda item: item.as_posix().lower())


def _append_file(parts: list[str], title: str, path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    text = "\n".join(line.rstrip() for line in text.splitlines())
    parts.extend(("", "=" * 78, title, "=" * 78, text))


def build() -> Path:
    parts = [
        "GATalk THIRD-PARTY NOTICES",
        "",
        "This file applies to the GATalk Windows binary distribution. GATalk's",
        "own source code is licensed under the MIT License. Components listed below",
        "remain under their respective licenses.",
        "",
        "Qt for Python / PySide6 6.11.1 and Shiboken6 are used under LGPL-3.0-only.",
        "They are dynamically linked in the onedir package. Users may replace the",
        "corresponding DLLs with compatible builds. See QT_SOURCE_OFFER.md for the",
        "exact corresponding source archives and checksums.",
    ]

    for folder, label in (
        (ROOT / "licenses" / "pyside", "Qt for Python / PySide6 and Shiboken6"),
        (ROOT / "licenses" / "qtbase", "Qt Base 6.11.1"),
        (ROOT / "licenses" / "qtsvg", "Qt SVG 6.11.1"),
        (ROOT / "licenses" / "runtime", "Python runtime"),
    ):
        for path in sorted(folder.glob("*"), key=lambda item: item.name.lower()):
            if path.is_file():
                _append_file(parts, f"{label}: {path.name}", path)

    for name in RUNTIME_DISTRIBUTIONS:
        distribution = metadata.distribution(name)
        files = _license_files(name)
        if not files:
            raise RuntimeError(f"No license file found for {name} {distribution.version}")
        for path in files:
            _append_file(
                parts,
                f"{distribution.metadata['Name']} {distribution.version}: {path.name}",
                path,
            )

    OUTPUT.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    print(build())
