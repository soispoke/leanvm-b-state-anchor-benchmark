# Results and statement

**RLP and SSZ block anchors add about 9% proving time over a direct state root in this batch. The SSZ/RLP difference is unresolved.** All three paths prove the same note opening and account/storage lookup inside leanVM-b.

| Anchor | Median prove time | Mean execution | Mean witness construction | Mean remaining proof work |
| --- | ---: | ---: | ---: | ---: |
| Direct state root | 6.41 s | 0.43 s | 0.58 s | 5.46 s |
| RLP block hash | 7.05 s | 0.77 s | 0.71 s | 5.58 s |
| Hypothetical SSZ summary | 7.03 s | 0.77 s | 0.70 s | 5.56 s |

There are 80 measurements per anchor, collected in randomized rounds. Paired geometric mean overheads relative to direct state are **+9.09% [+8.61%, +9.57%]** for RLP and **+8.80% [+8.15%, +9.45%]** for SSZ. SSZ relative to RLP is **−0.27% [−0.64%, +0.11%]**; an interval containing zero does not establish equivalence.

These are nominal 95% Student-t intervals on within-round log ratios. Early drift questions their independence assumption: RLP overhead changes from 6.75% in the first 20 rounds to 10.21% in the last 20; SSZ changes from 6.23% to 10.33%. No samples were removed. Interval coverage is not established, and this one batch does not measure variation across machines or independent sessions. [Run-order diagnostic](analysis/run-order-diagnostics.csv).

## What is proved

A witness contains a 20-byte owner address, a 32-byte secret, the account and storage proofs, and the required header or SSZ branch. The program checks:

1. `H = Keccak256(owner_addr || secret)` matches the public note commitment.
2. The **same address** selects an account authenticated against the state root.
3. The public storage slot selects a word authenticated against that account's storage root.
4. The state root matches the selected public anchor, directly or through the RLP/SSZ header path.

The public statement binds the anchor type, root or hash, note commitment and storage slot through a domain-separated VM public digest. The stored word remains available inside the relation. Parsing, hash computations, witness Booleanity and input binding are constrained inside the VM; the host does not supply trusted hash results.

The [fixture](../fixtures/mainnet-0x18bd000.json) is a Safe account's slot 0 at mainnet block **25,939,968**. Its singleton address stands in for a stored verification key hash. This is a fixed public proof shape, including node lengths and RLP layouts, rather than a general variable-length Ethereum verifier. The demonstration secret is public. Signature verification, recursive authorization and owner privacy are outside the measured relation; the pinned backend has no implemented zero-knowledge layer. [Privacy inspection](PRIVACY.md).

## What changes between anchors

The direct path starts with a public state root. The RLP path parses and Keccak-hashes the 634-byte historical block header. The SSZ path checks five SHA-256 pair hashes against a hypothetical summary root. Every path then verifies the same ten-node account proof and two-node storage proof, including canonical RLP and Keccak.

All measurements use the same `cse_dce` compiler: it shares repeated expressions and removes unused computations while preserving constraint checks. These optimizations change how the same hashes are compiled, not the cryptographic algorithms. Reference and candidate implementations remain in the source for correctness tests and supporting hash diagnostics.

Both state tries remain Keccak in the SSZ condition. The benchmark therefore measures the cost of changing header authentication, not replacing Ethereum's state tree or implementing a full private transaction.

## Where the time goes

The primary timer covers the complete `prove()` call: VM execution, witness-table construction, proof construction and return cleanup. It excludes program loading/assembly, witness loading, serialization and verification. The phase columns above are arithmetic means and sum to mean total time; headline absolute times are medians.

Remaining proof work accounts for **79–84%** of total time. Keccak and SHA account for **98.6–98.8% of guest instructions**, but standalone hash execution times cannot be subtracted to infer additive proof-construction costs. Shared tables, padding and polynomial commitments prevent that interpretation.

Proofs occupy 834,752, 835,712 and 836,384 bytes for direct, RLP and SSZ respectively. Maximum process footprints are about 38.78, 41.22 and 41.27 GiB. [Full source data and phase breakdown](analysis/source-data.csv).

## Evidence and methods

Collection used one Apple M5 Max with 128 GB memory, macOS 26.5, 11 workers and AC power. Three qualifying idle snapshots preceded collection; power, settings, load and thermal-warning status were recorded around every proof. Temperature and CPU frequency were not measured. Stable settings did not prevent timing drift.

All 243 proof processes passed proof and tamper checks. Three saved proofs verified independently without witness files. The 85 malformed-witness checks and 200 standalone hash execution diagnostics were collected on 11 September and reused with matching programs or executable; they were not rerun with the 15 September timings.

[Figures and captions](figures/README.md) · [Measurement method](CONTRACT.md) · [Raw records](results/README.md) · [Provenance](../PROVENANCE.md) · [Reproduction](../REPRODUCING.md)
