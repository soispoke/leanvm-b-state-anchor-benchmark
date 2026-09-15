# Expanded optimized-anchor measurements

Planned before collection: 80 rounds of all three optimized programs, **240 measured proofs**, plus three fresh-process warmups. This is ten times the eight measurements per anchor in the earlier figures. The earlier batch remains separate.

The native executable, programs, public inputs, witness files and metadata must match `collect-20260911T074413358669Z` byte for byte. The runner retains eleven Rayon workers, AC power and the existing complete-prove timer and phase clocks. Setup, fixture generation and hash diagnostics are reused by identity; they are not remeasured or pooled into this batch.

Seed `20260911` fixes randomized Williams order. For three conditions, forward and reverse rows give balanced six-round cycles. The schedule has thirteen complete cycles and two additional rows. A CPU-idle preflight requires three consecutive snapshots of at least 90% on AC before any warmup. Power, settings, load and thermal-warning status are recorded at every proof endpoint. Temperature and CPU frequency remain unmeasured.

The predeclared analysis uses 80 paired log ratios and Student-t intervals with 79 degrees of freedom, within this batch. Absolute times use medians; phase costs use additive arithmetic means. Every measured observation is retained. A correctness or environment failure stops and preserves the attempt. One saved proof per anchor is verified in a fresh process without witness files after collection. See the [expanded contract](../../CONTRACT.md#september-11-expansion-80-rounds-of-the-selected-programs).

`orchestrate.py` records the setup, full schedule, source snapshots, preflight readings, commands and outcomes in a fresh timestamped attempt subdirectory. An explicit `--output` must name a new directory; existing records are never overwritten.

```bash
python owner_state/repeats/20260911-80-rounds/orchestrate.py
```

## Initial preflight

The initial preflight was stopped before any warmup or measured proof. CPU idle stayed below 90%, and a separate Python process was observed using about 80 GB, leaving roughly 3 GB free. The existing proof processes peak near 42 GiB. `experiment.json` and `preflight.json` preserve this attempt; no timing estimates changed. Resume with the command above after freeing the competing workload.

## Completed September 15 batch

[Attempt record](attempt-20260915T093856598597Z/experiment.json): all **240 measured proofs and three warmups** verified, with no failed environment checks. All three saved proofs also verified without witness files. The batch ran from 09:40:23 to 10:14:14 UTC. All 52 precollection tests passed after exact program/input regeneration; the rebuilt executable matches the previous binary hash. [Workspace recovery and dependency checks](../20260915-recovery/README.md).

Median complete proving times are **6.41 s** for direct state, **7.05 s** for RLP and **7.03 s** for SSZ. Paired changes versus direct state are **+9.09% [+8.61%, +9.57%]** for RLP and **+8.80% [+8.15%, +9.45%]** for SSZ. The secondary SSZ/RLP change is **−0.27% [−0.64%, +0.11%]**, so this batch does not resolve a difference. These are the predeclared nominal 95% within-batch intervals over all 80 pairs. Paired-ratio drift and positive serial correlation question their independence assumption; nominal coverage is not established. The [post-collection diagnostic](../../analysis/run-order-diagnostics.csv) is descriptive and changes no observations or primary estimates.

[Analysis and source data](attempt-20260915T093856598597Z/analysis/) retain all measurements. Early timing drift remains visible; there is no outlier removal or pooling with the earlier batch. Hash diagnostics and the 85 altered-witness checks are reused from the identical September 11 programs and executable.
