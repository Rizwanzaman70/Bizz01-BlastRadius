# Bizz01 V3 - clean, guarded official sample benchmark (Windows PowerShell 5.1)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Dockerfile = Join-Path $Root 'Dockerfile'
$Selector = Join-Path $Root 'selector.py'

# Stop before building if the organizer's *starter* files overwrote our project.
if (-not (Test-Path $Dockerfile) -or -not (Test-Path $Selector)) {
    throw 'Missing Dockerfile/selector.py. Extract the Bizz01 V3 ZIP again into a NEW folder.'
}
$dockerText = [System.IO.File]::ReadAllText($Dockerfile)
$selectorText = [System.IO.File]::ReadAllText($Selector)
if (-not $dockerText.Contains('RUN python fetch_sqlglot.py') -or
    -not $dockerText.Contains('RUN python build_map.py') -or
    -not $dockerText.Contains('COPY main.py selector.py build_map.py coverage_plugin.py /app/')) {
    throw 'WRONG Dockerfile: this appears to be the starter Dockerfile (runs all tests). Restore the Bizz01 V3 Dockerfile. Do NOT copy the organizer starter files over this project.'
}
if (-not $selectorText.Contains('class Engine:') -or -not $selectorText.Contains('def affected(self,change:Change)')) {
    throw 'WRONG selector.py: expected Bizz01 V3 dependency-analysis selector. Restore it from the V3 ZIP.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI missing. Start Docker Desktop (Linux containers) and reopen PowerShell.'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python missing from PATH. Install Python and enable Add Python to PATH.'
}
Write-Host ('Verified Bizz01 V3 Dockerfile (' + ((Get-Item $Dockerfile).Length) + ' bytes) and selector.py (' + ((Get-Item $Selector).Length) + ' bytes).') -ForegroundColor Green

# The organizer archive contains score.py + sample/answers.json. Keep it OUTSIDE GitHub.
$Archive = Join-Path $Root 'blast-radius-sample.tar.gz'
$Kit = Join-Path $Root '_organizer_kit'
$Scorer = Join-Path $Kit 'score.py'
$DataDir = Join-Path $Kit 'sample'
if (Test-Path $Archive) {
    if (-not ((Test-Path $Scorer) -and (Test-Path (Join-Path $DataDir 'tests.json')) -and (Test-Path (Join-Path $DataDir 'answers.json')))) {
        if (-not (Test-Path $Kit)) { New-Item -ItemType Directory -Path $Kit | Out-Null }
        Write-Host 'Extracting ORIGINAL organizer starter archive for local scoring (not for Docker source)...'
        & tar -xzf $Archive -C $Kit
        if ($LASTEXITCODE -ne 0) { throw 'Could not extract official starter kit.' }
    }
} else {
    # Accept a previously extracted kit, but require ALL official scorer inputs.
    $Candidates = @(
        (Join-Path $Root 'sample'),
        (Join-Path $Root 'blast-radius-sample'),
        $Root
    )
    $Found = $false
    foreach ($Candidate in $Candidates) {
        $CandidateScorer = Join-Path $Candidate 'score.py'
        $CandidateData = Join-Path $Candidate 'sample'
        if ((Test-Path $CandidateScorer) -and
            (Test-Path (Join-Path $CandidateData 'tests.json')) -and
            (Test-Path (Join-Path $CandidateData 'answers.json'))) {
            $Scorer = $CandidateScorer
            $DataDir = $CandidateData
            $Found = $true
            break
        }
    }
    if (-not $Found) {
        throw 'Official scorer NOT FOUND. Place blast-radius-sample.tar.gz in THIS project folder (beside Dockerfile). Do NOT extract it over Dockerfile or selector.py.'
    }
}
if (-not ((Test-Path $Scorer) -and (Test-Path (Join-Path $DataDir 'answers.json')) -and (Test-Path (Join-Path $DataDir 'tests.json')) -and (Test-Path (Join-Path $DataDir 'commits')))) {
    throw 'Incomplete official sample/scorer. Use the unchanged blast-radius-sample.tar.gz from the organizers.'
}

$Image = 'bizz01-blast-radius-v3:verified'
Write-Host "Building REAL V3 image ($Image) with pinned-base coverage profiling..." -ForegroundColor Cyan
& docker build -t $Image -f $Dockerfile $Root
if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }

Write-Host 'Running 30 original sample commits under competition resource limits...'
$Predictions = @( & docker run --rm --network none --read-only --cpus 2 --memory 4g --pids-limit 256 `
    --tmpfs /tmp:rw,size=64m,mode=1777 -v "${DataDir}:/data:ro" $Image )
if ($LASTEXITCODE -ne 0) { throw 'Docker image execution failed.' }
$Output = Join-Path $Root 'predictions.jsonl'
[System.IO.File]::WriteAllLines($Output, [string[]]$Predictions, (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'Scoring with OFFICIAL score.py:' -ForegroundColor Cyan
& python $Scorer $DataDir (Join-Path $DataDir 'answers.json') $Output
if ($LASTEXITCODE -ne 0) { throw 'Official scorer rejected the output.' }
Write-Host 'Done. The scorer measures SIMULATED seconds only; leaderboard adds runtime CPU time and uses unseen commits.' -ForegroundColor Green
