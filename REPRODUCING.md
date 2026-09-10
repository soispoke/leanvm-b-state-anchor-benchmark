# Reproducing the benchmark

Run the commands below from this repository's root unless a command explicitly changes directory. The recorded measurements are from September 9, 2026. Checking those records is separate from collecting a new batch.

## Verify the recorded evidence

Use Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python verify_evidence.py
```

`requirements.txt` preserves the experiment's two direct dependency pins. `requirements-lock.txt` additionally pins the transitive Python dependencies resolved for this repository's verification environment. The latter is an export-time lock, not a claim about unrecorded original transitive versions.

Verification uses the saved RPC fixture and does not call Ethereum RPC providers. Regenerated outputs go to temporary directories and are compared with the committed files. File timestamps are ignored because they do not survive Git clones. The PNG copies are checked against their recorded SHA-256 hashes and dimensions; the SVG masters are regenerated from the data.

For individual checks:

```bash
python test_analyze_fixtures.py -q
python analyze_fixtures.py
python check_artifacts.py
```

## Prepare leanVM-b for live runs

The recorded environment was Apple M5 Max, 128 GB RAM, macOS 26.5, Homebrew Rust and Cargo 1.97.1, and 11 Rayon workers on AC power. Exact compiler details and source hashes appear at the beginning of both timing transcripts. Other machines and toolchains can produce different timings.

Clone the pinned upstream source into an ignored directory:

```bash
mkdir -p vendor
git clone https://github.com/leanEthereum/leanVM-b.git vendor/leanVM-b
git -C vendor/leanVM-b checkout --detach 8494c5d5df323f2b97ed89272942a4bee6247078
python - <<'PY'
from pathlib import Path
import hashlib
expected = "0c60e536366da5198d5536c3fdade9a7f20d48d070ee3093758f4b73712a2bf6"
actual = hashlib.sha256(Path("vendor/leanVM-b/Cargo.lock").read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"Cargo.lock mismatch: {actual}")
print("Pinned Cargo.lock verified")
PY
rustc -Vv
cargo -V
```

The pinned upstream tree includes its local `vendor/flock-core`, `vendor/flock-prover`, and `xmss` dependencies. Cargo downloads the remaining dependencies according to its committed lock. Install Rust separately and select the recorded toolchain if matching the original setup is your goal.

Execute all 24 structural calibration programs:

```bash
cp usecase_hash_bench.rs vendor/leanVM-b/tests/usecase_hash_bench.rs
(
  cd vendor/leanVM-b
  RAYON_NUM_THREADS=11 cargo test --locked --release --test usecase_hash_bench -- --nocapture --test-threads=1
)
```

This runs real leanVM-b proving, verification, and tamper checks for the counted serial hash programs. It does not implement Ethereum proof semantics inside the VM.

## Collect a new timing batch

The original collector is preserved unchanged because its hash is recorded in both batches. It invokes macOS `system_profiler` and `pmset`, so use macOS for this command. The fixture and evidence checks are portable. Put new results under `local-runs/` to preserve the published evidence:

```bash
mkdir -p local-runs/new-batch
python run_timings.py vendor/leanVM-b \
  --sessions 6 --repeats 10 --warmups 3 --threads 11 \
  --output local-runs/new-batch/timing-raw.txt
python - <<'PY'
from pathlib import Path
import analyze_timings
analyze_timings.RAW = Path("local-runs/new-batch/timing-raw.txt")
analyze_timings.OUTPUT = Path("local-runs/new-batch/timing-results.csv")
analyze_timings.main()
PY
```

The collector checks the upstream commit, refuses tracked upstream changes, uses `cargo --locked`, and verifies that the dependency lock is unchanged. It creates an untracked test wrapper in the leanVM-b checkout. Its default output would overwrite the original transcript, so keep the explicit `--output` above.

Keep AC power and the recorded settings fixed when comparing with the saved batches. Record temperature, CPU frequency, system load, and power mode separately if you need evidence about those conditions. The original collector does not capture them. Repeating a setup cannot guarantee identical ambient conditions or wall clock results.

To analyze the saved repeat in isolation without overwriting it:

```bash
mkdir -p local-runs/reanalysis
python - <<'PY'
from pathlib import Path
import analyze_timings
analyze_timings.RAW = Path("reruns/2026-09-09-independent-repeat/timing-raw.txt")
analyze_timings.OUTPUT = Path("local-runs/reanalysis/timing-results.csv")
analyze_timings.main()
PY
```

## Regenerate figures

SVG generation uses only the Python standard library:

```bash
python make_figures.py
```

PNG export needs Chrome, Chromium, or Brave. Alternatively, install Node.js and the `sharp` package locally (`npm install --no-save --package-lock=false sharp`):

```bash
python render_figures.py
```

For a separately installed Sharp package, set `SHARP_NODE` to the Node executable and `SHARP_MODULE` to the package directory. PNG rendering can vary with renderer and installed fonts. The recorded PNGs are included for sharing; regenerating a different rasterization will intentionally fail the evidence hash check until an explicitly documented new artifact is added.

Generate the repeat's SVG into an ignored output directory:

```bash
mkdir -p local-runs/repeat-figure
python - <<'PY'
from pathlib import Path
import make_figures
make_figures.TIMING_RAW = Path("reruns/2026-09-09-independent-repeat/timing-raw.txt")
make_figures.TIMING_RESULTS = Path("reruns/2026-09-09-independent-repeat/timing-results.csv")
make_figures.FIGURES = Path("local-runs/repeat-figure")
make_figures.make_timing_figure()
PY
```

## Earlier 400-chain calibration

The older harness combines representative paths in a serial chain. Its three samples per program are sanity checks and should not be substituted for the repeated timing experiment:

```bash
cp state_anchor_bench.rs vendor/leanVM-b/tests/state_anchor_bench.rs
(
  cd vendor/leanVM-b
  RAYON_NUM_THREADS=11 STATE_ANCHOR_BATCH=400 STATE_ANCHOR_REPEAT=3 \
    cargo test --locked --release --test state_anchor_bench -- --nocapture
)
```
