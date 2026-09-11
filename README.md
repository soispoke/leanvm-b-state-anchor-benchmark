# leanVM-b note-owner binding benchmark

How much does the state anchor cost when proving that a note belongs to an account? We open **`H = Keccak256(owner_addr || secret)`** and authenticate the **same address's account and storage word** inside leanVM-b, including all required hashes and encoding checks.

The comparison uses a direct state root, an RLP block hash and a hypothetical SSZ summary root. Signature verification and recursive authorization, item (ii), are outside scope. **Owner privacy is not established:** this pinned backend lacks a zero-knowledge layer.

![The note opening and authenticated account lookup use the same address](owner_state/figures/figure-1-owner-binding.png)

The fixture is a Safe account's slot 0 at mainnet block **25,939,968**. Its singleton address stands in for a stored verification key hash. The demonstration note secret is public. [Exact statement and limits](owner_state/README.md#exact-statement).

## Results

**Both block anchors add about 10% proving time over a direct state root; an SSZ advantage over RLP is unresolved.** With the optimized compiler, the paired changes are +10.4% for RLP (95% within-batch interval +6.6 to +14.4%) and +10.3% for SSZ (+7.0 to +13.7%).

The table and figures show **all 24 measured runs of the optimized programs**, eight per anchor. The compiler cleanup is applied consistently across anchors; the [full compiler comparison](owner_state/README.md#what-was-optimized) remains available.

| Anchor | Median proving time | Paired change vs direct state (95% interval) |
| --- | ---: | ---: |
| Direct state root | 6.51 s | Reference |
| RLP block hash | 7.31 s | +10.4% [+6.6, +14.4] |
| SSZ summary* | 7.19 s | +10.3% [+7.0, +13.7] |

The complete September 11 restart contains **48 measured proofs across eight randomized blocks**, plus six warmups, on an Apple M5 Max with eleven Rayon workers and AC power. All proofs verified. Observations span **6.32–8.29 s**, with residual drift during the batch; the intervals describe paired differences within this batch, not general machine variability.

All stages ran sequentially, after CPU-idle checks and with no concurrent local benchmark work. [Restart record](owner_state/repeats/20260911-full-restart/README.md).

For optimized programs, mean VM execution is **0.44–0.79 s** and witness construction **0.64–0.78 s**. The remaining **79–84%** of complete proving time is proof work and cleanup. Keccak and SHA account for **98.6–98.8% of guest instructions**, but their proof-construction costs cannot be separated by subtracting standalone hash timings.

*The SSZ summary is hypothetical and retains the same Keccak state tries. A secondary paired SSZ/RLP comparison also does not establish an SSZ timing advantage.


![All 24 optimized-program proof times and paired comparisons between the three anchors](owner_state/figures/figure-2-proving-results.png)

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
