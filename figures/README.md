# State Anchor Benchmark Figures

## TL;DR

These figures separate the intended private ownership mechanism from what the benchmark actually executes. They report deterministic structural counts from one pinned mainnet snapshot and repeated leanVM-b timings for synthetic serial BLAKE3 programs. The timings are not end to end private proof times.

## Figure 1

**Intended mechanism and measured scope.** Panel a shows a conceptual private spend in which a pool root authenticates a note and an Ethereum state root authenticates account storage for a hidden owner. Panel b shows two examples from the actual structural experiment: unrelated Tornado Cash and Safe mainnet proofs. Figure 2 reports all eight cases. The experiment runs the modeled hash counts as serial BLAKE3 programs in leanVM-b. It does not join the examples or implement note membership, a hidden owner, authorization, a nullifier, or outputs.

Files: [SVG](figure-1-private-owner-mechanism.svg) and [PNG](figure-1-private-owner-mechanism.png).

## Figure 2

**Structural cost of authenticated state claims.** Panel a isolates the public anchor overhead at mainnet block 25,939,968: zero modeled calls for hypothetical direct state root exposure, five for the draft EIP-7807 block root, and twenty for the available block hash and its 634 byte RLP header. Each value is added once to a row in panel b. Panel b reports the direct state root path for exact account, Safe, WETH, Tornado Cash, and BAYC fixtures. The Tornado application root shortcut is shown separately because it authenticates only that root, not arbitrary Ethereum state. Multi-claim rows hash identical encoded trie nodes once; this is a deduplication model, not an implemented multiproof. There are no error bars because these are deterministic counts for one snapshot.

Files: [SVG](figure-2-state-anchor-results.svg) and [PNG](figure-2-state-anchor-results.png).

## Figure 3

**Steady state leanVM-b calibration.** Panel a shows every measured proving time for all 24 serial BLAKE3 workloads, together with the median of six process medians and a 95 percent within-batch process bootstrap interval across those medians. Panels b to d show committed witness cells, serialized proof size, and warm verification time. Each point has 60 measured runs from six fresh processes on one machine. Each process used three warmups and one untimed tamper check per case before measurement. The proving timer includes VM execution and proof witness generation, but excludes setup and host-side input construction. These calibration programs do not execute RLP, MPT, SSZ, Ethereum Keccak or SHA-256, private logic, witness fetching, recursion, or gas accounting. An independent repeat is reported in [the independent repeat report](../reruns/2026-09-09-independent-repeat/README.md).

Files: [SVG](figure-3-leanvm-timing.svg) and [PNG](figure-3-leanvm-timing.png).

## Export

The editable SVG files are the publication masters. They are designed for full-width placement at 183 mm, not single-column reduction. At that width, ordinary text is 5.5 to 6.9 pt and panel labels are 8.1 pt. Figures 1 and 2 export to 3,600 by 2,200 pixels. Figure 3 exports to 3,600 by 2,800 pixels. The palette and marker shapes distinguish the three public anchors without relying on color alone. This follows [Nature's figure guidance](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/) on editable vector art, standard sans-serif fonts, RGB color, accessible marks, panel labels, axes, and 5 to 7 pt text. A journal production submission should convert the SVG masters to its requested PDF or EPS format, preserve editable text, and embed the selected Arial or Helvetica font.

Regenerate both formats with:

From the repository root:

```bash
python3 make_figures.py
python3 render_figures.py
```

## See also

- [Full benchmark report](../REPORT.md)
