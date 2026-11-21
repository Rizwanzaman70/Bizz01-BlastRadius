# Run from the Bizz01 project folder: powershell -ExecutionPolicy Bypass -File .\export_bizz01_diagnostics.ps1
# This does not rebuild Docker, run patches, or upload anything.
$ErrorActionPreference = 'Stop'
$project = (Get-Location).Path
$image = 'bizz01-blast-radius:latest'
$working = Join-Path $project 'bizz01_diagnostics'
$archive = Join-Path $project 'Bizz01_Diagnostics.zip'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Docker not found. Open Docker Desktop first.'
}
& docker image inspect $image *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Image $image not found. Run the original build script first."
}
if (Test-Path $working) { Remove-Item -LiteralPath $working -Recurse -Force }
New-Item -ItemType Directory -Path $working | Out-Null
$containerId = ''
try {
  $containerId = (& docker create --entrypoint /bin/true $image | Select-Object -First 1).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $containerId) { throw 'docker create failed.' }
  foreach ($name in @('coverage.json.gz', 'source_index.json', 'test_symbols.json.gz')) {
    Write-Host "Exporting $name ..."
    & docker cp "$($containerId):/app/$name" (Join-Path $working $name)
    if ($LASTEXITCODE -ne 0) { throw "Could not copy $name from the image." }
  }
} finally {
  if ($containerId) { & docker rm $containerId *> $null }
}
$predictions = Join-Path $project 'predictions.jsonl'
if (Test-Path $predictions) { Copy-Item -LiteralPath $predictions -Destination $working }
$meta = @(
  'Bizz01 Blast Radius diagnostic export',
  'Generated from local Docker image after build.',
  'Contains the pinned-base coverage map, source index, static symbol map and optional predicted test IDs.',
  'Does NOT include the sample answers, personal environment variables, or any secret tokens.'
)
$meta | Set-Content -LiteralPath (Join-Path $working 'README.txt') -Encoding UTF8
if (Test-Path $archive) { Remove-Item $archive -Force }
Compress-Archive -Path (Join-Path $working '*') -DestinationPath $archive -Force
Write-Host ''
Write-Host "SUCCESS: $archive"
Write-Host 'Upload Bizz01_Diagnostics.zip to the same ChatGPT conversation.'
