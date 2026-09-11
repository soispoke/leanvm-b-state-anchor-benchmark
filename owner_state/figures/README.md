# Owner-binding figures

These figures describe the complete note opening plus account/storage lookup. They use the collection selected in [evidence.json](../evidence.json), with **48 measured proofs, six warmups and every measured observation retained**. They replace the earlier state-only figures as the repository's main presentation; that earlier experiment remains unchanged.

All figures are 183 mm wide, with 6–9 point typography, vector PDF with embedded fonts, editable SVG text and a 600 dpi PNG preview. Colors distinguish the three anchors consistently. The designs use zero-based axes for absolute costs, paired observations for implementation comparisons, and explicit uncertainty instead of ranking noisy medians.

## Figure 1. The measured owner-binding relation

![Owner commitment and state-anchor paths](figure-1-owner-binding.png)

**a,** The same 20-byte witness address is used to open the note commitment `H = Keccak256(owner_addr || secret)` and form the secure account-trie key. The secret is 32 bytes. Both operations are constrained inside the VM. The public digest binds the anchor type, anchor root or hash, H and storage slot. **b,** Three anchor paths reach the same state root: direct exposure; canonical parsing and Keccak hashing of the 634-byte historical RLP header; or five SHA-256 pair hashes in a hypothetical SSZ summary. All paths then verify the same ten-node account proof and two-node storage proof, including canonical RLP and Keccak. The authenticated stored word is available inside the relation. The Safe singleton value stands in for a stored verification key hash; no signature or recursive authorization is verified. This establishes the implemented binding checks, not owner privacy. The pinned backend lacks a zero-knowledge layer, and the benchmark publishes its demonstration witness.

[PDF](figure-1-owner-binding.pdf) · [Editable SVG](figure-1-owner-binding.svg) · [PNG](figure-1-owner-binding.png)

## Figure 2. Proving results and exact work

![All proof samples, paired changes, instructions and commitments](figure-2-proving-results.png)

**a,** All eight measured fresh-process proving times per condition. Open markers show the baseline compiler; filled markers show common-subexpression elimination plus dead-code elimination. Thin lines connect observations from the same randomized block; black ticks are medians. The timer includes VM execution, witness construction, proof construction and return cleanup, excluding program loading/assembly, serialization and verification. **b,** Optimized/baseline time ratios, expressed as percentage changes. Each point is the geometric mean of eight blockwise ratios. Bars are 95% Student-t intervals on log ratios with seven degrees of freedom. They are within-batch, exploratory and unadjusted for multiple comparisons; they assume approximately independent, normally distributed block log ratios. An interval containing zero change does not establish equivalence. **c,** Exact executed instruction counts for each complete owner relation, including four wrapper instructions. **d,** Committed witness field cells reported by the backend, excluding virtual columns and before final aggregate polynomial padding. Each baseline/optimized pair has identical padded table sizes. Block-anchor programs cross a memory/bytecode domain boundary that the direct-state programs do not. This fixture-specific effect must not be generalized to arbitrary owner proofs.

[PDF](figure-2-proving-results.pdf) · [Editable SVG](figure-2-proving-results.svg) · [PNG](figure-2-proving-results.png)

## Figure 3. Execution and proof-construction costs

![Exclusive phase costs, hash instruction share and batch variation](figure-3-cost-breakdown.png)

**a,** Exclusive wall-time phases, averaged arithmetically across eight runs so their sum equals mean complete proving time. The phases are guest execution, witness-table construction, polynomial commitment, memory/instruction bus proof, arithmetic constraints, polynomial opening, and other work/cleanup. The last group includes transcript and claim setup, the mandatory BLAKE3 padding reduction, finalization, timer gaps and outer return cleanup. The backend's background setup overlaps other work; its CPU time is not added to these wall-time totals. **b,** Exact instruction attribution in optimized programs. Hash calculations are tagged during compilation and counted after optimization; other instructions include input Booleanity, parsing/traversal checks, public binding and the wrapper. This is an instruction breakdown, not a per-hash proof-time allocation. Separate [hash execution diagnostics](../analysis/hash-diagnostic-summary.csv) measure every actual input length using the same executable. Those times include input/output constraints and are not subtracted from complete proofs. **c,** Every measured proof's deviation from its own condition median, in block order. Colors identify anchors; dashed lines show baseline and solid lines show optimized programs. Conditions are interleaved within blocks, so the points in a block are not simultaneous measurements.

[PDF](figure-3-cost-breakdown.pdf) · [Editable SVG](figure-3-cost-breakdown.svg) · [PNG](figure-3-cost-breakdown.png)

## Source data and reproduction

The collection uses one Apple M5 Max with 128 GiB RAM, macOS 26.5, eleven Rayon workers, AC power and the same pinned native-target executable. Each condition has one fresh-process warmup, then eight measured fresh processes in randomized Williams order. Two attempts interrupted by power changes and one stopped at the user's request were retained and excluded as entire batches before the September 11 restart. Temperature and CPU frequency were not measured. The intervals describe the selected batch, not reproducibility across machines or independent batches.

- [All proof samples and phases, including labeled warmups](../analysis/source-data.csv)
- [Paired comparisons](../analysis/comparisons.csv)
- [Instruction counts for every hash call](../analysis/hash-instructions.csv)
- [All 200 standalone hash execution samples](../analysis/hash-diagnostic-samples.csv)
- [Hash diagnostic summaries](../analysis/hash-diagnostic-summary.csv)
- [Power, battery level and load at every proof endpoint](../analysis/environment.csv)
- [Machine-readable summary](../analysis/summary.json)
- [Raw evidence selection and hashes](../evidence.json)
- [Figure generator](../plot_figures.py)

```bash
python -m pip install -r real_state/figure-requirements.txt
python -m owner_state.plot_figures --run owner_state/results/collect-20260911T071527362410Z
python -m owner_state.plot_figures --run owner_state/results/collect-20260911T071527362410Z --check
```

Use the collection path from `evidence.json`. Verification recomputes SVGs deterministically from raw measurements; PDF and PNG encoders can vary between library/platform builds. See the [full report](../README.md) for the statement, validation and limits.
