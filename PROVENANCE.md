# Evidence and provenance

The published comparison is one complete collection from **15 September 2026**: 240 measured proofs and three warmups. No earlier timing batch is pooled into it. [The evidence manifest](owner_state/evidence.json) selects the records and hashes every retained source, log and result needed to check them.

| Record | Contents |
| --- | --- |
| [Collection](owner_state/results/collect-20260915T094023087152Z/report.json) | All 243 proof processes, environment snapshots, timing phases and three saved proofs |
| [Generation](owner_state/results/generate-20260915T093651868962Z/report.json) | Program and input hashes, metadata and source snapshots |
| [Independent verification](owner_state/results/verify-20260915T101414770576Z/report.json) | Three saved proofs verified without witness files |
| [Malformed-witness checks](owner_state/results/negative-20260911T073927482435Z/report.json) | 85 rejected mutations, reused from 11 September with identical measured programs |
| [Hash diagnostics](owner_state/diagnostics/20260911-full-restart/report.json) | 200 standalone execution samples, reused from 11 September with the same executable |
| [Collection plan and preflight](owner_state/collection/README.md) | Frozen schedule, analysis plan, source hashes and quiet-load checks |
| [Build](owner_state/build.json) | Native executable identity and toolchain; [Cargo logs](owner_state/build/) |

The measurement machine was an Apple M5 Max with 128 GB memory, macOS 26.5, Homebrew Rust/Cargo 1.97.1, Python 3.13.15 and 11 Rayon workers on AC power. The backend is [leanVM-b `8494c5d`](https://github.com/leanEthereum/leanVM-b/tree/8494c5d5df323f2b97ed89272942a4bee6247078). Its witness API patch and exclusive-timing patch leave the ISA and proof constraints unchanged. Exact identities are recorded rather than inferred from these version labels.

The [saved mainnet fixture](fixtures/mainnet-0x18bd000.json) contains the block and account/storage proofs. Verification is offline. The hypothetical SSZ root has an [independent reference](real_state/ssz-reference.json); it is not a historical Ethereum block root.

Recorded source snapshots are immutable evidence, including their original paths and comments. Active documentation and runners may be simplified without rewriting those snapshots. The frozen collection contract predates measurement; the run-order diagnostic was added afterward and reveals drift that questions nominal interval coverage.

Superseded calibration experiments, exploratory figures and interrupted attempts are available in the [full-history archive](https://github.com/soispoke/leanvm-b-state-anchor-benchmark/tree/archive/full-history-2026-09-15), at commit `f084c33e1902d8f624aeeb025cf90a98b56c2f19`. They are kept out of the current working tree so there is one current benchmark to read and reproduce.
