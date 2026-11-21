# Bizz01 Blast Radius: fetch organizer sample, build Docker, and generate predictions.
# For an official score, use the scorer included with the organizer's starter kit.
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Sample = Join-Path $Root "sample"
$Archive = Join-Path $Root "blast-radius-sample.tar.gz"
$Url = "https://www.joinbuilders.org/buildathon/tracks/blast-radius/files/blast-radius-sample.tar.gz"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker CLI not found. Install/start Docker Desktop, then retry."
}
if (-not (Test-Path $Sample)) {
  New-Item -Type Directory -Path $Sample | Out-Null
}
$Existing = Get-ChildItem -Path $Sample -Recurse -Filter "tests.json" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Existing) {
  if (-not (Test-Path $Archive)) {
    Write-Host "Downloading official sample archive..."
    Invoke-WebRequest -Uri $Url -OutFile $Archive
  }
  tar -xzf $Archive -C $Sample
  if ($LASTEXITCODE -ne 0) { throw "Could not extract sample archive." }
}
$TestsFile = Get-ChildItem -Path $Sample -Recurse -Filter "tests.json" | Select-Object -First 1
if (-not $TestsFile) { throw "Sample archive did not contain tests.json. Inspect sample folder." }
$DataDir = Split-Path -Parent $TestsFile.FullName
if (-not (Test-Path (Join-Path $DataDir "commits"))) {
  throw "No commits folder beside tests.json. Inspect sample folder."
}

Write-Host "Building Bizz01 image (includes pinned sqlglot profiling)..."
docker build -t bizz01-blast-radius $Root
if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }

$Output = Join-Path $Root "predictions.jsonl"
Write-Host "Running submission image on organizer sample..."
$Predictions = @(docker run --rm --network none --read-only --cpus 2 --memory 4g --pids-limit 256 `
  --tmpfs /tmp:rw,size=64m,mode=1777 -v "${DataDir}:/data:ro" bizz01-blast-radius)
if ($LASTEXITCODE -ne 0) { throw "Runtime failed." }
# Windows PowerShell 5.1's Out-File -Encoding utf8 adds a BOM; the scorer
# rejects BOM-prefixed JSON, so write explicitly as UTF-8 without a BOM.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($Output, [string[]]$Predictions, $Utf8NoBom)
Write-Host "Predictions saved to: $Output"
# Official score script is at the ROOT of the extracted starter kit, not /sample.
$Scorer = Join-Path $Sample 'score.py'
$Answers = Join-Path $DataDir 'answers.json'
if ((Test-Path $Scorer) -and (Test-Path $Answers)) {
  Write-Host "Scoring against the organizer's 30 labeled sample commits:"
  python $Scorer $DataDir $Answers $Output
  if ($LASTEXITCODE -ne 0) { throw "Official sample scorer rejected the output." }
} else {
  Write-Warning "score.py or sample/answers.json missing; score predictions with official kit."
}
