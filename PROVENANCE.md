# Evidence provenance

The original experiment and its independent repeat were collected on September 9, 2026. This standalone repository was prepared on September 10, 2026.

`evidence-sha256.txt` records the byte-for-byte export of 28 original files: all Rust programs, the fixture, measurements and validation transcripts, CSVs, SVG/PNG figures, Python fixture and timing sources, the figure generator, and the direct dependency pins. In particular, the timing program, runner, and analyzer still match the SHA-256 values recorded in both timing transcripts. These hashes establish file integrity, not an independent attestation of the experiment.

The reports were adapted for GitHub: vault frontmatter and internal links were removed, the main report became `REPORT.md`, and reproduction commands now use repository-relative paths. Historical transcripts retain their original command paths and temporary build directory names. Those paths are context, not installation requirements.

The export changes two support tools. `check_artifacts.py` now compares regenerated content in a temporary directory, rejects stale CSV or SVG data, and ignores modification times. `render_figures.py` accepts an ordinary Node/Sharp installation or browser instead of depending on an application-bundled runtime. Neither tool is one of the three sources hashed in the timing transcripts.

`verify_evidence.py`, the SHA-256 manifest, the complete Python dependency lock, and CI were added for this export. Verification recomputes the two timing summaries and the comparison, checks that all paired deterministic sample fields match, and regenerates all four SVGs. It reads the recorded proof success and tamper checks; it does not replace a live proof rerun or a cryptographic audit of leanVM-b.

The preserved timing collector uses macOS hardware and power commands and does not capture temperature, frequency, system load, or power mode. All confidence intervals remain labeled as within-batch intervals. No claim of exact environmental equivalence has been added.

The September 10 real account-and-storage experiment lives separately under `real_state/`. Its actual Keccak/RLP/MPT/SHA-256 VM programs, three serialized proofs, nine proving logs, environment records, and adversarial checks do not replace the original calibration. `real_state/evidence-sha256.txt` covers the new experiment, and `real_state/programs.json` records the large generated programs' hashes so the bytecode need not be stored in Git. The new measurements were taken on battery power and are not a third batch of the AC-powered BLAKE3 calibration.

The first separate verification succeeded in Rust but the Python collector failed to recognize a result printed after libtest's progress prefix. Both that attempt and the successful three-path repeat are preserved. `real_state/results/measurement-run.py.txt` preserves the collector before this output-parsing fix; the guest, VM patch, Rust runner, compiled binary, and saved proofs did not change. `verify_artifacts.py` checks the recorded source identities against the appropriate collector version.
