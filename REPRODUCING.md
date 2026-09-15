# Verify and reproduce

Run commands from the repository root. Python 3.13 and the pinned packages below reproduce the analysis and figures. Building the backend additionally requires Git, Rust 1.97.1 and rustfmt. The measured setup is recorded in [provenance](PROVENANCE.md).

## Check the published evidence

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m owner_state.verify_artifacts
python -m owner_state.plot_figures --check
python -m unittest test_analyze_fixtures -v
python -m unittest discover -s real_state -p 'test_*.py' -v
python -m unittest discover -s owner_state -p 'test_*.py' -v
```

The evidence checker validates raw logs, hashes, the collection schedule, environment records, phase accounting and derived data. Figure checking regenerates SVGs without changing the committed artwork. Some optional reference and native-patch tests skip until their dependencies are installed below. No Ethereum RPC request is needed.

## Regenerate programs and verify saved proofs

```bash
python -m owner_state.run setup
python -m owner_state.run generate
python -m owner_state.verify_artifacts --generated
python -m owner_state.run verify --run owner_state/results/collect-20260915T094023087152Z
```

Setup checks out pinned leanVM-b, validates its Cargo lock and patches, then builds the profiled runner. `generate` defaults to the three measured `cse_dce` programs. Regenerated program, public-input and witness bytes must match the recorded hashes. Each saved proof is verified in a fresh directory containing only the program, public input and proof. Building and verification are portable; timings depend on the machine and toolchain.

For all independent reference and instrumentation checks:

```bash
git clone https://github.com/ethereum/remerkleable.git local-runs/remerkleable
git -C local-runs/remerkleable checkout --detach 2f0baeef0082d4278acaef7d822deb7009d7db7e
PYTHONPATH=local-runs/remerkleable python -m unittest discover -s real_state -p 'test_*.py' -v
python -m real_state.run setup
cargo test --manifest-path vendor/leanVM-b/Cargo.toml --locked --release --test real_state_bench
python -m unittest discover -s owner_state -p 'test_*.py' -v
```

The separate unprofiled checkout supplies the reference for instrumentation tests. The [CI workflow](.github/workflows/verify.yml) runs these checks and verifies saved proofs on Linux; it does not collect comparison timings.

## Collect a new batch

Use macOS, AC power and enough free memory for a process footprint of about 42 GiB. Finish setup and generation first, then leave the machine free of other demanding work during collection:

```bash
python -m owner_state.collect
```

The collector waits for three consecutive CPU-idle snapshots of at least 90% on AC, records the complete schedule, and runs one warmup per anchor followed by 80 randomized rounds with 11 workers. It verifies saved proofs after collection. Each attempt has a unique record under `local-runs/collections/`; proof logs and reports go to a new `owner_state/results/` directory. Failed and interrupted attempts are retained, and no measured observation is discarded.

The collector requires the published guest programs and inputs. It records the local executable and enforces a single build throughout the batch; rebuilding on another machine need not reproduce the published executable hash. Compare results as a separate batch. CPU temperature and frequency are unmeasured, and preflight checks do not guarantee constant load throughout collection.

Use the collection path printed in the attempt record to analyze new results without overwriting published outputs:

```bash
python -m owner_state.analyze --run owner_state/results/YOUR_COLLECTION --output local-runs/new-analysis
python -m owner_state.plot_figures --run owner_state/results/YOUR_COLLECTION --output local-runs/new-figures
```

To regenerate the published artwork, run `python -m owner_state.plot_figures`. Numeric exports use twelve significant digits for deterministic comparisons; raw logs retain their original precision. PDF and PNG encoding may differ across platforms.
