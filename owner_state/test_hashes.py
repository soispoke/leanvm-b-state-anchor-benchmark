"""Differential tests for hash candidates and the exact carry substitution."""

import hashlib
import itertools
import random
import unittest
from contextlib import contextmanager

from eth_utils import keccak

from real_state.circuit import Circuit as BaselineCircuit
from real_state.hashes import _add as ripple_add
from real_state.test_hashes import EvalCircuit, evaluate

from owner_state.hashes import (
    _add, _add_hybrid, _full_adder, _full_adder_hybrid, keccak256,
    sha256, sha256_hybrid, sha256_ripple,
)


class HashCandidateTests(unittest.TestCase):
    def test_full_adder_exhaustively(self):
        for a, b, carry in itertools.product((0, 1), repeat=3):
            c = EvalCircuit()
            bit, next_carry = _full_adder(c, a, b, carry)
            self.assertEqual(bit + 2 * next_carry, a + b + carry)
            self.assertEqual((c.xor_gates, c.and_gates), (4, 1))
            bit, next_carry = _full_adder_hybrid(EvalCircuit(), a, b, carry)
            self.assertEqual(bit + 2 * next_carry, a + b + carry)

    def test_addition_random_and_carry_boundaries(self):
        rng = random.Random(20260911)
        pairs = [(0, 0), (0xffffffff, 1), (0xffffffff, 0xffffffff),
                 (0xaaaaaaaa, 0x55555555)]
        pairs += [(2**i - 1, 1) for i in range(1, 33)]
        pairs += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(512)]
        for a, b in pairs:
            for adder in (_add, _add_hybrid):
                actual = adder(EvalCircuit(), [(a >> i) & 1 for i in range(32)],
                               [(b >> i) & 1 for i in range(32)])
                self.assertEqual(sum(bit << i for i, bit in enumerate(actual)),
                                 (a + b) & 0xffffffff)

    def test_exact_variable_adder_gate_tradeoff(self):
        counts = []
        for function in (ripple_add, _add, _add_hybrid):
            c = BaselineCircuit()
            a = [bit for byte in c.witness('a', bytes(4)) for bit in byte]
            b = [bit for byte in c.witness('b', bytes(4)) for bit in byte]
            before = c.counts[:]
            function(c, a, b)
            counts.append([after - old for after, old in zip(c.counts, before)])
        self.assertEqual(counts, [[93, 61, 0], [123, 31, 0], [123, 31, 0]])

    def test_keccak_padding_and_multiblock(self):
        rng = random.Random(20260910)
        for length in (0, 1, 20, 32, 64, 134, 135, 136, 137,
                       271, 272, 532, 634, 1024):
            with self.subTest(length=length):
                message = rng.randbytes(length)
                self.assertEqual(evaluate(keccak256, message)[0], keccak(message))
        self.assertNotEqual(evaluate(keccak256, b'')[0], hashlib.sha3_256(b'').digest())

    def test_sha_candidates_padding_and_multiblock(self):
        rng = random.Random(256)
        for length in (0, 1, 31, 32, 55, 56, 57, 63, 64, 65, 119, 120,
                       127, 128, 532, 634, 1024):
            message = rng.randbytes(length)
            for function in (sha256, sha256_hybrid, sha256_ripple):
                with self.subTest(length=length, candidate=function.__name__):
                    self.assertEqual(evaluate(function, message)[0],
                                     hashlib.sha256(message).digest())

    def test_scope_is_used_and_closed_even_on_rejected_input(self):
        class ScopedCircuit(EvalCircuit):
            def __init__(self):
                super().__init__()
                self.entered = self.exited = 0

            @contextmanager
            def hash_scope(self, name, length):
                self.asserted_name = name
                self.asserted_length = length
                self.entered += 1
                try:
                    yield
                finally:
                    self.exited += 1

        for function in (keccak256, sha256, sha256_hybrid, sha256_ripple):
            c = ScopedCircuit()
            function(c, [])
            with self.assertRaises(ValueError):
                function(c, [[0] * 7])
            self.assertEqual((c.entered, c.exited), (2, 2))

    def test_no_witness_specialization_and_input_mutation(self):
        for function in (keccak256, sha256, sha256_hybrid, sha256_ripple):
            programs = []
            for message in (bytes(64), bytes(range(64))):
                c = BaselineCircuit()
                inputs = c.witness('message', message)
                original = [byte[:] for byte in inputs]
                digest = function(c, inputs)
                expected = keccak(message) if function is keccak256 else hashlib.sha256(message).digest()
                self.assertEqual(c.read_bytes(digest), expected)
                self.assertEqual(inputs, original)
                programs.append(c.ops)
            self.assertEqual(programs[0], programs[1])


if __name__ == '__main__':
    unittest.main()
