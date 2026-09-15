# Owner-binding figures

**For a short discussion follow-up, attach Figure 2. Add Figure 1 if readers need the relation and anchor paths.** Figure 3 supplies proof costs and timing drift.

The figures use **all 240 measured proofs from the optimized programs**, 80 per anchor, collected on September 15. This compiler cleanup is applied consistently to all three anchors; it is not a claim of the fastest possible implementation. Three labeled warmups are excluded from the estimates.

A measurement round is one randomized block containing each of the three anchors once. These figures describe the note opening plus authenticated account/storage lookup.

## Figure 1. One owner relation through three anchors

![One address opens the note commitment and selects the authenticated account](figure-1-owner-binding.png)

**a,** The same 20-byte witness address opens `H = Keccak256(owner_addr || secret)` and forms the secure account-trie key. The secret is 32 bytes. Both operations are constrained inside the VM. A public digest binds the anchor type, root or hash, H and storage slot. **b,** Three anchor paths reach the same state root: direct exposure; canonical parsing and Keccak hashing of the 634-byte historical RLP header; or five SHA-256 pair hashes in a hypothetical SSZ summary. Every path verifies the same ten-node account proof and two-node storage proof, including canonical RLP and Keccak. The authenticated word is available inside the relation. The Safe singleton value stands in for a stored verification key hash. No signature or recursive authorization is verified. The measured relation has a fixed public encoding shape, including node lengths and RLP layouts. Owner privacy is not established: the pinned backend lacks a zero-knowledge layer, and the benchmark publishes its demonstration witness.

[PDF](figure-1-owner-binding.pdf) · [Editable SVG](figure-1-owner-binding.svg) · [PNG](figure-1-owner-binding.png)

## Figure 2. Block anchors add about 9% in this batch

![All 240 optimized-program proof measurements and paired anchor comparisons with uncertainty](figure-2-proving-results.png)

**a,** Empirical cumulative distributions of all 80 fresh-process proving times per anchor (240 total), on identical axes. At each time, the curve shows the percentage of measurements at or below that time. Every observation contributes a step; no binning, smoothing or outlier removal is applied. Black dots at 50% and dashed vertical lines mark medians, also printed above each panel. The time axes use a restricted range with margins. The timer includes execution, witness construction, proof construction and return cleanup. It excludes program loading/assembly, witness loading, serialization and verification. **b,** Each point is the geometric mean of 80 within-round time ratios, expressed as percentage change. Positive values mean the first anchor is slower. Horizontal bars and bracketed values are nominal 95% Student-t intervals on log ratios (79 degrees of freedom). RLP/direct is +9.09% [+8.61%, +9.57%]; SSZ/direct is +8.80% [+8.15%, +9.45%]. The secondary SSZ/RLP contrast is −0.27% [−0.64%, +0.11%]. Its interval includes zero, which does not establish equivalence. Intervals are within-batch, exploratory and unadjusted for multiple comparisons, assuming approximately independent, normally distributed round log ratios. Both block anchors retain Keccak state tries; the figure does not test replacing those tries with SSZ. The paired anchor/direct ratios also drift: the first and last 20-round quarters give RLP overheads of 6.75% and 10.21%, and SSZ overheads of 6.23% and 10.33%. Their lag-one log-ratio correlations are 0.44 and 0.34. Independence is therefore questionable; nominal interval coverage is not established. [Post-collection diagnostic](../analysis/run-order-diagnostics.csv). Results concern one fixed-shape mainnet fixture and the recorded machine.

[PDF](figure-2-proving-results.pdf) · [Editable SVG](figure-2-proving-results.svg) · [PNG](figure-2-proving-results.png)

## Figure 3. Supporting costs and timing drift

![Three exclusive phase groups and separate timing-drift plots for each anchor](figure-3-cost-breakdown.png)

**a,** Exclusive wall-time phases for the optimized programs, averaged across 80 measurements per anchor. The three groups sum to mean complete proving time: VM execution, witness-table construction, and remaining proof work plus cleanup. The last group combines polynomial commitments/openings, bus proofs, arithmetic constraints, transcript/setup work, padding reduction, finalization, timer gaps and return cleanup. Overlapping background setup CPU time is not added. Labels show mean totals and the share in this last group. The full seven-group breakdown remains in the [source data](../analysis/source-data.csv). **b,** All 240 optimized-program measurements as percentage deviations from each anchor's own median, ordered by measurement round. Each anchor has its own panel with the same vertical scale. Conditions within a round are measured sequentially, not simultaneously. Residual drift remains despite stable power settings. Means in panel a and medians in Figure 2 answer different questions and need not coincide.

[PDF](figure-3-cost-breakdown.pdf) · [Editable SVG](figure-3-cost-breakdown.svg) · [PNG](figure-3-cost-breakdown.png)

## Artwork and source data

Figures are **180 mm wide**, with heights of **139, 136 and 112 mm**. Body text is 7 pt, notes 6.5 pt and bold lowercase panel letters 8 pt. Exports include vector PDFs with embedded TrueType fonts, SVGs with editable text and 600 dpi PNGs. Direct labels and separate rows or panels identify anchors without relying on color. Axis labels use explicit quantities and units; comparison plots mark zero change, and stacked costs start at zero.

The layout follows the dimensions and typography in Nature's [current formatting guide](https://www.nature.com/nature/for-authors/formatting-guide) and [figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/), checked September 11, 2026. PDF renders are checked for label spacing, clipping and font embedding. This is an artwork specification check, not a claim of journal acceptance. Retain the captions when reusing the figures, and use the vector exports at their intended print width.

The collection uses one Apple M5 Max with 128 GiB RAM, macOS 26.5, eleven Rayon workers, AC power and the same pinned native-target executable. Each condition has one fresh-process warmup, then 80 measured fresh processes in randomized Williams order. Thirteen complete six-round cycles balance positions and predecessors; two additional rows complete the schedule. Three consecutive preflight snapshots were at least 90% CPU idle on AC. No local build, diagnostic or figure work ran during collection. All 243 proofs verified and all recorded environment checks passed. The three saved proofs also verified in fresh processes without witness files. Temperature and CPU frequency were not measured; the visible early timing drift is retained. The intervals describe this batch, not reproducibility across machines or independent batches.

- [All proof samples and seven exclusive phase groups, including labeled warmups](../analysis/source-data.csv)
- [Paired comparisons](../analysis/comparisons.csv)
- [Descriptive checks of paired-ratio drift and lag-one correlation](../analysis/run-order-diagnostics.csv)
- [Instruction counts for every hash call](../analysis/hash-instructions.csv)
- [All 200 September 11 standalone hash execution samples](../analysis/hash-diagnostic-samples.csv)
- [Hash diagnostic summaries](../analysis/hash-diagnostic-summary.csv)
- [Power, battery level and load at every proof endpoint](../analysis/environment.csv)
- [Machine-readable summary, including instruction and commitment counts](../analysis/summary.json)
- [Raw evidence selection and hashes](../evidence.json)
- [Figure generator](../plot_figures.py)

Hash execution diagnostics are reused from September 11 with the identical binary. They include input/output constraints. They are not additive proof-construction costs and are not subtracted from complete proving times.

```bash
python -m pip install -r requirements.txt
python -m owner_state.plot_figures
python -m owner_state.plot_figures --check
```

Use the collection path from `evidence.json`. Verification recomputes SVGs deterministically from raw measurements; PDF and PNG encoders can vary between library/platform builds. See the [full report](../README.md) for the statement, validation and limits.
