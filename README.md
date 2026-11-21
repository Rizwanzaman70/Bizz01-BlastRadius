# Bizz01 — RWX Blast Radius (Builders Buildathon 2026)

A Python test-impact selector for the pinned [`sqlglot`](https://github.com/tobymao/sqlglot) source tree. **This project contains no memorized sample answers or patch-fingerprint lookup tables.** It is intended as a public GitHub submission with `Dockerfile` at repository root.

## Official interface

On startup, read `/data/tests.json` and `/data/commits/*.patch`. For **each** patch print exactly one compact JSON line, e.g.:

```json
{"commit":"abcd","workers":[[12,845],[3,77]]}
```

Only those two keys are printed; stdout is reserved for answers and diagnostics go to stderr. Workers use unique test numbers from `tests.json`, with no more than 8 nonempty workers. `"workers":[]` is allowed.

## How the selector works

1. During the Docker **build** (not charged as runtime CPU), download only the permitted, exact `sqlglot` commit `eb11aec4be8cb2122afe713a4816662c3f0fb2fa`. The pinned official `requirements.lock` is installed from PyPI. The build runs pytest on the base revision with `SKIP_INTEGRATION=0` and collects per-test Python function-call coverage, with a time budget of 330 seconds.
2. On each independent patch, parse all changed files and hunk line positions; map affected Python function/class definitions to tests that executed the function on the base revision.
3. Supplement with static test-source symbol references and direct/structural test references. SQL fixture changes use the corresponding test method **name** (`tests/fixtures/optimizer/simplify.sql` -> `test_simplify`) with a fallback to the owning test module if no reliable name match exists.
4. A change that can be verified against the exact base source as a Python token-equivalent comment-only edit can select no tests; SQL fixture comments are **never** assumed harmless.
5. For common source modules and missing/partial coverage, use structural suite-level fallbacks. The absence of a profiled call is not treated as definitive proof of no impact; selective smoke tests help mitigate it, but may still miss unseen failures.
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

## November 21 build repair — GitHub archive symlinks

An earlier ZIP could fail during `RUN python fetch_sqlglot.py` with
`ValueError: Unexpected archive link/device`. That was a **downloader bug**:
GitHub's pinned source archive includes links, which the older unpacker rejected.
This version preserves safe internal links using Python 3.13's `tarfile.data_filter`
and ignores any links escaping the source tree. A synthetic test checks both
cases. The build-time coverage collection limit is 330 seconds to leave room
under the organizer's 10-minute build cap, though slower downloads or package
installs can still exceed that budget.

To upgrade an already extracted copy, replace `fetch_sqlglot.py` and
`build_map.py` with the new versions, then rerun `run_windows.ps1`. Existing
`sample` test data can be kept; it is excluded from the Docker image.


## November 21 diagnostic-informed revision

The selector now supplements per-function coverage with general, base-revision
module dependencies for optimizer, parser, typing, serializer, and dialect-class
changes. It never reads sample answers or checks commit IDs.

On the organizers' 30-commit sample, a *reconstructed* benchmark combining the
previous Docker predictions with the new general selection rules scored
187.265 simulated seconds and 0 misses. This is **not** a fresh Docker test;
actual CPU time is excluded. Validate with `run_bizz01_fast.ps1` before
submitting. The prior Docker score was 1609.320s with 5 misses.

To test with your existing image on Windows:
1. Keep Docker Desktop running.
2. Replace `selector.py` in your original project folder.
3. Copy `run_bizz01_fast.ps1` next to it if not already present.
4. In PowerShell, inside that folder, run:

   `powershell -ExecutionPolicy Bypass -File .\run_bizz01_fast.ps1`

After validating, rebuild with `run_windows.ps1` to ensure the final public
Dockerfile incorporates the updated source code (the fast test uses a bind
mount and does *not* modify the existing image).

The 100-second target has not been reached. Even the sample oracle minimum is
approximately 94 seconds before CPU time, so this target leaves almost no
headroom for robust unseen-commit coverage.


## November 21 update: under-150-second candidate (v3)

This revision adds three **general-purpose** runtime-budgeting rules, all
based on pinned source metadata and test IDs/runtimes rather than sample
failure labels:

- Optimizer code with narrowly observed call coverage uses those observed
  tests; when the base profile spans multiple optimizer tests, the selector
  retains broader regression tests and cross-suite integration protection.
- Shared type-annotation code additionally runs the suite's general optimizer
  integration test, since class-field reads do not register as function calls.
- Changes to outer dialect configuration classes trigger a low-cost optimizer
  smoke set. Nested lexer/tokenizer class attributes use direct dialect tests.
- When an affected function wasn't executed in the pinned baseline despite
  other functions being profiled in its module, inexpensive module tests run
  rather than every long integration test. This is an explicit risk/speed
  tradeoff and cannot guarantee all future regressions will be detected.

**Local projection:** Using the organizer's 30 sample patches, the 2026-11-21
exported coverage maps, and a simulator for source-verified comment-only edits
that the previous **real** Docker run already classified as no-ops, the official
``score.py`` reports **144.474 simulated seconds with zero missed commits**.
This is not a new Docker result; CPU usage is not included and actual
competition scoring can differ. A fresh Docker test is required before
claiming the target was achieved.

### Verify using the already built Docker image

Extract the small v3 upgrade, overwrite `selector.py` and
`run_bizz01_fast.ps1` in the existing project folder, start Docker Desktop,
and execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_bizz01_fast.ps1
```

The script bind-mounts your new `selector.py` over the selector in your already
built image, and uses the image's exact pinned SQLGlot source and coverage maps.
It prints **Simulated** and **Misses** from the official local scorer. CPU time
isn't shown, but the leaderboard will add it. For the final submission you
**must rebuild** with `run_windows.ps1` so your new selector is baked into
Docker and works without the bind mount. The final also uses unseen commits.
