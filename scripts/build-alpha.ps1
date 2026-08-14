$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$specFile = Join-Path $projectRoot "GATalk.spec"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Development environment not found. Run start_dev.cmd first."
}

Set-Location -LiteralPath $projectRoot
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUSERBASE = Join-Path $projectRoot ".artifacts\python-userbase"
New-Item -ItemType Directory -Force -Path $env:PYTHONUSERBASE | Out-Null
& $venvPython (Join-Path $projectRoot "scripts\audit_public_release.py")
if ($LASTEXITCODE -ne 0) {
    throw "Public-release audit failed."
}
& $venvPython (Join-Path $projectRoot "scripts\collect_third_party_notices.py")
if ($LASTEXITCODE -ne 0) {
    throw "Third-party notice generation failed."
}
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    $specFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$distRoot = Join-Path $projectRoot "dist\GATalk"
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.txt") -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "QT_SOURCE_OFFER.md") -Destination $distRoot -Force
$manuals = Get-ChildItem -LiteralPath $projectRoot -Filter "GATalk_*.docx" -File |
    Where-Object { $_.Name -notlike "~$*" }
if ($manuals.Count -eq 0) {
    throw "GATalk user-guide DOCX was not found."
}
foreach ($manual in $manuals) {
    Copy-Item -LiteralPath $manual.FullName -Destination $distRoot -Force
}
$guideFiles = @("USER_GUIDE.md", "USER_GUIDE_EN.md")
foreach ($guideFile in $guideFiles) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $guideFile) -Destination $distRoot -Force
}
$guideImageDirectories = @("user-guide-0.18.0", "user-guide-0.18.0-en")
foreach ($guideImageDirectory in $guideImageDirectories) {
    $guideImages = Join-Path $projectRoot ("docs\images\" + $guideImageDirectory)
    if (-not (Test-Path -LiteralPath $guideImages)) {
        throw "User-guide screenshots were not found: $guideImageDirectory"
    }
    $guideImageDestination = Join-Path $distRoot ("docs\images\" + $guideImageDirectory)
    New-Item -ItemType Directory -Force -Path $guideImageDestination | Out-Null
    Copy-Item -Path (Join-Path $guideImages "*") `
        -Destination $guideImageDestination -Force
}
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses") -Destination $distRoot -Recurse -Force

Write-Host "Build complete: $(Join-Path $projectRoot 'dist\GATalk\GATalk.exe')"
