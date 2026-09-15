# Shared state-proof implementation

These modules supply the parsing, hashes, trie checks and native runner used by the [owner-binding benchmark](../owner_state/README.md).

| File | Purpose |
| --- | --- |
| [circuit.py](circuit.py), [hashes.py](hashes.py) | VM circuit operations and reference Keccak/SHA implementations |
| [statement.py](statement.py) | Fixed-profile RLP, account/storage and anchor checks |
| [profile.json](profile.json) | Public encoding shape of the mainnet fixture |
| [ssz_reference.py](ssz_reference.py), [ssz-reference.json](ssz-reference.json) | Independent SSZ reference and test vector |
| [real_state_bench.rs](real_state_bench.rs) | Native execution, proving, verification and rejection checks |
| [leanvm-witness-api.patch](leanvm-witness-api.patch) | Exposes the pinned backend's existing witness API |
| [run.py](run.py) | Reference runner setup, log parsing and mutation targets |
| `test_*.py` | Hash, encoding, inclusion and reference tests |

The measured guest entry point is [owner_state/relation.py](../owner_state/relation.py). Its collector and profiled backend setup are documented in [reproduction](../REPRODUCING.md).
