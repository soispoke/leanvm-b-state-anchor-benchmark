"""Independent synthetic fixtures for the bounded guest relation.

These tests use actual Boolean Keccak in Circuit, never a host hash substitute
inside the relation. Host Keccak constructs the independent expected trie roots.
The exported-op interpreter is deliberately restricted to small RLP circuits:
their operands fit below the field's reduction degree, including malicious 2.
"""

import struct
import tempfile
from pathlib import Path
import unittest

from eth_utils import keccak

from analyze_fixtures import rlp_encode
from real_state.circuit import Circuit
from real_state.hashes import keccak256
from real_state import statement as relation


def compact(nibbles, leaf=True):
    """Hex-prefix encoding independently assembled from integer nibbles."""
    flag = 2 * int(leaf) + len(nibbles) % 2
    digits = [flag] + (list(nibbles) if len(nibbles) % 2 else [0] + list(nibbles))
    return bytes(16 * digits[i] + digits[i + 1] for i in range(0, len(digits), 2))


def key_nibbles(key):
    return [nibble for byte in key for nibble in (byte >> 4, byte & 15)]


def leaf_case(key=bytes(range(32)), value=b"value"):
    node = [compact(key_nibbles(key)), value]
    return key, [node], keccak(rlp_encode(node)), [False]


def branch_case(index, values=(b"first", b"other")):
    """A canonical branch with occupied routes 3 and 12, same public layout."""
    leaves = {}
    branch = [b""] * 17
    for route, value in zip((3, 12), values):
        key = bytes([route << 4]) + bytes(31)
        leaf = [compact(key_nibbles(key)[1:]), value]
        leaves[route] = leaf
        branch[route] = keccak(rlp_encode(leaf))
    key = bytes([index << 4]) + bytes(31)
    return key, [branch, leaves[index]], keccak(rlp_encode(branch)), [False, True]


def compile_inclusion(case, root=None, check_witness=True):
    key, nodes, expected_root, odd_paths = case
    c = Circuit()
    c.check_witness = check_witness
    key_wires = c.witness("key", key)
    root_wires = c.witness("root", expected_root if root is None else root)
    raws = [c.witness(f"node_{i}", rlp_encode(node)) for i, node in enumerate(nodes)]
    result = relation.inclusion(c, key_wires, root_wires, raws,
                                [relation.shape(node) for node in nodes], odd_paths)
    return c, c.read_bytes(result)


def parse(raw, layout, check_witness=True):
    c = Circuit()
    c.check_witness = check_witness
    item = relation.decode(c, c.witness("rlp", raw), layout)
    return c, item


def run_exported_small_circuit(directory, replacements=None):
    """Check write-once arithmetic constraints from the actual exported bytes.

    XOR is binary-field addition. Multiplication is carryless polynomial
    multiplication; these tiny circuits never require degree-128 reduction.
    This is an independent constraint interpreter, not a cryptographic proof.
    """
    program = (directory / "program.bin").read_bytes()
    if program[:8] != b"LVMSTATE":
        raise ValueError("invalid program magic")
    count, instructions = struct.unpack_from("<II", program, 8)
    memory = [None] * count
    public = (directory / "public.bin").read_bytes()
    memory[:2] = [int.from_bytes(public[i:i + 16], "little") for i in (0, 16)]
    witness = (directory / "witness.bin").read_bytes()
    ranges, = struct.unpack_from("<I", witness)
    cursor = 4
    for _ in range(ranges):
        base, length = struct.unpack_from("<II", witness, cursor)
        cursor += 8
        for offset in range(length):
            memory[base + offset] = int.from_bytes(witness[cursor:cursor + 16], "little")
            cursor += 16
    if cursor != len(witness):
        raise ValueError("trailing witness bytes")
    for wire, value in (replacements or {}).items():
        memory[wire] = value

    def assign(wire, value):
        if memory[wire] is not None and memory[wire] != value:
            raise ValueError(f"unsatisfied write-once constraint at wire {wire}")
        memory[wire] = value

    cursor = 16
    for _ in range(instructions):
        op = program[cursor]
        if op == 2:
            out, = struct.unpack_from("<I", program, cursor + 1)
            assign(out, int.from_bytes(program[cursor + 5:cursor + 21], "little"))
            cursor += 21
            continue
        a, b, out = struct.unpack_from("<III", program, cursor + 1)
        x, y = memory[a], memory[b]
        if x is None or y is None:
            raise ValueError("uninitialized operand")
        if op == 0:
            value = x ^ y
        elif op == 1:
            value = 0
            while y:
                if y & 1:
                    value ^= x
                x <<= 1
                y >>= 1
            if value.bit_length() > 128:
                raise ValueError("test interpreter does not implement field reduction")
        else:
            raise ValueError("unknown opcode")
        assign(out, value)
        cursor += 13
    if cursor != len(program):
        raise ValueError("trailing program bytes")
    return memory


