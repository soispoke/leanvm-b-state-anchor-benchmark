//! leanVM-b execution check for the structural state anchor counts.
//!
//! Each case runs the exact number of native BLAKE3 calls counted by
//! `analyze_fixtures.py`. It checks execution and cycle counts. It does not
//! implement RLP parsing, trie navigation, or the private predicate.

use std::time::Instant;

use leanvm_b::blake3_flock::warm_setup;
use leanvm_b::compiler::{compile, parse};
use leanvm_b::cpu::{prove, verify};
use leanvm_b::field::F128;
use leanvm_b::vmhash::compress;

#[derive(Clone, Copy)]
struct Case {
    name: &'static str,
    hashes: usize,
}

const CASES: [Case; 24] = [
    Case {
        name: "plain_eoa_direct_state",
        hashes: 125,
    },
    Case {
        name: "plain_eoa_ssz_block",
        hashes: 130,
    },
    Case {
        name: "plain_eoa_rlp_block",
        hashes: 145,
    },
    Case {
        name: "account_storage_word_direct_state",
        hashes: 141,
    },
    Case {
        name: "account_storage_word_ssz_block",
        hashes: 146,
    },
    Case {
        name: "account_storage_word_rlp_block",
        hashes: 161,
    },
    Case {
        name: "weth_balance_direct_state",
        hashes: 220,
    },
    Case {
        name: "weth_balance_ssz_block",
        hashes: 225,
    },
    Case {
        name: "weth_balance_rlp_block",
        hashes: 240,
    },
    Case {
        name: "bayc_token_100_owner_direct_state",
        hashes: 305,
    },
    Case {
        name: "bayc_token_100_owner_ssz_block",
        hashes: 310,
    },
    Case {
        name: "bayc_token_100_owner_rlp_block",
        hashes: 325,
    },
    Case {
        name: "safe_authorization_direct_state",
        hashes: 151,
    },
    Case {
        name: "safe_authorization_ssz_block",
        hashes: 156,
    },
    Case {
        name: "safe_authorization_rlp_block",
        hashes: 171,
    },
    Case {
        name: "tornado_recent_root_direct_state",
        hashes: 248,
    },
    Case {
        name: "tornado_recent_root_ssz_block",
        hashes: 253,
    },
    Case {
        name: "tornado_recent_root_rlp_block",
        hashes: 268,
    },
    Case {
        name: "weth_and_bayc_direct_state",
        hashes: 508,
    },
    Case {
        name: "weth_and_bayc_ssz_block",
        hashes: 513,
    },
    Case {
        name: "weth_and_bayc_rlp_block",
        hashes: 528,
    },
    Case {
        name: "native_weth_and_bayc_direct_state",
        hashes: 616,
    },
    Case {
        name: "native_weth_and_bayc_ssz_block",
        hashes: 621,
    },
    Case {
        name: "native_weth_and_bayc_rlp_block",
        hashes: 636,
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
fn state_anchor_usecases() {
    leanvm_b::init_prover_pool();
    let selected = std::env::var("STATE_ANCHOR_CASE").unwrap_or_else(|_| "all".to_string());
    assert!(
        selected == "all" || CASES.iter().any(|case| case.name == selected),
        "unknown STATE_ANCHOR_CASE: {selected}"
    );

    for case in CASES {
        if selected != "all" && selected != case.name {
            continue;
        }

        let seed = [word(0, 1), word(0, 2)];
        let blocks: Vec<Vec<F128>> = (0..case.hashes)
            .map(|i| vec![word(i + 1, 3), word(i + 1, 4)])
            .collect();
        let mut want = seed;
        for block in &blocks {
            want = compress(want, [block[0], block[1]]);
        }

        let mut program = compile(&parse(&chain_source(case.hashes)).expect("program parses"));
        program.set_witness("seed", vec![seed.to_vec()]);
        program.set_witness("blocks", blocks);
        warm_setup(case.hashes);

        let started = Instant::now();
        let (proof, stats) = prove(&program, want);
        let prove_ms = started.elapsed().as_secs_f64() * 1000.0;
        let started = Instant::now();
        verify(&program, &want, &proof).expect("proof verifies");
        let verify_ms = started.elapsed().as_secs_f64() * 1000.0;

        assert_eq!(stats.counts[5], case.hashes);
        assert_eq!(stats.cycles, 20 + 24 * case.hashes);
        let bad = [want[0], want[1] + F128::ONE];
        assert!(
            verify(&program, &bad, &proof).is_err(),
            "changed claimed chain output must fail"
        );

        println!(
            "RESULT case={} hashes={} cycles={} committed={} proof_bytes={} prove_ms={:.3} verify_ms={:.3}",
            case.name,
            case.hashes,
            stats.cycles,
            stats.committed,
            bincode::serialized_size(&proof).expect("proof serializes"),
            prove_ms,
            verify_ms,
        );
    }
}
