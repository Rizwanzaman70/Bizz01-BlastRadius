# Bizz01 — RWX Blast Radius (Builders Buildathon 2026)

A Python test-impact selector for the pinned [`sqlglot`](https://github.com/tobymao/sqlglot) source tree. **This project contains no memorized sample answers or patch-fingerprint lookup tables.** It is intended as a public GitHub submission with `Dockerfile` at repository root.

## Official interface

On startup, read `/data/tests.json` and `/data/commits/*.patch`. For **each** patch print exactly one compact JSON line, e.g.:

```json
{"commit":"abcd","workers":[[12,845],[3,77]]}
```

Only those two keys are printed; stdout is reserved for answers and diagnostics go to stderr. Workers use unique test numbers from `tests.json`, with no more than 8 nonempty workers. `"workers":[]` is allowed.

## How the selector works

1. During the Docker **build** (not charged as runtime CPU), download only the permitted, exact `sqlglot` commit `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`. The pinned official `requirements.lock` is installed from PyPI. The build runs pytest on the base revision with `SKIP_INTEGRATION=0` and collects per-test Python function-call coverage, with a time budget of 390 seconds.
2. On each independent patch, parse all changed files and hunk line positions; map affected Python function/class definitions to tests that executed the function on the base revision.
3. Supplement with static test-source symbol references and direct/structural test references. SQL fixture changes use the corresponding test method **name** (`tests/fixtures/optimizer/simplify.sql` -> `test_simplify`) with a fallback to the owning test module if no reliable name match exists.
4. A change that can be verified against the exact base source as a Python token-equivalent comment-only edit can select no tests; SQL fixture comments are **never** assumed harmless.
5. For common source modules and missing/partial coverage, use conservative suite-level fallbacks. Any test not profiled in the build is considered potentially affected.
6. Greedily balance tests by recorded millisecond runtime for each worker count from 1 to 8; choose the cheapest schedule after including 2000 ms per occupied worker.

## Run the official sample (Windows 11 / PowerShell)

Requirements: Docker Desktop running with Linux containers, `python` on `PATH`, PowerShell, and Windows `tar` (included in recent Windows).

1. Extract `Bizz01_BlastRadius_Submission.zip` into a working folder. Open a PowerShell terminal in its `Bizz01_BlastRadius` directory.
2. Place the organizer's **unchanged** `blast-radius-sample.tar.gz` beside `Dockerfile`. You can use the archive you downloaded from the competition site.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

The script extracts the sample if needed, builds the image, runs the image with the official resource limits, saves a UTF-8 **without BOM** `predictions.jsonl`, and runs the bundled `score.py` against `sample/answers.json`.

You can also use the organizer's `Makefile`: place **only the submission files** from this folder in the root of the extracted kit, keeping their original `sample/` directory and official `score.py`, then run `make sample`. The starter's `Makefile` invokes `docker build` on the current directory.

## Offline fallback-only sanity check

When Docker is unavailable, run this **limited** check against the extracted organizer kit:

```powershell
python benchmark_offline.py C:\path\to\official\kit
```

This runs `selector.py` **without** the pinned source checkout or build-generated coverage map. It tests the conservative fallback behavior and uses the original local scorer. This is **not** the score of the built image.

With the 30 organizer sample commits uploaded on 2026-11-21, the fallback-only configuration scored **520.815 simulated seconds, 0 missed commits**. By comparison the official run-every-test starter baseline is **1614.1 simulated seconds**. CPU time is excluded. This result does not prove the build-time coverage variant or unseen final commits will obtain the same score.

## Submit

1. Create a **public repository owned by your team** and place **the contents of this folder at the repository root**, not within an additional subfolder.
2. Push to GitHub; note the repository URL and optional 40-character commit SHA.
3. Submit through the RWX track form on the Builders Buildathon website before the cutoff.
4. Keep the repo public and all submitted commits available until final results are published.

**Do not commit** `sample/answers.json` or memorized mappings from a patch or category of edit to tests that fail. The runtime selector never reads that file. The build fetches only the pinned upstream source and public PyPI dependencies, not user-controlled URLs.

## Files

| Filename | Purpose |
| --- | --- |
| `Dockerfile` | Submission image and pinned runtime environment |
| `fetch_sqlglot.py` | Fetches only the exact pinned upstream source archive |
| `main.py` | Competition input/output protocol |
| `selector.py` | Diff parser, impact selection, worker allocation |
| `build_map.py` | Static AST/test-symbol maps and base-revision coverage build |
| `coverage_plugin.py` | Build-time pytest function-call profiler |
| `requirements.lock` | Official starter kit's dependency lock versions |
| `run_windows.ps1` | Extract/build/run/score on Windows |
| `benchmark_offline.py` | No-Docker fallback-check only |
| `test_selector.py` | Seven synthetic unit tests |

## Limitations and caution

- A full Docker build has **not** been executed in the artifact-authoring environment because Docker is unavailable. The image must be built and scored locally before relying on it as a submission.
- Test coverage collected on the original revision is imperfect: newly introduced control flow, dynamically loaded modules, and fixture data can affect tests that were not observed; broad fallbacks reduce but do not eliminate this risk.
- The official scorer adds your container's CPU usage to simulated CI time, and only the hidden final commits decide prizes.

## 100-second competition goal (November 21 optimization)

Target: **100 s total on the official 30-commit sample**, including CPU time, with zero missed commits.
This is a target, **not a measured score**. The only validated score here is the
coverage-free local benchmark: **520.815 simulated seconds, zero misses**.

The selector is now optimized for a completed or partially available build-time
function-call coverage map: it does not run all *unprofiled* tests on every
commit. Changes in files without mapped functions still go through structural
fallbacks. This can greatly cut the per-commit selection cost, but may raise
miss risk, especially if pytest profiling was interrupted. Measure on the
actual Docker build before submitting. Do **not** rely solely on the fallback
benchmark as it runs with no pinned sqlglot checkout and no coverage map.

To compare against the target on Windows (Docker Desktop running):

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

Check the scorer's `Simulated` and `Misses` lines. A missed commit costs
300 seconds, so minimizing tests without adequate coverage is counterproductive.
The scorer only reports sample misses after generating predictions; the
implementation does not read the sample answer labels or memoize patches.
