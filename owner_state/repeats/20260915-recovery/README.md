# September 15 workspace recovery

The temporary checkout had disappeared. The repository was restored in a persistent workspace from the local checkpoint and the public GitHub snapshot at `41cff79c4417c08c16afe10b36edaa1cf46f51e3`. Its complete Git tree and commit hashes match GitHub. The pinned VM rebuilt offline to the previous executable SHA-256, `3d776efa8485482340b24bf72a9f9de7daabbec2fec3e55d318b2296a141db2a`.

All 33 measurement, analysis and profiling tests passed. Existing evidence hashes and derived analyses validate. These checks do not replace program regeneration, the remaining hash/relation tests or fresh proof verification. See [recovery.json](recovery.json) and the accompanying check transcripts.

The exact 22 Python dependency pins were subsequently installed and checked. Both compiler variants were regenerated, all six program/input/metadata bundles matched the previous collection byte for byte, and all 52 tests passed. [Dependency record](dependency-restoration.json), [generated-input validation](generated-validation.txt), [test transcript](full-tests.txt) and [ready record](ready.json) preserve those gates. The initial `recovery.json` remains an unchanged record of the earlier dependency blocker.

The [fresh 80-round attempt](../20260911-80-rounds/attempt-20260915T093856598597Z/experiment.json) then passed the original quiet-AC preflight and completed all 240 measured proofs, three warmups and three witness-free saved-proof verifications. The new figures use that batch alone. Earlier measurements remain preserved separately.
