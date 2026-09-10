//! Structural state-anchor benchmark for leanVM-b.
//!
//! This deliberately uses leanVM-b's native BLAKE3 relation for every hash. It
//! measures the incremental authenticated work in four proof paths, not the
//! relative cost of Keccak, SHA-256, and BLAKE3.

use std::time::Instant;

use leanvm_b::blake3_flock::warm_setup;
use leanvm_b::compiler::{compile, parse};
use leanvm_b::cpu::{prove, verify};
use leanvm_b::field::F128;
use leanvm_b::vmhash::compress;

// One transaction-binding hash plus a representative 32-level private
// authorization path.
const AUTH_HASHES: usize = 33;

// A pinned mainnet eth_getProof fixture at block 0x18bd000 for one WETH balance has
// nine account-proof nodes and seven storage-proof nodes. Hashing each node as
// 32-byte blocks takes 122 + 95 = 217 compressions. This deliberately measures
// the data shape with one uniform hash and does not model RLP parsing.
const STATE_WITNESS_HASHES: usize = 217;

// EIP-7807's state_root is field 2 of an 18-field ProgressiveContainer. Its
// branch has two hashes inside the four-leaf subtree, two progressive-tree
// links, and the active-fields mix-in.
const SSZ_HEADER_HASHES: usize = 5;

// The RLP header of the same pinned block is 634 bytes and independently
// re-hashes to its RPC block hash. At 32 bytes per uniform-hash input block it
// takes ceil(634 / 32) = 20 compressions.
const RLP_HEADER_HASHES: usize = 20;

#[derive(Clone, Copy)]
struct Variant {
    name: &'static str,
    header_hashes: usize,
    state_hashes: usize,
}

impl Variant {
    fn hashes_per_tx(self) -> usize {
        AUTH_HASHES + self.state_hashes + self.header_hashes
    }
}

const VARIANTS: [Variant; 4] = [
    Variant {
        name: "direct_app_root",
        header_hashes: 0,
        state_hashes: 0,
    },
    Variant {
        name: "direct_state_root",
        header_hashes: 0,
        state_hashes: STATE_WITNESS_HASHES,
    },
    Variant {
        name: "eip7807_ssz_block_hash",
        header_hashes: SSZ_HEADER_HASHES,
        state_hashes: STATE_WITNESS_HASHES,
    },
    Variant {
        name: "rlp_block_hash",
        header_hashes: RLP_HEADER_HASHES,
        state_hashes: STATE_WITNESS_HASHES,
    },
];

fn chain_source(n: usize) -> String {
    let final_lo = 2 * n;
    let final_hi = final_lo + 1;
    format!(
        "def main():\n\
         \x20   buff = HeapBuf({size})\n\
         \x20   seed = StackBuf(2)\n\
         \x20   hint_witness(seed, \"seed\")\n\
         \x20   buff[1] = seed[0]\n\
         \x20   buff[GEN] = seed[1]\n\
         \x20   for i in mul_range(1, GEN ** {n}):\n\
         \x20       b = i * i\n\
         \x20       block = StackBuf(2)\n\
         \x20       hint_witness(block, \"blocks\")\n\
         \x20       blake3(buff[b:b + 2], block, buff[b * GEN ** 2:b * GEN ** 2 + 2])\n\
         \x20   p = GEN ** 0\n\
         \x20   p[1] = buff[GEN ** {final_lo}]\n\
         \x20   p[GEN] = buff[GEN ** {final_hi}]\n\
         \x20   return\n",
        size = 2 * n + 2,
    )
}

fn word(i: usize, lane: u64) -> F128 {
    let x = (i as u64)
        .wrapping_mul(0x9e37_79b9_7f4a_7c15)
        .wrapping_add(lane);
    F128::new(x, x.rotate_left(23) ^ 0xa5a5_5a5a_d3c4_b2e1)
}

