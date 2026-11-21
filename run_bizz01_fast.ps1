# Run from Bizz01 project folder. Reuses the existing image's coverage map.
# Allows testing a revised local selector.py without a 6-minute image rebuild.
$ErrorActionPreference = 'Stop'
$project = (Get-Location).Path
$image = 'bizz01-blast-radius:latest'
$sample = Join-Path $project 'sample'
$testsFile = Get-ChildItem -Path $sample -Recurse -Filter 'tests.json' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $testsFile) { throw 'Cannot find sample/tests.json. Run original run_windows.ps1 first.' }
$dataDir = Split-Path -Parent $testsFile.FullName
$scorePy = Join-Path $sample 'score.py'
$answers = Join-Path $dataDir 'answers.json'
$selector = Join-Path $project 'selector.py'
if (-not (Test-Path $selector)) { throw 'Missing selector.py in current project folder.' }
& docker image inspect $image *> $null
if ($LASTEXITCODE -ne 0) { throw 'No built image found. Run run_windows.ps1 first.' }
Write-Host 'Running current local selector.py with original Docker image maps; no rebuild...'
$preds = @( & docker run --rm --network none --read-only --cpus 2 --memory 4g --pids-limit 256 `
    --tmpfs /tmp:rw,size=64m,mode=1777 `
    -v "${dataDir}:/data:ro" `
    -v "${selector}:/app/selector.py:ro" `
    $image )
if ($LASTEXITCODE -ne 0) { throw 'Docker run failed.' }
$out = Join-Path $project 'predictions_fast.jsonl'
[System.IO.File]::WriteAllLines($out, [string[]]$preds, (New-Object System.Text.UTF8Encoding($false)))
if ((Test-Path $scorePy) -and (Test-Path $answers)) {
    & python $scorePy $dataDir $answers $out
    if ($LASTEXITCODE -ne 0) { throw 'Scorer failed.' }
} else {
    Write-Host 'No official scorer found; predictions in predictions_fast.jsonl'
}
