# Evidence provenance

The original experiment and its independent repeat were collected on September 9, 2026. This standalone repository was prepared on September 10, 2026.

`evidence-sha256.txt` records the byte-for-byte export of 28 original files: all Rust programs, the fixture, measurements and validation transcripts, CSVs, SVG/PNG figures, Python fixture and timing sources, the figure generator, and the direct dependency pins. In particular, the timing program, runner, and analyzer still match the SHA-256 values recorded in both timing transcripts. These hashes establish file integrity, not an independent attestation of the experiment.

The reports were adapted for GitHub: vault frontmatter and internal links were removed, the main report became `REPORT.md`, and reproduction commands now use repository-relative paths. Historical transcripts retain their original command paths and temporary build directory names. Those paths are context, not installation requirements.

The export changes two support tools. `check_artifacts.py` now compares regenerated content in a temporary directory, rejects stale CSV or SVG data, and ignores modification times. `render_figures.py` accepts an ordinary Node/Sharp installation or browser instead of depending on an application-bundled runtime. Neither tool is one of the three sources hashed in the timing transcripts.

`verify_evidence.py`, the SHA-256 manifest, the complete Python dependency lock, and CI were added for this export. Verification recomputes the two timing summaries and the comparison, checks that all paired deterministic sample fields match, and regenerates all four SVGs. It reads the recorded proof success and tamper checks; it does not replace a live proof rerun or a cryptographic audit of leanVM-b.

The preserved timing collector uses macOS hardware and power commands and does not capture temperature, frequency, system load, or power mode. All confidence intervals remain labeled as within-batch intervals. No claim of exact environmental equivalence has been added.
