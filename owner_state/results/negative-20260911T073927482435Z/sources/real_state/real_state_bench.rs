//! File-driven real-state Boolean circuits using unchanged leanVM-b opcodes.
//! `prove` includes execution; `verify` never loads the witness file.

use std::env;
use std::fs;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::Path;
use std::time::Instant;

use bincode::Options;
use leanvm_b::cpu::{Op, Program, Proof, prove, verify};
use leanvm_b::field::{F128, g_pow};

struct Reader<'a> {
    bytes: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, pos: 0 }
    }

    fn take(&mut self, count: usize) -> &'a [u8] {
        let end = self.pos.checked_add(count).expect("binary offset overflow");
        assert!(end <= self.bytes.len(), "truncated binary input");
        let result = &self.bytes[self.pos..end];
        self.pos = end;
        result
    }

    fn u32(&mut self) -> u32 {
        u32::from_le_bytes(self.take(4).try_into().unwrap())
    }

    fn field(&mut self) -> F128 {
        let bytes = self.take(16);
        F128::new(
            u64::from_le_bytes(bytes[..8].try_into().unwrap()),
            u64::from_le_bytes(bytes[8..].try_into().unwrap()),
        )
    }

    fn finish(&self) {
        assert_eq!(self.pos, self.bytes.len(), "trailing binary data");
    }
}

struct Loaded {
    program: Program,
    cells: u32,
    counts: [usize; 6],
    cycles: usize,
}

fn assemble(mut ops: Vec<Op>, cells: u32, mut counts: [usize; 6]) -> Loaded {
    assert!(cells >= 2, "frame must include two public cells");
    let main_frame = cells.checked_add(3).expect("frame size overflow");
    let padded = ops
        .len()
        .checked_add(5)
        .and_then(usize::checked_next_power_of_two)
        .expect("bytecode size overflow");
    assert!(
        padded <= u32::MAX as usize,
        "bytecode exceeds u32 addresses"
    );
    let cycles = ops.len() + 4;
    // The final slot is the VM's unexecuted sentinel. Jump over padding to it.
    ops.extend([
        Op::Set {
            o: cells,
            k: F128::ONE,
        },
        Op::Set {
            o: cells + 1,
            k: g_pow(padded - 1),
        },
        Op::Set {
            o: cells + 2,
            k: F128::ONE,
        },
        Op::Jump {
            oc: cells,
            od: cells + 1,
            of: cells + 2,
        },
    ]);
    ops.resize(
        padded,
        Op::Set {
            o: cells,
            k: F128::ONE,
        },
    );
    counts[2] += 3;
    counts[4] += 1;
    Loaded {
        program: Program::from_bytecode(ops, main_frame),
        cells: main_frame,
        counts,
        cycles,
    }
}

fn load_program(bytes: &[u8]) -> Loaded {
    let mut reader = Reader::new(bytes);
    assert_eq!(reader.take(8), b"LVMSTATE", "unknown circuit format");
    let cells = reader.u32();
    let count = reader.u32() as usize;
    assert!(
        count <= (bytes.len() - reader.pos) / 13,
        "impossible instruction count"
    );
    let mut ops = Vec::with_capacity(count);
    let mut counts = [0; 6];
    for _ in 0..count {
        let tag = reader.take(1)[0];
        let op = match tag {
            0 | 1 => {
                let (a, b, c) = (reader.u32(), reader.u32(), reader.u32());
                assert!(
                    a < cells && b < cells && c < cells,
                    "operand outside circuit frame"
                );
                if tag == 0 {
                    Op::Xor { a, b, c }
                } else {
                    Op::Mul { a, b, c }
                }
            }
            2 => {
                let o = reader.u32();
                let k = reader.field();
                assert!(o < cells, "SET target outside circuit frame");
                Op::Set { o, k }
            }
            _ => panic!("unknown instruction tag {tag}"),
        };
        counts[tag as usize] += 1;
        ops.push(op);
    }
    reader.finish();
    assemble(ops, cells, counts)
}

fn load_public(bytes: &[u8]) -> [F128; 2] {
    let mut reader = Reader::new(bytes);
    let public = [reader.field(), reader.field()];
    reader.finish();
    public
}

fn load_witness(loaded: &mut Loaded, bytes: &[u8], mutation: Option<(u32, Option<u128>)>) {
    let mut reader = Reader::new(bytes);
    let range_count = reader.u32() as usize;
    assert!(
        range_count <= (bytes.len() - reader.pos) / 8,
        "impossible witness range count"
    );
    let mut ranges = Vec::new();
    let mut mutated = false;
    for i in 0..range_count {
        let (base, len) = (reader.u32(), reader.u32());
        let end = base.checked_add(len).expect("witness range overflow");
        assert!(
            base >= 2 && end <= loaded.cells - 3,
            "witness outside circuit frame"
        );
        assert!(
            !ranges
                .iter()
                .any(|&(start, stop)| base < stop && start < end),
            "overlapping witness ranges"
        );
        ranges.push((base, end));
        assert!(
            len as usize <= (bytes.len() - reader.pos) / 16,
            "truncated witness range"
        );
        let mut values: Vec<F128> = (0..len).map(|_| reader.field()).collect();
        if let Some((cell, replacement)) = mutation {
            if base <= cell && cell < end {
                let value = &mut values[(cell - base) as usize];
                *value = replacement.map_or(*value + F128::ONE, |value| {
                    F128::new(value as u64, (value >> 64) as u64)
                });
                mutated = true;
            }
        }
        let name = format!("range_{i}");
        loaded.program.add_witness_range(&name, base, len);
        loaded.program.set_witness(name, vec![values]);
    }
    reader.finish();
    assert!(
        mutation.is_none() || mutated,
        "mutation cell is not a witness input"
    );
}

