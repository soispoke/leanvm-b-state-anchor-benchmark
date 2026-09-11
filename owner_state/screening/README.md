# Screening and rejected shortcuts

The selected compiler candidate applies per-hash common-subexpression elimination and removes dead calculations while retaining every constraint side effect. It uses the original SHA adder. For the complete owner-binding relation it removes 92,597 instructions in direct mode, 98,102 in RLP mode and 92,828 in SSZ mode (1.22%, 1.15%, 1.08%). These reductions do not change the padded domains within any baseline/candidate pair.

The direct DCE-only ablation has 7,505,960 VM instructions, compared with 7,498,510 for CSE plus DCE and 7,591,107 for baseline. The principal elimination is unused outputs from Keccak's last permutation, where only 256 of 1,600 output bits feed the digest. Intermediate permutation states in a multi-block hash remain live. All RLP, trie, equality, Booleanity and public-input checks remain roots of the retained computation.

The alternatives below are preserved in source or described here rather than silently presented as wins:

- Packing Boolean wires into 128-bit words is not free. Independent Boolean inputs require packing/binding constraints, and field multiplication is not packed bitwise AND. Keccak's existing rotations are free wire permutations. No packed implementation or speedup is claimed.
- Keccak's standard lane-complement technique trades NOTs for ORs. OR itself takes multiple instructions on this ISA, cancelling the obvious gate saving. It was not selected.
- A one-MUL full-adder carry reduces multiplications but loses constant-folding opportunities. For a 64-byte SHA input, hash logic alone grows from 196,576 to 202,312 gates before compiler optimization. Including input Booleanity and the two initial SETs gives 197,090 to 202,826, before public-output binding.
- A hybrid adder preserves the baseline gate count by retaining the old formula for public constant inputs. However, it increases the padded XOR table for an isolated 64-byte SHA circuit. Both arithmetic tables have the same number of committed columns. Whole SSZ owner programs retain identical padding under the two adders, so fewer MULs alone is not a sufficient reason to select it.

The separate [hash diagnostics](../diagnostics/) record all actual hash input lengths and baseline/candidate execution samples. They include input Booleanity and public-output binding; their elapsed times are not subtracted from full proofs or treated as additive proving costs. They are exploratory execution diagnostics, without the full per-run environmental records of the primary collection.

`cse-dce-direct-proof.txt` records a successful optimized owner-binding proof, its tamper rejections and phase timings. The outer `/usr/bin/time -l` failed afterward because the sandbox denied `sysctl kern.clockrate`; the command therefore exited nonzero and the memory report is incomplete. This is a preserved validation smoke run, not a primary timing sample. The primary collector requires a successful process and complete memory data and runs with the required host read permissions.
