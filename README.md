# leanVM-b state anchor benchmark

Reproducible state anchor hash counts from real Ethereum mainnet proofs, with two batches of leanVM-b timing measurements. The benchmark compares a direct state root, an EIP-7807 block root, and the RLP block hash under one uniform BLAKE3 cost model.

**The main result:** small differences in hash count can have almost no timing effect until they cross a committed witness padding boundary.

| Observation | Original batch | Independent repeat |
| --- | ---: | ---: |
| Proving spread across 141, 146, and 161 hashes | 0.71% | 0.99% |
| Proving increase from 508 to 513 hashes | 29.90% | 27.74% |
| Median proving shift across all 24 workloads | Reference | +3.52% |

The 508 → 513 jump appeared in all 12 process sessions across both batches. Each batch contains 1,440 samples: 24 workloads, six fresh processes, and ten measured passes per process after three warmups per workload.

![Independent repeat: proving time, committed witness cells, proof size, and verification time](reruns/2026-09-09-independent-repeat/figure-3-leanvm-timing.png)

These are **synthetic serial BLAKE3 calibration programs**, not end to end Ethereum state proofs or private transaction proofs. The host-side analyzer validates actual Keccak MPT proofs, but the VM programs do not execute RLP parsing, trie traversal, SSZ verification, or private application logic.

Both batches used the same recorded machine, OS, toolchain, leanVM-b commit, dependency lock, source hashes, AC power, threads, warmups, repetitions, and workload order. Temperature, CPU frequency, system load, and power mode were not recorded in the original run. Exact environmental equivalence cannot be proven. The intervals describe variation **within each batch**; the 3.52% shift is consistent with ambient machine variation, whose cause was not measured.

## Read the evidence

- [Full report](REPORT.md): mechanism, eight structural cases, validation, measurements, and limits.
- [Independent repeat report](reruns/2026-09-09-independent-repeat/README.md) and [comparison CSV](reruns/2026-09-09-independent-repeat/comparison.csv).
- [Original timing CSV](timing-results.csv) and [raw transcript](timing-raw.txt).
- [Repeat timing CSV](reruns/2026-09-09-independent-repeat/timing-results.csv) and [raw transcript](reruns/2026-09-09-independent-repeat/timing-raw.txt).
- [Mainnet fixture](fixtures/mainnet-0x18bd000.json), [structural counts](usecase-results.csv), and [figure captions](figures/README.md).

## Verify locally

Python 3.11 or newer is recommended. No RPC access or Rust build is needed to check the recorded evidence.

```bash
git clone https://github.com/soispoke/leanvm-b-state-anchor-benchmark.git
cd leanvm-b-state-anchor-benchmark
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python verify_evidence.py
```

The check validates the original file hashes, 13 MPT tests, eight structural cases, 24 recorded chain runs, all 2,880 timing samples, both timing summaries, the comparison CSV, and the SVG figures. It checks recorded proof success and tamper rejection; executing the proofs again requires leanVM-b.

See [REPRODUCING.md](REPRODUCING.md) for live proof runs, timing collection, and figure export. The implementation is pinned to [leanVM-b commit `8494c5d`](https://github.com/leanEthereum/leanVM-b/tree/8494c5d5df323f2b97ed89272942a4bee6247078).

## Repository contents

| Files | Purpose |
| --- | --- |
| `analyze_fixtures.py`, `test_analyze_fixtures.py`, `fixtures/` | Validate the pinned Ethereum proofs and derive structural counts |
| `usecase_hash_bench.rs` | Execute the 24 counted workloads in leanVM-b |
| `timing_hash_bench.rs`, `run_timings.py`, `analyze_timings.py` | Original timing program, collector, and bootstrap analysis |
| `reruns/2026-09-09-independent-repeat/` | Complete second batch, comparison, report, and figure |
| `make_figures.py`, `render_figures.py`, `figures/` | Figure source and SVG/PNG exports |
| `verify_evidence.py`, `check_artifacts.py`, `evidence-sha256.txt` | Evidence integrity and consistency checks |
| `state_anchor_bench.rs`, `raw-results.txt`, `results.csv` | Earlier 400-chain calibration, retained as historical evidence |

See [PROVENANCE.md](PROVENANCE.md) for the export's preservation rules and tooling changes.
