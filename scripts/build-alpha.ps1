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
$manual = Get-ChildItem -LiteralPath $projectRoot -Filter "GATalk_*.docx" -File |
    Where-Object { $_.Name -notlike "~$*" } |
    Sort-Object Length -Descending |
    Select-Object -First 1
if ($null -eq $manual) {
    throw "GATalk user-guide DOCX was not found."
}
Copy-Item -LiteralPath $manual.FullName -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "USER_GUIDE_EN.md") -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses") -Destination $distRoot -Recurse -Force

Write-Host "Build complete: $(Join-Path $projectRoot 'dist\GATalk\GATalk.exe')"
