# GATalk

**Interface languages:** Simplified Chinese (reference UI); English, Traditional Chinese, Japanese, and French (preview).

GATalk is a desktop toolkit for game environment art and scene production. It brings reference-image analysis, visual comparison, artwork study, scene review, and asset breakdown into one workflow, helping artists understand images more clearly, organize production evidence, and turn analysis into actionable art tasks.

> Status: `0.18.1 Beta 2`. This is a public beta. The interface, project formats,
> and AI-provider compatibility may continue to change. Keep separate backups of
> important projects.

[中文](README.md) · [Illustrated guide](USER_GUIDE_EN.md) · [Roadmap](docs/PUBLIC_ROADMAP.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## Download for Windows x64

**[Download GATalk 0.18.1 Beta 2 for Windows](https://github.com/WrayMark/GATalk/releases/download/v0.18.1-beta.2/GATalk-0.18.1-beta.2-windows-x64.zip)**

> GitHub's green **Code → Download ZIP** button downloads the source code. It does
> not contain a runnable EXE. Regular users should download the Windows package above.

Extract the complete archive, then run `GATalk/GATalk.exe`. Python is not required
on the target computer. The beta is unsigned; check the SHA-256 and known limitations
on the [Release page](https://github.com/WrayMark/GATalk/releases/tag/v0.18.1-beta.2)
before first launch.

![GATalk workbench home](docs/images/user-guide-0.18.0-en/01-workspace-hub.png)

## Intended users

GATalk is built for game environment artists, scene builders, Unreal Engine level
artists, concept artists, and learners. It helps organize visual evidence and
production decisions. It does not replace art-direction judgment, copyright
review, or performance analysis inside an Unreal project.

## Implemented workbenches

- **Scene Art Control**: production intent, reference/screenshot comparison,
  palette and value evidence, paired regions, focused reviews, tasks, and version
  follow-up.
- **Artwork Study**: local measurements, structured interpretation, and learning
  notes for a single artwork or concept image.
- **Comparative Study**: side-by-side research of two to six artworks under one
  question and a shared set of visual axes.
- **Asset Breakdown**: scene understanding, editable asset hierarchy, breakdown
  depth, automatic asset boards, and generation prompts.
- **References & Knowledge Base**: images, article links, tags, crops, notes, and
  cross-project references.
- **Production Tasks & Acceptance**: confirmed findings, acceptance criteria,
  version checks, and quality gates.
- **Language and appearance**: Simplified Chinese is the reference UI; Traditional
  Chinese, English, Japanese, and French are previews. Dark, light, and system
  themes are available.

## Current limitations

- Only a Windows x64 beta is distributed. It is unsigned, so Windows SmartScreen
  may show a warning on first launch.
- Non-Chinese translations still require native-speaker review.
- Real AI calls require the user's own account, API key, quota, and regional
  access. Provider models and endpoints may change after a GATalk release.
- Offline Mock checks workflow and structured data only. It is not a local vision
  model and does not interpret image semantics.
- AI output can be wrong. GATalk separates evidence, inference, and generated
  completion, but users must still verify conclusions.
- Production-ready 3D generation, Unreal project scanning, video analysis, local
  large models, and CUDA workflows are not included.

## Data and privacy

- Projects and imported material stay in user-selected local folders. Original
  images are read-only and are never overwritten.
- GATalk has no background upload, telemetry, or automatic update service.
- Every network transmission requires an explicit user action and a send-manifest
  review.
- API keys can be stored in Windows Credential Manager and are never written to a
  project, SQLite database, JSON file, or log.
- External-AI exports can remove metadata and local paths and reduce image size.

See [SECURITY.md](SECURITY.md) and [Privacy and network boundaries](docs/PRIVACY.md).

## Run from source

Requirements: Windows 10/11 x64, Python 3.11 x64, and Git. The first dependency
installation needs network access.

```powershell
git clone https://github.com/WrayMark/GATalk.git
cd GATalk
.\start_dev.cmd
```

Manual setup:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m scenelens
```

Do not place API keys in `.env` or source files. Store them through the
application in Windows Credential Manager.

## Test and build

```powershell
.\scripts\test.ps1
.\build_alpha.cmd
.\scripts\windows-acceptance.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release_bundle.ps1
```

Build output is written to `dist/GATalk/`. Public releases also require the
security audit, third-party notice collection, and package verification described
in [the release checklist](docs/RELEASE_CHECKLIST.md).

## Naming and license

`scenelens` was the project's early name. It remains in the Python package,
module IDs, and compatibility paths so that older projects keep working. The
product, executable, and public repository are named **GATalk**.

GATalk source code is available under the [MIT License](LICENSE). The Windows
binary includes third-party components under their own licenses, notably Qt for
Python under LGPLv3. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) and
`THIRD_PARTY_NOTICES.txt` in the release package.
