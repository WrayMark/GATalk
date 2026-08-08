$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $projectRoot "dist\GATalk\GATalk.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "dist\GATalk\GATalk.exe was not found. Run build_alpha.cmd first."
}

$resultRoot = Join-Path $projectRoot ".artifacts\windows-acceptance"
New-Item -ItemType Directory -Force -Path $resultRoot | Out-Null

$scales = @("1.0", "1.25", "1.5")
$results = @()
foreach ($scale in $scales) {
    $env:QT_SCALE_FACTOR = $scale
    $process = Start-Process `
        -FilePath $exe `
        -ArgumentList "--smoke-test" `
        -PassThru `
        -Wait `
        -WindowStyle Hidden
    $results += [PSCustomObject]@{
        Scale = $scale
        ExitCode = $process.ExitCode
        Passed = ($process.ExitCode -eq 0)
    }
}
Remove-Item Env:\QT_SCALE_FACTOR -ErrorAction SilentlyContinue

$output = Join-Path $resultRoot "smoke-results.json"
$results | ConvertTo-Json | Set-Content -LiteralPath $output -Encoding UTF8
$results | Format-Table -AutoSize
if ($results.Where({ -not $_.Passed }).Count -gt 0) {
    throw "One or more Windows scale smoke tests failed."
}

Write-Host "Automated smoke tests passed. Real high-DPI and clean-machine checks remain manual."
