# leanVM-b state anchor benchmark

How much does the choice of anchor add to the state proof needed for **note-owner binding**? We prove one real account-and-storage claim through a direct state root, an RLP block hash and a hypothetical SSZ summary root, with every required hash and encoding check enforced inside leanVM-b.

The motivating note commits `H = hash(owner_addr, secret)`. Its owner binding must use the same address to open the commitment and authenticate the account's stored key. This benchmark measures the **state lookup**. The commitment opening is context, and owner hiding has not been demonstrated. Signature or recursive authorization is outside the selected scope.

![State lookup for owner binding: context, measured scope, and three anchor paths](real_state/figures/figure-1-proof-paths.png)

**Figure 1. The measured component of owner binding.** All paths authenticate the same account and storage word. The real fixture is a Safe account's slot 0 at mainnet block **25,939,968**; its singleton address stands in for a verification key hash. [Full caption and exports](real_state/figures/README.md#figure-1--state-lookup-for-owner-binding).

## Results

**The block anchors add about 13% more instructions, with identical padded commitment size.** Every proving-time observation appears below. Their variation does not establish a reliable timing ranking.

![Additional anchor work, identical padded commitment sizes, and all nine proving measurements](real_state/figures/figure-2-measured-results.png)

| Anchor | VM instructions | Added versus direct | Median proving time |
| --- | ---: | ---: | ---: |
| Direct state root | 7,401,439 | Baseline | 19.414 s |
| RLP block hash | 8,370,523 | 969,084 (+13.09%) | 19.964 s |
| Hypothetical SSZ summary | 8,385,857 | 984,418 (+13.30%) | 22.247 s |

All three programs commit **182,455,228 witness cells**. They share the account and storage trie work; only the anchor path changes. The roughly 20-second medians reflect this unoptimized Boolean hash implementation, not an intrinsic cost of owner binding. Runs used an Apple M5 Max, eleven Rayon workers and battery power, with three fresh processes per condition.

All nine proofs verified. Three saved proofs also verified in separate processes without witness files, and all 76 altered-witness cases failed inside the VM. The relation uses a **fixed public encoding shape**. The SSZ summary contains the real state root, but is not a historical mainnet SSZ block.

The [figure gallery](real_state/figures/README.md) includes full captions, editable SVGs, vector PDFs, 600 dpi PNGs and source data. [Supplementary Figure S1](real_state/figures/README.md#supplementary-figure-s1--verification-size-and-memory) retains verification time, proof size and memory. Read the [report](real_state/README.md) for the exact statement, timing ranges, implementation and reproduction details.

## Verify locally

```bash
git clone https://github.com/soispoke/leanvm-b-state-anchor-benchmark.git
cd leanvm-b-state-anchor-benchmark
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m real_state.verify_artifacts
python -m unittest discover -s real_state -p 'test_*.py' -v
```

The commands above check the evidence and native tests. With Rust installed, regenerate the programs and verify the saved proofs cryptographically:

```bash
python -m real_state.run setup
python -m real_state.run generate
python -m real_state.verify_artifacts --generated
RAYON_NUM_THREADS=11 python -m real_state.run verify --saved-proof real_state/proofs
```

The implementation uses [leanVM-b commit `8494c5d`](https://github.com/leanEthereum/leanVM-b/tree/8494c5d5df323f2b97ed89272942a4bee6247078) with a small patch exposing its existing witness input API. Its ISA and proof constraints are unchanged. See the [reproduction details](real_state/README.md#reproduce) to generate new proofs. Live proving used up to about 39 GiB of peak memory footprint; CI regenerates the programs and verifies the saved proofs without running these large proving jobs.

## Earlier BLAKE3 calibration

The original synthetic calibration and independent repeat remain preserved as background. They measure serial BLAKE3 chains and do not supply the state-lookup timings above.

Read the [calibration report](REPORT.md), [independent repeat](reruns/2026-09-09-independent-repeat/README.md), [comparison CSV](reruns/2026-09-09-independent-repeat/comparison.csv) and [original figure gallery](figures/README.md). Run `python verify_evidence.py` to check all 2,880 calibration samples and preserved artifacts. [REPRODUCING.md](REPRODUCING.md) and [PROVENANCE.md](PROVENANCE.md) document reproduction and evidence preservation.
