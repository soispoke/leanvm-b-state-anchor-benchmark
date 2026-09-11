# Owner-binding figures

**For a short discussion follow-up, attach Figure 2. Add Figure 1 if readers need the relation and anchor paths.** Figure 3 supplies proof costs and timing drift.

The figures use **all 24 measured proofs from the optimized programs**, eight per anchor. This compiler cleanup is applied consistently to all three anchors; it is not a claim of the fastest possible implementation. The complete collection selected in [evidence.json](../evidence.json) retains 48 measured proofs and six warmups, including the baseline compiler. Baseline measurements and compiler comparisons remain in the [full report](../README.md#what-was-optimized) and [source data](../analysis/source-data.csv).

A measurement round is one randomized block containing all six original conditions (three anchors × two compilers). Figures display the three optimized conditions from each round. These figures describe the note opening plus authenticated account/storage lookup; the earlier state-only figures remain separate historical evidence.

## Figure 1. One owner relation through three anchors

![One address opens the note commitment and selects the authenticated account](figure-1-owner-binding.png)

**a,** The same 20-byte witness address opens `H = Keccak256(owner_addr || secret)` and forms the secure account-trie key. The secret is 32 bytes. Both operations are constrained inside the VM. A public digest binds the anchor type, root or hash, H and storage slot. **b,** Three anchor paths reach the same state root: direct exposure; canonical parsing and Keccak hashing of the 634-byte historical RLP header; or five SHA-256 pair hashes in a hypothetical SSZ summary. Every path verifies the same ten-node account proof and two-node storage proof, including canonical RLP and Keccak. The authenticated word is available inside the relation. The Safe singleton value stands in for a stored verification key hash. No signature or recursive authorization is verified. The measured relation has a fixed public encoding shape, including node lengths and RLP layouts. Owner privacy is not established: the pinned backend lacks a zero-knowledge layer, and the benchmark publishes its demonstration witness.

[PDF](figure-1-owner-binding.pdf) · [Editable SVG](figure-1-owner-binding.svg) · [PNG](figure-1-owner-binding.png)

## Figure 2. Block anchors add about 10% in this batch

![All 24 optimized-program proof measurements and paired anchor comparisons with uncertainty](figure-2-proving-results.png)

**a,** All eight fresh-process proving times per anchor for the optimized programs (24 total). Dots show individual measurements; black ticks mark medians, also printed at right. The time axis is restricted to the observed range with margins; position, rather than bar length, encodes time. Small vertical offsets separate nearby dots and have no quantitative meaning. The timer includes execution, witness construction, proof construction and return cleanup. It excludes program loading/assembly, witness loading, serialization and verification. **b,** Each point is the geometric mean of eight within-round time ratios, expressed as percentage change. Positive values mean the first anchor is slower. Horizontal bars and bracketed values are 95% Student-t intervals on log ratios (seven degrees of freedom). They are within-batch, exploratory and unadjusted for multiple comparisons, assuming approximately independent, normally distributed round log ratios. The SSZ/RLP contrast is secondary, introduced after an earlier batch and retained before this restart. Its interval includes zero, which does not establish equivalence. Both block anchors retain Keccak state tries; the figure does not test replacing those tries with SSZ. Results concern one fixed-shape mainnet fixture and the recorded machine.

[PDF](figure-2-proving-results.pdf) · [Editable SVG](figure-2-proving-results.svg) · [PNG](figure-2-proving-results.png)

## Figure 3. Supporting costs and timing drift

![Three exclusive phase groups and separate timing-drift plots for each anchor](figure-3-cost-breakdown.png)

**a,** Exclusive wall-time phases for the optimized programs, averaged across eight measurements per anchor. The three groups sum to mean complete proving time: VM execution, witness-table construction, and remaining proof work plus cleanup. The last group combines polynomial commitments/openings, bus proofs, arithmetic constraints, transcript/setup work, padding reduction, finalization, timer gaps and return cleanup. Overlapping background setup CPU time is not added. Labels show mean totals and the share in this last group. The full seven-group breakdown remains in the [source data](../analysis/source-data.csv). **b,** All 24 optimized-program measurements as percentage deviations from each anchor's own median, ordered by measurement round. Each anchor has its own panel with the same vertical scale. Conditions within a round are measured sequentially, not simultaneously. Residual drift remains despite stable power settings. Means in panel a and medians in Figure 2 answer different questions and need not coincide.

[PDF](figure-3-cost-breakdown.pdf) · [Editable SVG](figure-3-cost-breakdown.svg) · [PNG](figure-3-cost-breakdown.png)

## Artwork and source data

Figures are **180 mm wide**, with heights of **139, 136 and 112 mm**. Body text is 7 pt, notes 6.5 pt and bold lowercase panel letters 8 pt. Exports include vector PDFs with embedded TrueType fonts, SVGs with editable text and 600 dpi PNGs. Direct labels and separate rows or panels identify anchors without relying on color. Axis labels use explicit quantities and units; comparison plots mark zero change, and stacked costs start at zero.

The layout follows the dimensions and typography in Nature's [current formatting guide](https://www.nature.com/nature/for-authors/formatting-guide) and [figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/), checked September 11, 2026. PDF renders are checked for label spacing, clipping and font embedding. This is an artwork specification check, not a claim of journal acceptance. Retain the captions when reusing the figures, and use the vector exports at their intended print width.

The collection uses one Apple M5 Max with 128 GiB RAM, macOS 26.5, eleven Rayon workers, AC power and the same pinned native-target executable. Each condition has one fresh-process warmup, then eight measured fresh processes in randomized Williams order. Two attempts interrupted by power changes and one stopped at the user's request were retained and excluded as entire batches before the first completed September 11 batch. The user then requested the complete sequential restart selected here. Each timing stage began after three CPU-idle snapshots above 90% on AC power; no local build, diagnostic or figure work ran during proof collection. The earlier complete batch remains separate. Temperature and CPU frequency were not measured. The intervals describe the selected batch, not reproducibility across machines or independent batches.

- [All proof samples and seven exclusive phase groups, including labeled warmups](../analysis/source-data.csv)
- [Paired comparisons](../analysis/comparisons.csv)
- [Instruction counts for every hash call](../analysis/hash-instructions.csv)
- [All 200 standalone hash execution samples](../analysis/hash-diagnostic-samples.csv)
- [Hash diagnostic summaries](../analysis/hash-diagnostic-summary.csv)
- [Power, battery level and load at every proof endpoint](../analysis/environment.csv)
- [Machine-readable summary, including instruction and commitment counts](../analysis/summary.json)
- [Raw evidence selection and hashes](../evidence.json)
- [Figure generator](../plot_figures.py)

Hash execution diagnostics include input/output constraints. They are not additive proof-construction costs and are not subtracted from complete proving times.

```bash
python -m pip install -r real_state/figure-requirements.txt
python -m owner_state.plot_figures --run owner_state/results/collect-20260911T074413358669Z
python -m owner_state.plot_figures --run owner_state/results/collect-20260911T074413358669Z --check
```

Use the collection path from `evidence.json`. Verification recomputes SVGs deterministically from raw measurements; PDF and PNG encoders can vary between library/platform builds. See the [full report](../README.md) for the statement, validation and limits.
