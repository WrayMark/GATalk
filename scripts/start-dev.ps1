$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$marker = Join-Path $venvDir ".dependencies-ok"
$pyproject = Join-Path $projectRoot "pyproject.toml"

function Assert-Python311X64 {
    $probe = & python -c "import struct,sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor)+'|'+str(struct.calcsize('P')*8))"
    if ($LASTEXITCODE -ne 0 -or $probe.Trim() -ne "3.11|64") {
        throw "SceneLens requires Python 3.11 x64. Detected: $probe"
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating the SceneLens Python 3.11 virtual environment..."
    Assert-Python311X64
    & python -m venv $venvDir
}

$needsInstall = -not (Test-Path -LiteralPath $marker)
if (-not $needsInstall) {
    $needsInstall = (Get-Item -LiteralPath $pyproject).LastWriteTimeUtc -gt (Get-Item -LiteralPath $marker).LastWriteTimeUtc
}

if ($needsInstall) {
    Write-Host "Installing pinned SceneLens dependencies. The first run may take a few minutes..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Unable to update pip." }
    & $venvPython -m pip install -e "$projectRoot[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check the network connection and pip output above." }
    New-Item -ItemType File -Path $marker -Force | Out-Null
}

Set-Location -LiteralPath $projectRoot
& $venvPython -m scenelens
exit $LASTEXITCODE