class RLPRelationTests(unittest.TestCase):
    def test_canonical_string_encodings_at_prefix_boundaries(self):
        for value in (b"", b"\x00", b"\x7f", b"\x80", b"\xff", bytes(55), bytes(56), bytes(256)):
            with self.subTest(length=len(value), first=value[:1]):
                c, item = parse(rlp_encode(value), relation.shape(value))
                self.assertEqual(c.read_bytes(item.payload), value)

    def test_canonical_nested_list_and_long_list(self):
        for value in ([b"", b"\x01", [b"\x80", b"abc"]], [bytes(56), b"last"]):
            c, item = parse(rlp_encode(value), relation.shape(value))
            self.assertEqual(c.read_bytes(item.raw), rlp_encode(value))
            self.assertEqual(len(item.children), len(value))

    def test_noncanonical_single_byte_and_wrong_bare_flag_reject(self):
        # 0x81 0x01 is a redundant prefix: 0x01 must encode itself.
        with self.assertRaises(ValueError):
            parse(b"\x81\x01", {"kind": "bytes", "length": 1, "bare": False})
        with self.assertRaises(ValueError):
            parse(b"\x80", {"kind": "bytes", "length": 1, "bare": True})

    def test_noncanonical_long_prefixes_and_length_reject(self):
        layout = relation.shape(bytes(56))
        for encoded in (b"\xb8\x37" + bytes(56), b"\xb9\x00\x38" + bytes(56), b"\xb8\x38" + bytes(55)):
            with self.subTest(prefix=encoded[:3]), self.assertRaises(ValueError):
                parse(encoded, layout)
        # An overlong prefix for a short string is rejected too.
        with self.assertRaises(ValueError):
            parse(b"\xb8\x01\x80", relation.shape(b"\x80"))

    def test_storage_integer_zero_width_and_leading_zero(self):
        for value in (b"", b"\x01", b"\x80", b"\xff" * 32):
            c, item = parse(rlp_encode(value), relation.shape(value))
            self.assertEqual(c.read_bytes(relation.integer(c, item, 32)), value)
        for value in (b"\x00", b"\x00\x01", b"\x01" * 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                c, item = parse(rlp_encode(value), relation.shape(value))
                relation.integer(c, item, 32)

    def test_account_integer_fields_reject_leading_zero_and_nonce_overflow(self):
        for nonce, balance in ((b"\x00", b"\x01"), (b"\x01", b"\x00\x01"), (b"\x01" * 9, b"")):
            value = [nonce, balance, bytes(32), bytes([1]) * 32]
            with self.subTest(nonce=nonce, balance=balance), self.assertRaises(ValueError):
                c, item = parse(rlp_encode(value), relation.shape(value))
                relation.integer(c, item.children[0], 8)
                relation.integer(c, item.children[1], 32)

    def test_diagnostics_disabled_still_exports_rejecting_constraints(self):
        layout = {"kind": "bytes", "length": 1, "bare": False}
        good, _ = parse(b"\x81\x80", layout)
        bad, _ = parse(b"\x81\x01", layout, check_witness=False)
        self.assertEqual(good.ops, bad.ops)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            good.export(directory, {})
            run_exported_small_circuit(directory)
            # Same public shape allows other canonical one-byte payloads.
            base = good.inputs[0]["base"]
            run_exported_small_circuit(directory, {base + 8: 1})
            with self.assertRaises(ValueError):
                run_exported_small_circuit(directory, {base + 15: 0})
            with self.assertRaises(ValueError):
                run_exported_small_circuit(directory, {base + 8: 2})
            bad.export(directory, {})
            with self.assertRaises(ValueError):
                run_exported_small_circuit(directory)


class MPTRelationTests(unittest.TestCase):
    def test_full_key_leaf_and_value(self):
        c, result = compile_inclusion(leaf_case())
        self.assertEqual(result, b"value")
        self.assertGreater(c.counts[1], 1000)  # Actual Keccak gates were emitted.

    def test_wrong_secure_key_and_root_reject(self):
        key, nodes, root, odd = leaf_case()
        with self.assertRaises(ValueError):
            compile_inclusion((key[:-1] + bytes([key[-1] ^ 1]), nodes, root, odd))
        with self.assertRaises(ValueError):
            compile_inclusion((key, nodes, root, odd), root=bytes([root[0] ^ 1]) + root[1:])

    def test_leaf_flags_and_even_padding_reject(self):
        key, nodes, _, odd = leaf_case()
        for flag_byte in (0x00, 0x21, 0x30, 0x40):
            node = [bytes([flag_byte]) + nodes[0][0][1:], nodes[0][1]]
            with self.subTest(flag=flag_byte), self.assertRaises(ValueError):
                compile_inclusion((key, [node], keccak(rlp_encode(node)), odd))

    def test_leaf_must_consume_full_key(self):
        key = bytes(32)
        node = [compact(key_nibbles(key)[:-2]), b"value"]
        with self.assertRaises(ValueError):
            compile_inclusion((key, [node], keccak(rlp_encode(node)), [False]))

    def test_branch_selects_two_routes_and_bytecode_ignores_witness_values(self):
        first, first_value = compile_inclusion(branch_case(3))
        second, second_value = compile_inclusion(branch_case(12, (b"third", b"newer")))
        self.assertEqual(first_value, b"first")
        self.assertEqual(second_value, b"newer")
        self.assertEqual(first.ops, second.ops)
        self.assertEqual(first.counts, second.counts)
        self.assertNotEqual(first.inputs[1]["data"], second.inputs[1]["data"])

    def test_branch_wrong_route_and_wrong_child_reject(self):
        key, nodes, root, odd = branch_case(3)
        with self.assertRaises(ValueError):
            compile_inclusion((bytes([0x40]) + key[1:], nodes, root, odd))
        other_leaf = branch_case(12)[1][1]
        with self.assertRaises(ValueError):
            compile_inclusion((key, [nodes[0], other_leaf], root, odd))

    def test_collapsible_branch_rejects(self):
        key, nodes, _, odd = branch_case(3)
        nodes[0][12] = b""
        with self.assertRaises(ValueError):
            compile_inclusion((key, nodes, keccak(rlp_encode(nodes[0])), odd))

    def test_embedded_child_and_hash_reference_boundary(self):
        for encoded_size in (31, 32):
            # 1 list prefix + 1 bare compact path + 1 string prefix + value.
            node = [b"\x30", b"v" * (encoded_size - 3)]
            raw = rlp_encode(node)
            self.assertEqual(len(raw), encoded_size)
            for embedded in (True, False):
                c = Circuit()
                next_raw = c.witness("next_node", raw)
                next_hash = keccak256(c, next_raw)
                child_value = node if embedded else keccak(raw)
                child = relation.decode(c, c.witness("reference", rlp_encode(child_value)), relation.shape(child_value))
                with self.subTest(encoded_size=encoded_size, embedded=embedded):
                    if embedded == (encoded_size < 32):
                        relation.child_matches(c, child, next_raw, next_hash)
                    else:
                        with self.assertRaises(ValueError):
                            relation.child_matches(c, child, next_raw, next_hash)

    def test_adjacent_extension_and_leaf_reject(self):
        key = bytes(32)
        leaf = [compact(key_nibbles(key)[2:]), b"value"]
        extension = [compact(key_nibbles(key)[:2], leaf=False), keccak(rlp_encode(leaf))]
        with self.assertRaisesRegex(ValueError, "adjacent extension"):
            compile_inclusion((key, [extension, leaf], keccak(rlp_encode(extension)), [False, False]))

    def test_valid_extension_branch_and_embedded_leaf(self):
        # A canonical extension needs a branch successor, hence three small
        # node hashes here. The last nibble chooses one of two embedded leaves.
        key = bytes(32)
        leaf = [compact([]), b"a"]
        branch = [b""] * 17
        branch[0], branch[1] = leaf, [compact([]), b"b"]
        self.assertLess(len(rlp_encode(branch)), 32)
        extension = [compact(key_nibbles(key)[:63], leaf=False), branch]
        _, value = compile_inclusion((key, [extension, branch, leaf],
                                      keccak(rlp_encode(extension)), [True, False, False]))
        self.assertEqual(value, b"a")


if __name__ == "__main__":
    unittest.main()
