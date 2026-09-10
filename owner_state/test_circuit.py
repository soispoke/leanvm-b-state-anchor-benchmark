"""Independent exported-constraint checks for compiler optimization safety.

The imported interpreter evaluates emitted XOR/MUL/SET bytes. Boolean hashes
and public bit packing never exceed degree 127, so its carryless multiplier is
exact here. These checks are not a substitute for native VM/prover tests.
"""

import hashlib
from pathlib import Path
import tempfile
import unittest

from eth_utils import keccak

from owner_state.circuit import Circuit
from owner_state.hashes import keccak256, sha256, sha256_hybrid, sha256_ripple
from real_state.test_statement import run_exported_small_circuit


class CompilerOptimizationTests(unittest.TestCase):
    def test_dead_dag_is_removed_but_unused_witness_booleanity_remains(self):
        c = Circuit(cse=True, dce=True)
        byte = c.witness('unused', b'\x05')[0]
        dead = byte[0]
        for _ in range(12):
            dead = c.xor(c.and_(dead, byte[1]), byte[2])
        before = sum(c.counts)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c.export(directory, {})
            self.assertLess(sum(c.counts), before)
            self.assertEqual(c.counts, [0, 8, 2])
            self.assertEqual(len(c.values), 12)
            run_exported_small_circuit(directory)
            base = c.inputs[0]['base']
            # An unused Boolean is unrestricted, but it must remain Boolean.
            run_exported_small_circuit(directory, {base: 0})
            with self.assertRaisesRegex(ValueError, 'write-once'):
                run_exported_small_circuit(directory, {base: 2})

    def test_unused_equality_still_rejects(self):
        c = Circuit(dce=True)
        bit = c.witness('x', b'\x00')[0][0]
        c.check_witness = False
        c.assert_eq(bit, c.one)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c.export(directory, {})
            self.assertEqual(c.counts[0], 1)
            with self.assertRaisesRegex(ValueError, 'write-once'):
                run_exported_small_circuit(directory)

    def test_conflicting_writes_retain_original_computation(self):
        for second_write in ('xor', 'set'):
            with self.subTest(second_write=second_write):
                c = Circuit(dce=True)
                bits = c.witness('x', b'\x00')[0]
                target = c.xor(bits[0], bits[1])
                if second_write == 'xor':
                    c._gate(0, c.one, c.zero, target)
                else:
                    c._set(target, 1)
                with tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    c.export(directory, {})
                    self.assertEqual(sum(c.counts), 12)
                    with self.assertRaisesRegex(ValueError, 'write-once'):
                        run_exported_small_circuit(directory)

    def test_conflicting_constant_writes_remain(self):
        c = Circuit(dce=True)
        target = c._wire(0)
        c._set(target, 0)
        c._set(target, 1)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c.export(directory, {})
            self.assertEqual(c.counts, [0, 0, 4])
            with self.assertRaisesRegex(ValueError, 'write-once'):
                run_exported_small_circuit(directory)

    def test_compacted_witness_ranges_remain_contiguous(self):
        c = Circuit(dce=True)
        first = c.witness('first', b'\x04\x05')
        dead = first[0][0]
        for _ in range(10):
            dead = c.xor(c.and_(dead, first[0][1]), first[1][2])
        second = c.witness('second', b'\x06\x07\x08')
        original_second_base = c.inputs[1]['base']
        c.assert_bytes(first, c.literal(b'\x04\x05'))
        c.assert_bytes(second, c.literal(b'\x06\x07\x08'))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c.export(directory, {})
            self.assertLess(c.inputs[1]['base'], original_second_base)
            self.assertEqual(c.inputs[1]['base'], c.inputs[0]['base'] + 16)
            memory = run_exported_small_circuit(directory)
            for entry in c.inputs:
                expected = [(byte >> bit) & 1 for byte in entry['data'] for bit in range(8)]
                self.assertEqual(memory[entry['base']:entry['base'] + entry['length']], expected)

    def test_empty_witness_exports_after_compaction(self):
        for dce in (False, True):
            with self.subTest(dce=dce):
                c = Circuit(dce=dce)
                c.witness('empty', b'')
                with tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    c.export(directory, {})
                    run_exported_small_circuit(directory)

    def test_cse_is_local_and_double_not_is_exact(self):
        c = Circuit(cse=True)
        a, b = c.witness('x', b'\x12')[0][:2]
        with c.hash_scope('test', 1):
            first = c.xor(a, b)
            self.assertEqual(first, c.xor(b, a))
            self.assertEqual(c.and_(a, b), c.and_(b, a))
            self.assertEqual(c.not_(c.not_(a)), a)
        with c.hash_scope('test', 1):
            self.assertNotEqual(first, c.xor(a, b))

    def test_valid_different_witnesses_produce_identical_optimized_program(self):
        programs = []
        for message in (bytes(32), bytes(range(32))):
            c = Circuit(cse=True, dce=True)
            digest = keccak256(c, c.witness('message', message))
            self.assertEqual(c.read_bytes(digest), keccak(message))
            c.pack_public(digest)
            c.finalize()
            programs.append(bytes(c.ops))
            before = (bytes(c.ops), c.counts[:], list(c.values))
            c.finalize()
            self.assertEqual(before, (bytes(c.ops), c.counts, c.values))
        self.assertEqual(programs[0], programs[1])

    def test_hash_binding_survives_dce_and_rejects_witness_public_mutations(self):
        message = bytes(range(64))
        for function in (keccak256, sha256, sha256_hybrid, sha256_ripple):
            with self.subTest(function=function.__name__):
                expected = keccak(message) if function is keccak256 else hashlib.sha256(message).digest()
                public_inputs = []
                for optimized in (False, True):
                    c = Circuit(cse=optimized, dce=optimized)
                    digest = function(c, c.witness('message', message))
                    self.assertEqual(c.read_bytes(digest), expected)
                    c.pack_public(digest)
                    with tempfile.TemporaryDirectory() as temporary:
                        directory = Path(temporary)
                        c.export(directory, {})
                        memory = run_exported_small_circuit(directory)
                        public_inputs.append(memory[:2])
                        if not optimized:
                            continue
                        self.assertLessEqual(c.optimization['after_dce']['instructions'],
                                             c.optimization['before_dce']['instructions'])
                        base = c.inputs[0]['base']
                        for bit in (0, 128, 511):
                            with self.assertRaisesRegex(ValueError, 'write-once'):
                                run_exported_small_circuit(directory, {base + bit: memory[base + bit] ^ 1})
                        with self.assertRaisesRegex(ValueError, 'write-once'):
                            run_exported_small_circuit(directory, {base: 2})
                        with self.assertRaisesRegex(ValueError, 'write-once'):
                            run_exported_small_circuit(directory, {0: memory[0] ^ 1})
                self.assertEqual(public_inputs[0], public_inputs[1])


if __name__ == '__main__':
    unittest.main()
