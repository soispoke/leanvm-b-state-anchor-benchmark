# Evidence provenance

The original experiment and its independent repeat were collected on September 9, 2026. This standalone repository was prepared on September 10, 2026.

`evidence-sha256.txt` records the byte-for-byte export of 28 original files: all Rust programs, the fixture, measurements and validation transcripts, CSVs, SVG/PNG figures, Python fixture and timing sources, the figure generator, and the direct dependency pins. In particular, the timing program, runner, and analyzer still match the SHA-256 values recorded in both timing transcripts. These hashes establish file integrity, not an independent attestation of the experiment.

The reports were adapted for GitHub: vault frontmatter and internal links were removed, the main report became `REPORT.md`, and reproduction commands now use repository-relative paths. Historical transcripts retain their original command paths and temporary build directory names. Those paths are context, not installation requirements.

The export changes two support tools. `check_artifacts.py` now compares regenerated content in a temporary directory, rejects stale CSV or SVG data, and ignores modification times. `render_figures.py` accepts an ordinary Node/Sharp installation or browser instead of depending on an application-bundled runtime. Neither tool is one of the three sources hashed in the timing transcripts.

`verify_evidence.py`, the SHA-256 manifest, the complete Python dependency lock, and CI were added for this export. Verification recomputes the two timing summaries and the comparison, checks that all paired deterministic sample fields match, and regenerates all four SVGs. It reads the recorded proof success and tamper checks; it does not replace a live proof rerun or a cryptographic audit of leanVM-b.

The preserved timing collector uses macOS hardware and power commands and does not capture temperature, frequency, system load, or power mode. All confidence intervals remain labeled as within-batch intervals. No claim of exact environmental equivalence has been added.

The September 10 real account-and-storage experiment lives separately under `real_state/`. Its actual Keccak/RLP/MPT/SHA-256 VM programs, three serialized proofs, nine proving logs, environment records, and adversarial checks do not replace the original calibration. `real_state/evidence-sha256.txt` covers the new experiment, and `real_state/programs.json` records the large generated programs' hashes so the bytecode need not be stored in Git. The new measurements were taken on battery power and are not a third batch of the AC-powered BLAKE3 calibration.

The first separate verification succeeded in Rust but the Python collector failed to recognize a result printed after libtest's progress prefix. Both that attempt and the successful three-path repeat are preserved. `real_state/results/measurement-run.py.txt` preserves the collector before this output-parsing fix; the guest, VM patch, Rust runner, compiled binary, and saved proofs did not change. `verify_artifacts.py` checks the recorded source identities against the appropriate collector version.

## Owner-state figure focus

The September 10 presentation update focuses the report on the authenticated account-and-storage lookup needed for note-owner binding. Figure 1 marks note-commitment opening as context. Figure 2 isolates net anchor instruction overhead, padded commitment size and all nine proving samples. Supplementary Figure S1 retains verification, size and memory measurements. The root README links the earlier calibration as background. Only documentation and figure-generation artifacts changed; the measured programs, saved proofs, raw logs and source-data CSV are unchanged.

## Complete note opening and profiled measurements

The later September 10 implementation under `owner_state/` connects the same address to `H = Keccak256(owner_addr || secret)` and the authenticated account/storage lookup. It adds compiler optimization and an opt-in timing patch in a separate pinned VM checkout. The patch preserves the prover's work and transcript calls, adding exclusive clocks and one output record. The witness and ISA patches remain unchanged. This is a different relation from `real_state/`, whose programs and evidence remain preserved.

`owner_state/CONTRACT.md` records the comparison and analysis choices before measurement. `owner_state/build.json` records the native-target executable and Cargo fingerprint; `owner_state/build/` preserves its build output. Each collection snapshots the exact source files, program metadata, public inputs and hashes. Large generated programs remain reproducible in ignored local directories. The evidence manifest selects the completed collection, separate witness-free verification, negative checks, and hash diagnostics, and hashes the published artifacts. These hashes are integrity checks, not independent attestation.

Two collection attempts were interrupted by AC-to-battery transitions, during measured proofs 1 and 16. A third stopped at the user's request after 20 completed measured proofs. Their records remain under `owner_state/results/`; none supplies the selected estimates. Collection restarted on September 11. The initial smoke proof also succeeded cryptographically but its `/usr/bin/time -l` wrapper failed on a sandboxed resource query, so it is excluded. The first standalone hash diagnostics used a non-native build; later diagnostics use the same native executable as the primary comparison. Each set is retained and distinguished explicitly.

Public statements omit the address and secret, but the pinned backend has no demonstrated zero-knowledge layer. The benchmark publishes its synthetic note secret. The owner-binding result and its timings must not be described as a completed private transaction proof or as a measurement of owner privacy.

The fresh Linux evidence check exposed last-bit differences in regenerated floating-point comparisons. Derived CSV/JSON exports now use twelve significant digits, with a regression check for adjacent floating-point values. Raw measurements, statistical calculations and figure geometry are unchanged.

At the user's request, the entire owner-binding suite ran again sequentially on September 11, from setup and generation through all checks and measurements. `owner_state/repeats/20260911-full-restart/` preserves the orchestration, logs and CPU-idle preflights. Collection `collect-20260911T074413358669Z` is now selected; the earlier complete collection remains intact and is not pooled into the new estimates. The executable hash is unchanged. Each timing stage began after three snapshots above 90% CPU idle, but background activity and thermal equilibrium are not guaranteed. Figures retain all 48 new measured proofs and their remaining drift.