#[test]
fn state_anchor_paths() {
    leanvm_b::init_prover_pool();
    let selected = std::env::var("STATE_ANCHOR_VARIANT").unwrap_or_else(|_| "all".to_string());
    assert!(
        selected == "all" || VARIANTS.iter().any(|variant| variant.name == selected),
        "unknown STATE_ANCHOR_VARIANT: {selected}"
    );
    let batch = std::env::var("STATE_ANCHOR_BATCH")
        .ok()
        .map(|s| {
            s.parse()
                .expect("STATE_ANCHOR_BATCH must be a positive integer")
        })
        .unwrap_or(512usize);
    let repeat = std::env::var("STATE_ANCHOR_REPEAT")
        .ok()
        .map(|s| {
            s.parse()
                .expect("STATE_ANCHOR_REPEAT must be a positive integer")
        })
        .unwrap_or(3usize);
    assert!(batch > 0, "STATE_ANCHOR_BATCH must be positive");
    assert!(repeat > 0, "STATE_ANCHOR_REPEAT must be positive");

    for variant in VARIANTS {
        if selected != "all" && selected != variant.name {
            continue;
        }

        let hashes_per_tx = variant.hashes_per_tx();
        let total_hashes = hashes_per_tx
            .checked_mul(batch)
            .expect("STATE_ANCHOR_BATCH is too large");
        let seed = [word(0, 1), word(0, 2)];
        let blocks: Vec<Vec<F128>> = (0..total_hashes)
            .map(|i| vec![word(i + 1, 3), word(i + 1, 4)])
            .collect();
        let mut want = seed;
        for block in &blocks {
            want = compress(want, [block[0], block[1]]);
        }

        let mut program =
            compile(&parse(&chain_source(total_hashes)).expect("benchmark program parses"));
        program.set_witness("seed", vec![seed.to_vec()]);
        program.set_witness("blocks", blocks);
        warm_setup(total_hashes);

        // Discard one complete warmup so the samples do not include first-use
        // prover allocations and caches. The proof is still verified.
        let (warm_proof, _) = prove(&program, want);
        verify(&program, &want, &warm_proof).expect("warmup proof verifies");

        let mut prove_ms = Vec::with_capacity(repeat);
        let mut verify_ms = Vec::with_capacity(repeat);
        let mut last_stats = None;
        let mut last_proof_bytes = 0u64;

        for _ in 0..repeat {
            let t = Instant::now();
            let (proof, stats) = prove(&program, want);
            prove_ms.push(t.elapsed().as_secs_f64() * 1000.0);

            let t = Instant::now();
            verify(&program, &want, &proof).expect("state-anchor proof verifies");
            verify_ms.push(t.elapsed().as_secs_f64() * 1000.0);

            last_proof_bytes = bincode::serialized_size(&proof).expect("proof serializes");
            last_stats = Some(stats);
        }

        let stats = last_stats.expect("at least one repetition");
        assert_eq!(stats.counts[5], total_hashes);
        let bad = [want[0], want[1] + F128::ONE];
        let (proof, _) = prove(&program, want);
        assert!(
            verify(&program, &bad, &proof).is_err(),
            "changed claimed chain output must fail"
        );

        let mean = |xs: &[f64]| xs.iter().sum::<f64>() / xs.len() as f64;
        println!(
            "RESULT variant={} batch={} auth_hashes={} state_hashes={} header_hashes={} hashes_per_tx={} total_hashes={} cycles={} committed={} proof_bytes={} prove_ms_mean={:.3} verify_ms_mean={:.3} prove_ms_samples={:?} verify_ms_samples={:?}",
            variant.name,
            batch,
            AUTH_HASHES,
            variant.state_hashes,
            variant.header_hashes,
            hashes_per_tx,
            total_hashes,
            stats.cycles,
            stats.committed,
            last_proof_bytes,
            mean(&prove_ms),
            mean(&verify_ms),
            prove_ms,
            verify_ms,
        );
    }
}
