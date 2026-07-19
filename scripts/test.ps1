$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Development environment not found. Run start_dev.cmd first."
}

Set-Location -LiteralPath $projectRoot
$env:QT_QPA_PLATFORM = "offscreen"
& $venvPython -m pytest
exit $LASTEXITCODE
