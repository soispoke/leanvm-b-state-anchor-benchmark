//! Repeated timing run for the synthetic leanVM-b state anchor workloads.
//!
//! Each workload is a serial BLAKE3 chain with the structural count produced by
//! `analyze_fixtures.py`. The proving timer excludes host-side program and
//! input preparation, one-time BLAKE3 setup, warmups, and verification. It
//! includes VM execution and proof witness generation inside `prove()`. It does
//! not execute RLP, MPT, SSZ, or private spend logic.

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
    let cells = n.checked_mul(2).expect("hash count is too large");
    let final_hi = cells.checked_add(1).expect("hash count is too large");
    let size = cells.checked_add(2).expect("hash count is too large");
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
         \x20   p[1] = buff[GEN ** {cells}]\n\
         \x20   p[GEN] = buff[GEN ** {final_hi}]\n\
         \x20   return\n",
    )
}

fn word(i: usize, lane: u64) -> F128 {
    let x = (i as u64)
        .wrapping_mul(0x9e37_79b9_7f4a_7c15)
        .wrapping_add(lane);
    F128::new(x, x.rotate_left(23) ^ 0xa5a5_5a5a_d3c4_b2e1)
}

fn positive_env(name: &str, default: usize) -> usize {
    let value = std::env::var(name)
        .ok()
        .map(|text| {
            text.parse()
                .unwrap_or_else(|_| panic!("{name} must be a positive integer"))
        })
        .unwrap_or(default);
    assert!(value > 0, "{name} must be positive");
    assert!(value <= 1_000, "{name} must not exceed 1000");
    value
}

fn shuffled_indices(length: usize, pass: usize, session: usize) -> Vec<usize> {
    let mut indices: Vec<usize> = (0..length).collect();
    let mut state = (pass as u64 + 1).wrapping_mul(0x9e37_79b9_7f4a_7c15)
        ^ (session as u64 + 1).wrapping_mul(0xd1b5_4a32_d192_ed03);
    for upper in (1..length).rev() {
        state ^= state >> 12;
        state ^= state << 25;
        state ^= state >> 27;
        state = state.wrapping_mul(0x2545_f491_4f6c_dd1d);
        indices.swap(upper, state as usize % (upper + 1));
    }
    indices
}

#[test]
fn time_state_anchor_usecases() {
    leanvm_b::init_prover_pool();
    let repeats = positive_env("STATE_ANCHOR_TIMING_REPEATS", 10);
    let warmups = positive_env("STATE_ANCHOR_TIMING_WARMUPS", 3);
    let session = std::env::var("STATE_ANCHOR_TIMING_SESSION")
        .ok()
        .map(|text| {
            text.parse::<usize>()
                .expect("STATE_ANCHOR_TIMING_SESSION must be a nonnegative integer")
        })
        .unwrap_or(0);

    let mut prepared = Vec::with_capacity(CASES.len());
    for case in CASES {
        let seed = [word(0, 1), word(0, 2)];
        let blocks: Vec<Vec<F128>> = (0..case.hashes)
            .map(|index| vec![word(index + 1, 3), word(index + 1, 4)])
            .collect();
        let mut want = seed;
        for block in &blocks {
            want = compress(want, [block[0], block[1]]);
        }
        let mut program = compile(&parse(&chain_source(case.hashes)).expect("program parses"));
        program.set_witness("seed", vec![seed.to_vec()]);
        program.set_witness("blocks", blocks);
        warm_setup(case.hashes);
        prepared.push((case, program, want));
    }

    for (case, program, want) in &prepared {
        for _ in 0..warmups {
            let (proof, stats) = prove(program, *want);
            assert_eq!(stats.counts[5], case.hashes);
            assert_eq!(stats.cycles, 20 + 24 * case.hashes);
            verify(program, want, &proof).expect("warmup proof verifies");
        }
        let (proof, _) = prove(program, *want);
        let bad = [want[0], want[1] + F128::ONE];
        assert!(
            verify(program, &bad, &proof).is_err(),
            "changed claimed chain output must fail"
        );
    }

    println!(
        "TIMING_CONFIG session={} cases={} repeats={} warmups={} order=deterministic_shuffled_passes",
        session,
        prepared.len(),
        repeats,
        warmups,
    );
    for sample in 0..repeats {
        for (order, index) in shuffled_indices(prepared.len(), sample, session)
            .into_iter()
            .enumerate()
        {
            let (case, program, want) = &prepared[index];
            let started = Instant::now();
            let (proof, stats) = prove(program, *want);
            let prove_ns = started.elapsed().as_nanos();

            let started = Instant::now();
            verify(program, want, &proof).expect("timed proof verifies");
            let verify_ns = started.elapsed().as_nanos();

            assert_eq!(stats.counts[5], case.hashes);
            assert_eq!(stats.cycles, 20 + 24 * case.hashes);
            println!(
                "SAMPLE session={} pass={} order={} case={} hashes={} blake3_domain={} cycles={} committed={} log_mem={} mem_used={} proof_bytes={} prove_ns={} verify_ns={}",
                session,
                sample,
                order,
                case.name,
                case.hashes,
                case.hashes.next_power_of_two(),
                stats.cycles,
                stats.committed,
                stats.log_mem,
                stats.mem_used,
                bincode::serialized_size(&proof).expect("proof serializes"),
                prove_ns,
                verify_ns,
            );
        }
    }
}
