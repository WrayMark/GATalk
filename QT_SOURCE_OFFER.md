# Qt / PySide6 corresponding source

The GATalk Windows beta dynamically links unmodified community builds from
PySide6 Essentials 6.11.1 and Shiboken6 6.11.1. Those components are distributed
under LGPL-3.0-only. The package contains Qt Core, Gui, Widgets, Network, OpenGL,
and SVG components required by the application and Qt image/platform plugins.

The exact corresponding source archives are attached to the same GitHub Release
as the Windows binary:

| Archive | SHA-256 |
|---|---|
| `pyside-setup-everywhere-src-6.11.1.tar.xz` | `6ffd9835bb0dd2c56f061d62f1616bb1707cfc0202b80e3165d6be087f3965e2` |
| `qtbase-everywhere-src-6.11.1.tar.xz` | `d9594a31228aa23ad6b531719a29b45f0f3989fe6c136d45767ea179f233c1ac` |
| `qtsvg-everywhere-src-6.11.1.tar.xz` | `7f3cf02f4824bf03c2c5859ea6db173bf1482a1daf24e6cdf7bc78cfa26a8a94` |

The same archives are available from the Qt Project's official release server:

- <https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/>
- <https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/>

GATalk does not modify these libraries. The `onedir` layout intentionally keeps
Qt DLLs separate from `GATalk.exe`; recipients may replace them with compatible
LGPL builds. License texts and third-party attributions are included in
`THIRD_PARTY_NOTICES.txt` and the `licenses/` directory.

This notice is offered for the duration required by LGPLv3. If a Release asset is
unavailable, open a public repository issue titled `Qt source request` to request
the exact archive without charge. Do not use the security channel for ordinary
source-code requests.
