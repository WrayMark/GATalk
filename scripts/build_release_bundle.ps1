$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$releaseDir = Join-Path $root "release"
$distDir = Join-Path $root "dist\GATalk"
$archive = Join-Path $releaseDir "GATalk-0.18.1-beta.2-windows-x64.zip"
$checksums = Join-Path $releaseDir "SHA256SUMS.txt"
$manifest = Join-Path $releaseDir "GATalk-0.18.1-beta.2-manifest.json"
$sourceDir = Join-Path $root ".artifacts\third-party-source"

if (-not (Test-Path -LiteralPath (Join-Path $distDir "GATalk.exe"))) {
    throw "Packaged application not found. Run build_alpha.cmd first."
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}

Compress-Archive -LiteralPath $distDir -DestinationPath $archive -CompressionLevel Optimal

$assets = @(
    $archive,
    (Join-Path $sourceDir "pyside-setup-everywhere-src-6.11.1.tar.xz"),
    (Join-Path $sourceDir "qtbase-everywhere-src-6.11.1.tar.xz"),
    (Join-Path $sourceDir "qtsvg-everywhere-src-6.11.1.tar.xz")
)

foreach ($asset in $assets) {
    if (-not (Test-Path -LiteralPath $asset)) {
        throw "Release asset not found: $asset"
    }
}

$hashRows = foreach ($asset in $assets) {
    $hash = Get-FileHash -LiteralPath $asset -Algorithm SHA256
    "{0}  {1}" -f $hash.Hash.ToLowerInvariant(), (Split-Path -Leaf $asset)
}
[System.IO.File]::WriteAllLines($checksums, $hashRows, [System.Text.UTF8Encoding]::new($false))

$distFiles = Get-ChildItem -LiteralPath $distDir -Recurse -File
$manifestObject = [ordered]@{
    product = "GATalk"
    version = "0.18.1b2"
    release_tag = "v0.18.1-beta.2"
    platform = "windows-x64"
    package_format = "PyInstaller onedir"
    unsigned = $true
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    package = [ordered]@{
        name = (Split-Path -Leaf $archive)
        size_bytes = (Get-Item -LiteralPath $archive).Length
        sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        unpacked_size_bytes = ($distFiles | Measure-Object Length -Sum).Sum
        file_count = $distFiles.Count
    }
    tests = [ordered]@{
        offline_automated = 295
        packaged_scale_smoke = @("100%", "125%", "150%")
    }
    corresponding_sources = $assets[1..3] | ForEach-Object {
        [ordered]@{
            name = (Split-Path -Leaf $_)
            size_bytes = (Get-Item -LiteralPath $_).Length
            sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}
$json = $manifestObject | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($manifest, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

Write-Host "Release archive: $archive"
Write-Host "Checksums: $checksums"
Write-Host "Manifest: $manifest"
