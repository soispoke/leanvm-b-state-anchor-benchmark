# leanVM-b note-owner binding benchmark

How much does the state anchor cost when proving that a note belongs to an account? We open **`H = Keccak256(owner_addr || secret)`** and authenticate the **same address's account and storage word** inside leanVM-b, including all required hashes and encoding checks.

The comparison uses a direct state root, an RLP block hash and a hypothetical SSZ summary root. Signature verification and recursive authorization, item (ii), are outside scope. **Owner privacy is not established:** this pinned backend lacks a zero-knowledge layer.

![The note opening and authenticated account lookup use the same address](owner_state/figures/figure-1-owner-binding.png)

The fixture is a Safe account's slot 0 at mainnet block **25,939,968**. Its singleton address stands in for a stored verification key hash. The demonstration note secret is public. [Exact statement and limits](owner_state/README.md#exact-statement).

## Results

**Both block anchors add about 9% proving time over a direct state root; an SSZ advantage over RLP is unresolved.** With 80 measurements per anchor, the paired changes are +9.1% for RLP (95% within-batch interval +8.6 to +9.6%) and +8.8% for SSZ (+8.2 to +9.5%).

The table and figures show **all 240 measured runs of the optimized programs**, 80 per anchor, ten times the earlier sample count. The compiler cleanup is applied consistently across anchors; the [full compiler comparison](owner_state/README.md#what-was-optimized) remains available.

| Anchor | Median proving time | Paired change vs direct state (nominal 95% interval) |
| --- | ---: | ---: |
| Direct state root | 6.41 s | Reference |
| RLP block hash | 7.05 s | +9.1% [+8.6, +9.6] |
| SSZ summary* | 7.03 s | +8.8% [+8.2, +9.5] |

The September 15 collection contains **240 measured proofs across 80 randomized rounds**, plus three warmups, on an Apple M5 Max with eleven Rayon workers and AC power. All proofs verified, and all recorded environment checks passed. Observations span **6.13–7.96 s**, with visible early drift; the intervals describe paired differences within this batch, not general machine variability. The earlier eight-round batch remains separate. The paired ratios also change over the run: early and late quarters give different overheads. The narrow t intervals assume independent rounds, so their nominal coverage is not established by this batch.

Collection ran sequentially after three qualifying CPU-idle checks, with no concurrent local benchmark, build or figure work. The binary, generated programs and inputs match the September 11 setup byte for byte. [Expanded-batch record](owner_state/repeats/20260911-80-rounds/README.md).

Mean VM execution is **0.43–0.77 s** and witness construction **0.58–0.71 s**. The remaining **79–84%** of complete proving time is proof work and cleanup. Keccak and SHA account for **98.6–98.8% of guest instructions**, but their proof-construction costs cannot be separated by subtracting standalone hash timings.

*The SSZ summary is hypothetical and retains the same Keccak state tries. The secondary SSZ/RLP comparison is **−0.27% [−0.64%, +0.11%]**: this batch does not resolve a difference or establish equivalence.


![All 240 optimized-program proof times and paired comparisons between the three anchors](owner_state/figures/figure-2-proving-results.png)

The supporting figure explains proof costs and remaining timing drift.

![Proof costs and timing drift](owner_state/figures/figure-3-cost-breakdown.png)

For a short follow-up, attach Figure 2 alone, or Figures 1 and 2 together. The [figure gallery](owner_state/figures/README.md) contains full captions, editable SVGs, vector PDFs with embedded fonts, 600 dpi PNGs and source data. The [full report](owner_state/README.md) documents the relation, optimization, exact setup and statistical limits. [Privacy inspection](owner_state/PRIVACY.md) explains why witness inputs alone do not establish owner hiding.

## Verify and reproduce

```bash
git clone https://github.com/soispoke/leanvm-b-state-anchor-benchmark.git
cd leanvm-b-state-anchor-benchmark
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m owner_state.verify_artifacts
python -m unittest discover -s owner_state -p 'test_*.py' -v
```

With Rust installed, follow the [reproduction commands](owner_state/README.md#validation-and-reproduction) to regenerate all six programs, verify saved proofs without witness files, or collect a new batch. The implementation pins [leanVM-b `8494c5d`](https://github.com/leanEthereum/leanVM-b/tree/8494c5d5df323f2b97ed89272942a4bee6247078), exposes its existing witness API, and adds exclusive timing clocks. The VM's ISA and proof constraints remain unchanged.

## Earlier experiments

The earlier [real state-lookup experiment](real_state/README.md) and its [figures](real_state/figures/README.md) remain preserved. They omit the note opening and contain three exploratory battery-powered runs per anchor. They must not be pooled with the new owner-binding measurements.

The original synthetic BLAKE3 calibration and its independent repeat remain separate background evidence about padding: [report](REPORT.md), [repeat](reruns/2026-09-09-independent-repeat/README.md), [comparison](reruns/2026-09-09-independent-repeat/comparison.csv) and [figures](figures/README.md). Run `python verify_evidence.py` to check all 2,880 calibration samples. [PROVENANCE.md](PROVENANCE.md) distinguishes every experiment and preserved attempt.
