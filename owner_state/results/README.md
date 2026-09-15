# Raw evidence

These four records support the published owner-binding comparison. Their source snapshots and logs retain the exact measured bytes.

| Directory | Role |
| --- | --- |
| [collect-20260915T094023087152Z](collect-20260915T094023087152Z/) | 240 measured proofs, three warmups, environment records and three saved proofs |
| [generate-20260915T093651868962Z](generate-20260915T093651868962Z/) | Generated input identities and metadata; includes the reference implementation used in validation |
| [negative-20260911T073927482435Z](negative-20260911T073927482435Z/) | 85 malformed-witness rejection checks with the same measured programs |
| [verify-20260915T101414770576Z](verify-20260915T101414770576Z/) | Independent verification of the three saved proofs without witness files |

Each directory contains `report.json`, recorded source files and any process logs or proof artifacts. The [manifest](../evidence.json) checks their hashes and relationships. The [collection record](../collection/README.md) preserves the predeclared plan and preflight; [provenance](../../PROVENANCE.md) explains reused diagnostic evidence.

New collection commands create unique directories here. Only complete, validated batches should be selected for a new analysis; they must not silently replace or pool into the published batch.
