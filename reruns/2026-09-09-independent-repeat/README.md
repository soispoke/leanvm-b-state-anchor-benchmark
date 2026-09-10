# Independent Repeat of the leanVM-b State Anchor Timing

## TL;DR

The complete 1,440 sample timing experiment was repeated under the same recorded conditions. Every deterministic result matched exactly, and the central timing shape reproduced in every process: nearby workloads that use the same committed witness size form plateaus, while crossing a padding boundary causes a clear jump. Absolute proving medians were 3.52 percent higher in the second batch, showing that the process bootstrap intervals measure variation within one short batch rather than reproducibility across separate batches.

## Conditions

Both batches used the same Apple M5 Max with 128 GB memory, macOS 26.5, Rust and Cargo 1.97.1, eleven Rayon workers, AC power, leanVM-b commit `8494c5d5df323f2b97ed89272942a4bee6247078`, and Cargo lock hash `0c60e536366da5198d5536c3fdade9a7f20d48d070ee3093758f4b73712a2bf6`. The timing program, runner, and analyzer hashes also match. Each batch ran six fresh processes sequentially. Every process used three warmups and one untimed tamper check per workload, then ten complete passes in the same deterministic shuffled order.

The first batch began at 15:55 UTC and the repeat began at 16:18 UTC on 2026-09-09. Both ran on AC power. The first transcript did not record power mode, temperature, CPU frequency, or system load, so those ambient conditions cannot be proven identical. No monotonic slowdown appears across the repeat's processes or passes.

## Results

All 1,440 paired records have the same workload order, hash count, padded BLAKE3 domain, VM cycles, committed cells, memory use, and proof size. All proofs verified and all tamper checks failed as expected. A separate live run of all 24 leanVM-b chain programs also passed. The artifact checker reran all thirteen MPT tests and eight structural cases, then confirmed that the recorded chain results, timing samples, CSV files, transcripts, and three figures agree.

| Comparison | First batch | Independent repeat |
| --- | ---: | ---: |
| Proving spread across 141, 146, and 161 calls | 0.71% | 0.99% |
| Proving increase from 508 to 513 calls | 29.90% | 27.74% |
| Median shift across all proving workloads | reference | +3.52% |
| Median shift across all verification workloads | reference | +0.90% |

The 508 to 513 call jump appears in every one of the twelve process sessions across both batches. It ranges from 25.7 to 31.3 percent. Across transitions where the committed witness size does not change, the largest change in a batch median is about 1.05 percent.

Only five of the 24 proving interval pairs overlap, and none of the repeat medians falls inside the corresponding first-batch interval. The two batches remain almost perfectly correlated across workloads (`r = 0.9995`), which shows a common timing shift rather than a change in the workload ordering. Two batches are not enough to estimate a reliable interval for variation between batches.

The older 400 transaction calibration was also repeated. All four programs passed with the same cycle counts, committed cells, proof sizes, proof verification, and tamper rejection. Its three timing samples per program remain sanity checks rather than performance evidence.

## Files

- [timing-raw.txt](timing-raw.txt) contains the complete repeat transcript and environment record.
- [timing-results.csv](timing-results.csv) contains the 24 repeat summaries.
- [comparison.csv](comparison.csv) compares every first-batch and repeat median.
- [figure-3-leanvm-timing.svg](figure-3-leanvm-timing.svg) and [figure-3-leanvm-timing.png](figure-3-leanvm-timing.png) render the repeat alone.

## Interpretation

Each additional hash still adds exactly 24 VM cycles. Wall clock proving time is not expected to rise smoothly because leanVM-b commits padded witness tables. Nearby workloads can use the same table size and remain on one plateau, while a small increase that crosses a padding boundary allocates a larger table and produces a visible timing jump. The repeat confirms this mechanism but also shows that absolute milliseconds depend on ambient machine conditions that the current harness does not fully observe.

## See also

- [Full benchmark report](../../REPORT.md)
