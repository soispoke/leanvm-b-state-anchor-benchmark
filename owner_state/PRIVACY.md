# Owner binding and privacy

**This experiment tests owner binding, not owner privacy.** The relation opens `H = Keccak256(owner_addr || secret)` and uses that same address for the authenticated account/storage lookup. Address, secret and stored value are witness inputs rather than public statement fields. That distinction does not make the proof zero knowledge. The benchmark fixture also publishes these values, including its demonstration secret.

At pinned leanVM-b commit `8494c5d5df323f2b97ed89272942a4bee6247078`, the proving path has no implemented witness-hiding layer:

- Witness columns are [copied unchanged into a zero-padded polynomial](https://github.com/leanEthereum/leanVM-b/blob/8494c5d5df323f2b97ed89272942a4bee6247078/src/witness.rs#L79-L107). The commitment [encodes that witness without a random mask](https://github.com/leanEthereum/leanVM-b/blob/8494c5d5df323f2b97ed89272942a4bee6247078/vendor/flock-core/src/pcs/commit.rs#L181-L232).
- The bus proof [transmits witness-column evaluations](https://github.com/leanEthereum/leanVM-b/blob/8494c5d5df323f2b97ed89272942a4bee6247078/src/leaf.rs#L221-L240), and the constraint proof [transmits its folded column evaluations](https://github.com/leanEthereum/leanVM-b/blob/8494c5d5df323f2b97ed89272942a4bee6247078/src/constraints.rs#L74-L84).
- Polynomial openings contain [codeword rows and a final polynomial in clear](https://github.com/leanEthereum/leanVM-b/blob/8494c5d5df323f2b97ed89272942a4bee6247078/vendor/flock-core/src/pcs/ligerito.rs#L1438-L1454). [Fiat–Shamir challenges are public](https://github.com/leanEthereum/leanVM-b/blob/8494c5d5df323f2b97ed89272942a4bee6247078/src/transcript.rs#L124-L132), so they do not supply secret blinding randomness.

Independent verification without loading witness files demonstrates that verification needs only the program, public input and proof. It does not demonstrate that the proof hides the witness. This code inspection is not a demonstrated recovery of an account address from a benchmark proof, and no such recovery is claimed.

A private-owner proof requires a justified zero-knowledge construction covering the commitment and proof messages, or a suitable established zero-knowledge wrapper, plus consideration of the public encoding shape. Merely hiding fields in the API or adding random unused witness cells is insufficient. Implementing that protection is separate cryptographic work; it does not require adding signature verification or recursive authorization.

The present timings therefore measure the owner-binding relation on this backend. They do not measure a completed private transaction proof or the additional cost of a future privacy layer.
