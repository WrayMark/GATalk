$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$specFile = Join-Path $projectRoot "SceneLens.spec"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Development environment not found. Run start_dev.cmd first."
}

Set-Location -LiteralPath $projectRoot
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUSERBASE = Join-Path $projectRoot ".artifacts\python-userbase"
New-Item -ItemType Directory -Force -Path $env:PYTHONUSERBASE | Out-Null
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    $specFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

Write-Host "Build complete: $(Join-Path $projectRoot 'dist\SceneLens\SceneLens.exe')"
