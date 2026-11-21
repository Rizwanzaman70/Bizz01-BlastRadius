# Bizz01 Blast Radius — V3

Python test-selection engine for the Builders Buildathon RWX challenge.

## Submission

The top-level Dockerfile builds an image using pinned SQLGlot base revision `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`. The image writes one JSON line per commit.

This package contains the *same application source files* as the locally tested Bizz01 V3 ReadyToRun ZIP. It excludes the official sample data, sample answer keys, and build output.

### Local verification

Place the organizer's `blast-radius-sample.tar.gz` in this folder for local testing, then run on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

Observed on the 30 labeled sample commits: 144.966 simulated seconds, zero missed commits. CPU time is additional. The hidden evaluation may differ; no official V3 score is claimed.
