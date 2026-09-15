# Note-owner binding through three state anchors

This experiment opens `H = Keccak256(owner_addr || secret)` and authenticates the **same address's account and storage word** inside leanVM-b. It compares a direct state root, an RLP block hash and a hypothetical SSZ summary root. The selected compiler optimization preserves the relation and all hash algorithms.

**Binding is implemented; owner privacy is not established.** The pinned backend lacks a zero-knowledge layer. Signature verification, leanSPHINCS and recursive authorization, item (ii), remain outside this experiment. See the [privacy inspection](PRIVACY.md).

![Owner commitment opening connected to the same account lookup](figures/figure-1-owner-binding.png)

## Results

The complete measurement table and figures are generated from the collection selected in [evidence.json](evidence.json). The original [state-lookup measurements](../real_state/README.md) remain preserved as an earlier, different relation.

**Both block anchors add about 9% proving time over a direct state root; the SSZ/RLP difference remains unresolved.** The table and figures use all 240 optimized-program measurements, 80 per anchor. The earlier paired compiler comparison is retained under [What was optimized](#what-was-optimized).

| Anchor | Median proving time | Paired change vs direct state (nominal 95% interval) |
| --- | ---: | ---: |
| Direct state root | 6.41 s | Reference |
| RLP block hash | 7.05 s | +9.1% [+8.6, +9.6] |
| SSZ summary* | 7.03 s | +8.8% [+8.2, +9.5] |

The September 15 collection contains **240 measured proofs across 80 randomized rounds**, plus three warmups, on an Apple M5 Max with eleven Rayon workers and AC power. All proofs verified, and all recorded environment checks passed. Observations span **6.13–7.96 s**, with visible early drift; the intervals describe paired differences within this batch, not general machine variability. The earlier eight-round batch remains separate. The paired ratios also change over the run: early and late quarters give different overheads. The narrow t intervals assume independent rounds, so their nominal coverage is not established by this batch.

Mean VM execution is **0.43–0.77 s** and witness construction **0.58–0.71 s**. The remaining **79–84%** of complete proving time is proof work and cleanup. Keccak and SHA account for **98.6–98.8% of guest instructions**, but their proof-construction costs cannot be separated by subtracting standalone hash timings.

*The SSZ summary is hypothetical and retains the same Keccak state tries. The secondary SSZ/RLP comparison is **−0.27% [−0.64%, +0.11%]**: this batch does not resolve a difference or establish equivalence.


### Optimized phase costs

Arithmetic means in seconds; the unrounded phases add to the complete prove call.

| Anchor | Execution | Witness build | Remaining prove work and cleanup | Complete prove call |
| --- | ---: | ---: | ---: | ---: |
| Direct state root | 0.427 | 0.584 | 5.463 | 6.475 |
| RLP block hash | 0.774 | 0.707 | 5.580 | 7.061 |
| SSZ summary* | 0.773 | 0.705 | 5.563 | 7.042 |

### Proof size and process memory

Verification medians below are measured immediately after proving. Independent witness-free verification is recorded separately. Peak footprint covers the complete process, including loading and checks.

| Anchor | Proof bytes | Median verification | Maximum peak footprint |
| --- | ---: | ---: | ---: |
| Direct state root | 834,752 | 152.1 ms | 38.78 GiB |
| RLP block hash | 835,712 | 299.5 ms | 41.22 GiB |
| SSZ summary* | 836,384 | 299.3 ms | 41.27 GiB |

All 243 proofs passed their public-input and serialized-proof tamper checks. Three saved proofs, one per anchor, also verified in fresh processes containing no witness files. All 52 precollection tests passed after regeneration. The 85 altered-witness checks from September 11 are reused against byte-identical programs. [Raw evidence and source hashes](evidence.json) preserve these checks.

![All 240 optimized-program proof times and paired anchor comparisons](figures/figure-2-proving-results.png)

![Supporting figure: proof costs and observed timing drift](figures/figure-3-cost-breakdown.png)

## Exact statement

The public inputs are the anchor type, anchor root or block hash, note commitment `H`, and storage slot. The VM binds their fixed-width encoding through two public field elements containing:

```text
Keccak256("LVMOWNER1" || mode:u8 || anchor:32 || H:32 || slot:32)
H = Keccak256(owner_addr:20 || secret:32)
```

The witness supplies the address, secret, account proof, storage proof and stored word, plus a header or SSZ branch where needed. The same address wires feed both the note hash and the secure account-trie key. The authenticated account's `storageRoot` anchors the storage lookup. The slot wires feed both the secure storage key and public statement, and the decoded stored value must equal the supplied witness word. No host-provided hash digest is trusted.

The account is Safe `0xb235f9b71000a39c25476f7ba40aaa3763287685`, slot `0`, at Ethereum mainnet block **25,939,968**. Its singleton address is a stand-in for a stored verification key hash; this experiment does not claim it is a real verification key. The demonstration secret is the public byte sequence `00, 01, …, 1f`, and the note commitment is `0x644730db4e62e76585160679508e0fec9df6a75a4e1fe9ce9c9d014b03310fe5`. These are benchmark fixtures, not private user data.

All canonical RLP checks, secure trie key hashing, account and storage traversal, header hashing or SSZ branch verification, commitment opening and public-input hashing execute as constrained VM instructions. The relation retains the original **fixed public encoding shape**, including node lengths and RLP layouts. It is not a general variable-length Ethereum state verifier. The SSZ branch contains the real state root, but its summary is hypothetical; both state tries remain Keccak MPTs. See the [original profile and fixture derivation](../real_state/README.md).

## What was optimized

**Hash optimization removes 1.08–1.22% of instructions, but a proving-speed improvement was not established in the September 11 compiler comparison.** The table below belongs to that earlier eight-round batch; it is not pooled with the new 80-round anchor comparison. Every optimization interval includes no change. Positive timing changes mean slower. [Earlier analysis](repeats/20260911-full-restart/analysis/summary.json).

| Anchor | Baseline median | Optimized median | Paired time change (95% interval) |
| --- | ---: | ---: | ---: |
| Direct state root | 6.54 s | 6.51 s | -0.7% [-3.1, +1.8] |
| RLP block hash | 7.40 s | 7.31 s | -1.5% [-4.1, +1.1] |
| SSZ summary* | 7.19 s | 7.19 s | -0.4% [-3.0, +2.3] |

The baseline and optimized conditions prove identical public statements. Common-subexpression elimination reuses identical operations within each hash. Dead-code elimination removes unused calculations, mainly unneeded outputs of Keccak's last permutation. Every write to an initialized cell remains a constraint root, preserving Booleanity, equality checks, conflicting-write rejection and public-input binding. Compilation decisions depend on public shape and wire identities, not witness values.

This removes **1.08–1.22% of whole-program instructions**. No baseline/optimized pair crosses a padded table boundary. Other candidates, including two SHA carry formulas, are recorded in the [screening report](screening/README.md). A reduction in multiplications alone is not a demonstrated speedup when it increases XOR work or leaves the same padded proof tables.

Adding the note commitment also changes the comparison with the earlier state-only relation: the RLP and SSZ programs now cross the `2^23` memory and bytecode domain boundary, while direct state remains below it. Their committed witness size is **207,621,052 field cells**, versus **182,455,228** for direct state. This is a property of this fixture, relation and backend padding. It is not a universal cost ratio between anchors.

## Measurements and interpretation

The [expanded experiment contract](CONTRACT.md#september-11-expansion-80-rounds-of-the-selected-programs) fixed the 80-round design before collection. Each of three optimized anchor programs has one fresh-process warmup and 80 measured fresh processes. Seed `20260911` fixes randomized Williams order with forward and reverse rows: thirteen complete six-round cycles and two additional rows. Every measurement is retained. The native executable, programs, public inputs, witness files and metadata match the earlier collection byte for byte. Earlier batches are preserved and are not pooled into these estimates.

The machine is an Apple M5 Max with 128 GiB RAM, running macOS 26.5, Rust 1.97.1, eleven Rayon workers and recorded AC power. The pinned upstream Cargo configuration builds with `-C target-cpu=native`; [build.json](build.json) records the executable, dependency lock, patches and build fingerprint. The collector records power source/settings, load, hardware, toolchain and thermal-warning status before and after every proof. CPU temperature and frequency are **not measured**, and stable settings do not imply constant environmental conditions.

Two initial batches stopped when power changed from AC to battery, during measured proofs 1 and 16 respectively. A third batch was stopped at the user's request after 20 completed measured proofs. All three attempts remain preserved, including completed proofs and warmups. None enters the selected timing estimates. The first complete September 11 batch is also retained as earlier evidence. At the user's request, the entire suite then restarted: setup, generation, native tests, malformed-witness checks, hash diagnostics, all proof warmups/measurements and witness-free verification. The restart uses the same executable and predeclared schedule.

The [September 15 attempt](repeats/20260911-80-rounds/attempt-20260915T093856598597Z/experiment.json) records sequential collection with no concurrent local builds, diagnostics or figure generation. Its last three preflight snapshots were 90.6%, 92.0% and 92.2% CPU idle on AC, spaced by 20 seconds plus probe time. Collection took about 34 minutes. This controls our workload, not every macOS background process or thermal state. Round mean proving times range from 6.53 to 7.69 seconds, with visible early drift. Exact equal load is not claimed, and no early observations were discarded.

The primary timer covers the complete `prove()` call, including VM execution, witness-table construction, proof construction and return cleanup. Program loading/assembly and verification are timed separately. Witness loading and serialization are outside the prove timer and have no separate timers. The [profiling patch](profile.patch) adds exclusive phase clocks and prints once after internal timing ends. Its work and transcript operations otherwise retain their original order. Phase stacks use arithmetic means so they sum to the mean outer time; absolute headline times use medians.

Each optimization or anchor/direct comparison pairs observations by block. The SSZ/RLP comparisons remain secondary: they were introduced after the earlier batch and retained before this restart, using the same pairing and interval method. The new anchor ratios are geometric means of 80 within-round time ratios, with 95% Student-t intervals on their logarithms and 79 degrees of freedom. The historical compiler comparisons retain eight pairs and seven degrees of freedom. These **within-batch, exploratory, unadjusted** intervals assume approximately independent, normally distributed block log ratios. They do not estimate variability across machines or independent batches, and an interval spanning no change does not establish equivalence. A post-collection [run-order diagnostic](analysis/run-order-diagnostics.csv) finds lag-one correlations of 0.44 for RLP/direct and 0.34 for SSZ/direct. Their first-20 versus last-20 geometric mean overheads are 6.75% versus 10.21%, and 6.23% versus 10.33%, respectively. This descriptive check questions the independence assumption; the original intervals remain reported as nominal, without replacing the analysis or discarding observations. The SSZ/RLP first and last quarter changes are −0.49% and +0.11%. More measurements make the batch better described, but do not by themselves establish its interval coverage.

Hashing is attributed by exact retained instruction counts, with [200 standalone execution diagnostics](diagnostics/20260911-full-restart/report.json) covering every actual hash input length, both selected implementations and the hybrid SHA candidate. Those September 11 diagnostics are reused, not remeasured. They use the same native executable as the selected proof batch, but record environment at batch endpoints rather than per sample. They include witness Booleanity and public-output binding. They are not additive proving costs and are never subtracted from complete proofs: shared tables, padding and polynomial commitments make such subtraction invalid. The earlier non-native diagnostic batch is retained separately.

## Validation and reproduction

Install [requirements-lock.txt](../requirements-lock.txt) in a Python virtual environment. The evidence checker validates hashes, raw logs, phase accounting, the collection schedule, environmental records, saved verification reports, and deterministic analysis outputs. Derived numeric exports use twelve significant digits to avoid platform-specific last-bit differences; raw logs retain their recorded precision:

```bash
python -m owner_state.verify_artifacts
python -m unittest discover -s owner_state -p 'test_*.py' -v
```

The recorded Rust installation must include `rustfmt` for the patch syntax check (with rustup: `rustup component add rustfmt --toolchain 1.97.1`). With that version installed, regenerate the programs and cryptographically verify the three saved proofs in fresh directories containing only the program, public input and proof:

```bash
python -m owner_state.run setup
python -m owner_state.run generate --variants baseline cse_dce
python -m owner_state.verify_artifacts --generated
python -m owner_state.run verify --run owner_state/results/collect-20260915T094023087152Z
```

`evidence.json` supplies the selected collection path. Setup uses a separate `vendor/leanVM-b-profiled` checkout and leaves the original baseline checkout intact. Generated binaries and programs stay in ignored local directories. The preserved proofs are under the selected collection's `proofs/` directory.

To repeat the 80-round anchor comparison on macOS with ample memory and AC power, first regenerate and validate the programs as above, then use the orchestrator. It enforces the original binary/input identities and quiet-load preflight:

```bash
python owner_state/repeats/20260911-80-rounds/orchestrate.py
python -m owner_state.analyze --run owner_state/results/YOUR_COLLECTION --output local-runs/new-analysis
python -m pip install -r real_state/figure-requirements.txt
python -m owner_state.plot_figures --run owner_state/results/YOUR_COLLECTION --output local-runs/new-figures
```

The collector rejects failed processes, missing memory metrics, inconsistent provenance, invalid proofs, and power-source or power-settings changes. Permission to read macOS resource counters is required for `/usr/bin/time -l`. Report directories are unique and retained on failure. The 85 malformed-witness checks exercise VM rejection after compilation, not a forged-proof attack; each successful proving process separately checks that an altered public input and mutated serialized proof fail verification.