fn decode_proof(bytes: &[u8]) -> Proof {
    bincode::DefaultOptions::new()
        .with_fixint_encoding()
        .reject_trailing_bytes()
        .with_limit(bytes.len() as u64)
        .deserialize(bytes)
        .expect("invalid serialized proof")
}

fn rejection_checks(program: &Program, public: &[F128; 2], proof: &Proof, encoded: &[u8]) {
    for limb in 0..2 {
        let mut wrong = *public;
        wrong[limb] += F128::ONE;
        assert!(
            verify(program, &wrong, proof).is_err(),
            "changed public limb {limb} was accepted"
        );
    }
    // The first eight bytes encode the scalar vector length; alter the first
    // scalar without changing the serialized shape or any allocation length.
    let mut corrupt = encoded.to_vec();
    assert!(corrupt.len() > 8, "empty proof encoding");
    corrupt[8] ^= 1;
    let corrupt_proof = decode_proof(&corrupt);
    assert!(
        verify(program, public, &corrupt_proof).is_err(),
        "mutated serialized proof was accepted"
    );
}

fn milliseconds(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1000.0
}

#[test]
fn real_state_benchmark() {
    let Some(directory) = env::var_os("REAL_STATE_DIR") else {
        eprintln!("REAL_STATE_DIR unset; file-driven benchmark skipped");
        return;
    };
    leanvm_b::init_prover_pool();
    let directory = Path::new(&directory);
    let action = env::var("REAL_STATE_ACTION").unwrap_or_else(|_| "prove".into());
    assert!(
        matches!(action.as_str(), "execute" | "prove" | "verify"),
        "unknown REAL_STATE_ACTION"
    );
    let started = Instant::now();
    let mut loaded =
        load_program(&fs::read(directory.join("program.bin")).expect("read program.bin"));
    let public = load_public(&fs::read(directory.join("public.bin")).expect("read public.bin"));
    let assembly_ms = milliseconds(started);
    let mutation = env::var("REAL_STATE_MUTATE_CELL").ok().map(|cell| {
        (
            cell.parse::<u32>().expect("invalid mutation cell"),
            env::var("REAL_STATE_MUTATE_VALUE")
                .ok()
                .map(|value| value.parse::<u128>().expect("invalid mutation value")),
        )
    });
    assert!(
        mutation.is_none() || action == "execute",
        "witness mutation requires execute action"
    );
    if action != "verify" {
        load_witness(
            &mut loaded,
            &fs::read(directory.join("witness.bin")).expect("read witness.bin"),
            mutation,
        );
    }
    if action == "execute" {
        let started = Instant::now();
        if let Some((cell, _)) = mutation {
            let error = catch_unwind(AssertUnwindSafe(|| loaded.program.execute(public)))
                .err()
                .expect("mutated witness was unexpectedly accepted");
            let message = error
                .downcast_ref::<String>()
                .map(String::as_str)
                .or_else(|| error.downcast_ref::<&str>().copied())
                .unwrap_or("non-string panic");
            assert!(
                message.contains("write-once conflict"),
                "unexpected execution failure: {message}"
            );
            println!(
                "REJECTED mutation_cell={cell} execute_ms={:.3} reason={message}",
                milliseconds(started)
            );
            return;
        }
        let execution = loaded.program.execute(public);
        let execute_ms = milliseconds(started);
        assert_eq!(execution.cycles, loaded.cycles);
        println!(
            "RESULT {{\"action\":\"execute\",\"cycles\":{},\"counts\":{:?},\"cells\":{},\"mem_used\":{},\"assembly_ms\":{:.3},\"execute_ms\":{:.3}}}",
            execution.cycles,
            loaded.counts,
            loaded.cells,
            execution.mem_used,
            assembly_ms,
            execute_ms
        );
    } else if action == "prove" {
        let started = Instant::now();
        let (proof, stats) = prove(&loaded.program, public);
        let prove_ms = milliseconds(started);
        assert_eq!(stats.cycles, loaded.cycles);
        assert_eq!(stats.counts, loaded.counts);
        let encoded = bincode::serialize(&proof).expect("serialize proof");
        fs::write(directory.join("proof.bin"), &encoded).expect("write proof.bin");
        let restored = decode_proof(&encoded);
        let started = Instant::now();
        verify(&loaded.program, &public, &restored).expect("honest proof verifies");
        let verify_ms = milliseconds(started);
        let started = Instant::now();
        rejection_checks(&loaded.program, &public, &restored, &encoded);
        let negative_checks_ms = milliseconds(started);
        println!(
            "RESULT {{\"action\":\"prove\",\"cycles\":{},\"counts\":{:?},\"cells\":{},\"mem_used\":{},\"log_mem\":{},\"committed\":{},\"proof_bytes\":{},\"assembly_ms\":{:.3},\"prove_including_execute_ms\":{:.3},\"verify_ms\":{:.3},\"negative_checks_ms\":{:.3},\"wrong_public_rejected\":true,\"mutated_proof_rejected\":true}}",
            stats.cycles,
            stats.counts,
            loaded.cells,
            stats.mem_used,
            stats.log_mem,
            stats.committed,
            encoded.len(),
            assembly_ms,
            prove_ms,
            verify_ms,
            negative_checks_ms
        );
    } else {
        let encoded = fs::read(directory.join("proof.bin")).expect("read proof.bin");
        let proof = decode_proof(&encoded);
        let started = Instant::now();
        verify(&loaded.program, &public, &proof).expect("independent proof verification");
        let verify_ms = milliseconds(started);
        println!(
            "RESULT {{\"action\":\"verify\",\"cycles\":{},\"counts\":{:?},\"cells\":{},\"proof_bytes\":{},\"assembly_ms\":{:.3},\"verify_ms\":{:.3},\"witness_loaded\":false}}",
            loaded.cycles,
            loaded.counts,
            loaded.cells,
            encoded.len(),
            assembly_ms,
            verify_ms
        );
    }
}

