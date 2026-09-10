"""Differential checks for the Boolean hash algorithms and their padding."""

import hashlib
import random
import unittest

from eth_utils import keccak

from real_state.hashes import keccak256, sha256


class EvalCircuit:
    """Evaluate gates directly, counting calls without constant folding."""

    zero = 0
    one = 1

    def __init__(self):
        self.xor_gates = 0
        self.and_gates = 0

    def xor(self, a, b):
        self.xor_gates += 1
        return a ^ b

    def and_(self, a, b):
        self.and_gates += 1
        return a & b


def evaluate(function, message):
    circuit = EvalCircuit()
    inputs = [[(byte >> bit) & 1 for bit in range(8)] for byte in message]
    result = function(circuit, inputs)
    assert len(result) == 32 and all(len(byte) == 8 for byte in result)
    digest = bytes(sum(bit << i for i, bit in enumerate(byte)) for byte in result)
    return digest, circuit


class HashCircuitTests(unittest.TestCase):
    def test_keccak_empty_known_answer_and_domain(self):
        actual, _ = evaluate(keccak256, b"")
        self.assertEqual(actual.hex(),
                         "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertNotEqual(actual, hashlib.sha3_256(b"").digest())

    def test_sha256_known_answers(self):
        for message in (b"", b"abc",
                        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"):
            with self.subTest(message=message):
                actual, _ = evaluate(sha256, message)
                self.assertEqual(actual, hashlib.sha256(message).digest())

    def test_keccak_padding_and_multiblock(self):
        rng = random.Random(20260910)
        for length in (1, 3, 32, 64, 134, 135, 136, 137, 271, 272,
                       532, 634, 1024):
            with self.subTest(length=length):
                message = rng.randbytes(length)
                actual, _ = evaluate(keccak256, message)
                self.assertEqual(actual, keccak(message))
        self.assertEqual(evaluate(keccak256, b"abc")[0], keccak(b"abc"))

    def test_sha256_padding_and_multiblock(self):
        rng = random.Random(256)
        for length in (1, 31, 32, 55, 56, 57, 63, 64, 65, 119, 120,
                       127, 128, 532, 634, 1024):
            with self.subTest(length=length):
                message = rng.randbytes(length)
                actual, _ = evaluate(sha256, message)
                self.assertEqual(actual, hashlib.sha256(message).digest())

    def test_input_wires_are_not_mutated(self):
        for function in (keccak256, sha256):
            inputs = [[(value >> bit) & 1 for bit in range(8)] for value in range(17)]
            original = [byte[:] for byte in inputs]
            function(EvalCircuit(), inputs)
            self.assertEqual(inputs, original)

    def test_rejects_malformed_byte_shape(self):
        for function in (keccak256, sha256):
            with self.assertRaises(ValueError):
                function(EvalCircuit(), [[0] * 7])


if __name__ == "__main__":
    unittest.main()