#[test]
fn witness_hint_keeps_bytecode_fixed_and_constrains_bits() {
    let mut loaded = assemble(vec![Op::Mul { a: 2, b: 2, c: 2 }], 3, [0, 1, 0, 0, 0, 0]);
    let original = format!("{:?}", loaded.program.prog);
    loaded.program.add_witness_range("bit", 2, 1);
    for value in [F128::ZERO, F128::ONE] {
        loaded.program.set_witness("bit", vec![vec![value]]);
        assert_eq!(
            loaded.program.execute([F128::ZERO; 2]).cycles,
            loaded.cycles
        );
        assert_eq!(format!("{:?}", loaded.program.prog), original);
    }
    loaded
        .program
        .set_witness("bit", vec![vec![F128::new(2, 0)]]);
    assert!(catch_unwind(AssertUnwindSafe(|| loaded.program.execute([F128::ZERO; 2]))).is_err());
    assert_eq!(format!("{:?}", loaded.program.prog), original);
}

#[test]
fn witness_hint_rejects_public_cells_and_out_of_frame_ranges() {
    for (base, len) in [(0, 1), (1, 1), (7, 1), (u32::MAX, 2)] {
        let mut loaded = assemble(vec![], 3, [0; 6]);
        assert!(
            catch_unwind(AssertUnwindSafe(|| loaded
                .program
                .add_witness_range("bad", base, len)))
            .is_err()
        );
    }
}

#[test]
fn proven_witness_cannot_be_reused_with_substituted_bytecode() {
    leanvm_b::init_prover_pool();
    let mut loaded = assemble(vec![Op::Mul { a: 2, b: 2, c: 2 }], 3, [0, 1, 0, 0, 0, 0]);
    loaded.program.add_witness_range("bit", 2, 1);
    loaded.program.set_witness("bit", vec![vec![F128::ONE]]);
    let public = [F128::ZERO; 2];
    let (proof, _) = prove(&loaded.program, public);
    // Honest public verification needs neither witness hints nor witness data.
    let honest = Program::from_bytecode(loaded.program.prog.clone(), loaded.cells);
    verify(&honest, &public, &proof).expect("witness-free verification");
    let mut substituted = loaded.program.prog.clone();
    // Even an unexecuted sentinel change must alter the bound program digest.
    *substituted.last_mut().unwrap() = Op::Set {
        o: loaded.cells - 1,
        k: F128::ZERO,
    };
    let substituted = Program::from_bytecode(substituted, loaded.cells);
    assert!(verify(&substituted, &public, &proof).is_err());
}

#[test]
fn binary_inputs_reject_truncation_unknown_tags_and_trailing_data() {
    let mut bytes = b"LVMSTATE".to_vec();
    bytes.extend(3u32.to_le_bytes());
    bytes.extend(1u32.to_le_bytes());
    bytes.push(1);
    for _ in 0..3 {
        bytes.extend(2u32.to_le_bytes());
    }
    assert_eq!(load_program(&bytes).cycles, 5);
    for length in 0..bytes.len() {
        assert!(catch_unwind(|| load_program(&bytes[..length])).is_err());
    }
    let mut unknown = bytes.clone();
    unknown[16] = 3;
    assert!(catch_unwind(|| load_program(&unknown)).is_err());
    bytes.push(0);
    assert!(catch_unwind(|| load_program(&bytes)).is_err());
    assert!(catch_unwind(|| load_public(&[0; 31])).is_err());
    assert!(catch_unwind(|| load_public(&[0; 33])).is_err());
}
