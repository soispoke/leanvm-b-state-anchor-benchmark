#!/usr/bin/env python3
"""Adversarial unit tests for the fixture MPT verifier."""

from __future__ import annotations

import unittest
from typing import Any

from analyze_fixtures import ProofError, keccak, nibbles, rlp_encode, verify_mpt


def compact_encode(path: list[int], *, leaf: bool) -> bytes:
    odd = len(path) % 2
    flags = 2 * int(leaf) + odd
    encoded = [flags] + path if odd else [flags, 0] + path
    return bytes(16 * encoded[index] + encoded[index + 1] for index in range(0, len(encoded), 2))


def as_hex(value: bytes) -> str:
    return "0x" + value.hex()


class MptNodeEncodingTests(unittest.TestCase):
    key = b"fixture-key"
    path = nibbles(keccak(key))
    selected = path[-1]
    sibling = (selected + 1) % 16

    def branch(self, selected_child: Any, *, value: bytes = b"", include_sibling: bool = True) -> list[Any]:
        node: list[Any] = [b""] * 17
        node[self.selected] = selected_child
        if include_sibling:
            node[self.sibling] = [compact_encode([], leaf=True), b"s"]
        node[16] = value
        return node

    def root_for_branch(self, branch: list[Any], *, force_hash: bool = False) -> tuple[bytes, list[str]]:
        encoded_branch = rlp_encode(branch)
        hashed = force_hash or len(encoded_branch) >= 32
        child = keccak(encoded_branch) if hashed else branch
        root_node = [compact_encode(self.path[:-1], leaf=False), child]
        encoded_root = rlp_encode(root_node)
        proof = [as_hex(encoded_root)]
        if hashed:
            proof.append(as_hex(encoded_branch))
        return keccak(encoded_root), proof

    def test_accepts_short_embedded_children(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v"]
        branch = self.branch(leaf)
        self.assertLess(len(rlp_encode(leaf)), 32)
        self.assertLess(len(rlp_encode(branch)), 32)
        root, proof = self.root_for_branch(branch)

        self.assertEqual(verify_mpt(root, self.key, proof), b"v")

    def test_accepts_exact_32_byte_hashed_child(self) -> None:
        value = b"v" * 29
        leaf = [compact_encode([], leaf=True), value]
        encoded_leaf = rlp_encode(leaf)
        self.assertEqual(len(encoded_leaf), 32)
        branch = self.branch(keccak(encoded_leaf))
        root, proof = self.root_for_branch(branch)
        proof.append(as_hex(encoded_leaf))

        self.assertEqual(verify_mpt(root, self.key, proof), value)

    def test_accepts_long_hashed_child(self) -> None:
        value = b"v" * 30
        leaf = [compact_encode([], leaf=True), value]
        encoded_leaf = rlp_encode(leaf)
        self.assertEqual(len(encoded_leaf), 33)
        branch = self.branch(keccak(encoded_leaf))
        root, proof = self.root_for_branch(branch)
        proof.append(as_hex(encoded_leaf))

        self.assertEqual(verify_mpt(root, self.key, proof), value)

    def test_accepts_branch_value_with_one_child(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v"]
        branch = self.branch(leaf, value=b"prefix", include_sibling=False)
        root, proof = self.root_for_branch(branch)

        self.assertEqual(verify_mpt(root, self.key, proof), b"v")

    def test_rejects_exact_32_byte_embedded_child(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v" * 29]
        self.assertEqual(len(rlp_encode(leaf)), 32)
        branch = self.branch(leaf)
        root, proof = self.root_for_branch(branch, force_hash=True)

        with self.assertRaisesRegex(ProofError, "referenced by hash"):
            verify_mpt(root, self.key, proof)

    def test_rejects_long_embedded_child(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v" * 30]
        self.assertEqual(len(rlp_encode(leaf)), 33)
        branch = self.branch(leaf)
        root, proof = self.root_for_branch(branch, force_hash=True)

        with self.assertRaisesRegex(ProofError, "referenced by hash"):
            verify_mpt(root, self.key, proof)

    def test_rejects_short_hashed_child(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v"]
        encoded_leaf = rlp_encode(leaf)
        self.assertLess(len(encoded_leaf), 32)
        branch = self.branch(keccak(encoded_leaf))
        root, proof = self.root_for_branch(branch)
        proof.append(as_hex(encoded_leaf))

        with self.assertRaisesRegex(ProofError, "must be embedded"):
            verify_mpt(root, self.key, proof)

    def test_rejects_raw_child_encoding(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v" * 30]
        encoded_leaf = rlp_encode(leaf)
        branch = self.branch(encoded_leaf)
        root, proof = self.root_for_branch(branch, force_hash=True)

        with self.assertRaisesRegex(ProofError, "reference length"):
            verify_mpt(root, self.key, proof)

    def test_rejects_empty_extension_path(self) -> None:
        branch = self.branch([compact_encode([], leaf=True), b"v"])
        encoded_branch = rlp_encode(branch)
        root_node = [compact_encode([], leaf=False), keccak(encoded_branch)]
        encoded_root = rlp_encode(root_node)

        with self.assertRaisesRegex(ProofError, "extension path is empty"):
            verify_mpt(keccak(encoded_root), self.key, [as_hex(encoded_root), as_hex(encoded_branch)])

    def test_rejects_extension_to_leaf(self) -> None:
        leaf = [compact_encode(self.path[1:], leaf=True), b"v"]
        encoded_leaf = rlp_encode(leaf)
        root_node = [compact_encode(self.path[:1], leaf=False), keccak(encoded_leaf)]
        encoded_root = rlp_encode(root_node)

        with self.assertRaisesRegex(ProofError, "extension child must be a branch"):
            verify_mpt(keccak(encoded_root), self.key, [as_hex(encoded_root), as_hex(encoded_leaf)])

    def test_rejects_extension_to_extension(self) -> None:
        branch = self.branch([compact_encode([], leaf=True), b"v"])
        encoded_branch = rlp_encode(branch)
        inner = [compact_encode(self.path[1:-1], leaf=False), keccak(encoded_branch)]
        encoded_inner = rlp_encode(inner)
        root_node = [compact_encode(self.path[:1], leaf=False), keccak(encoded_inner)]
        encoded_root = rlp_encode(root_node)

        with self.assertRaisesRegex(ProofError, "extension child must be a branch"):
            verify_mpt(keccak(encoded_root), self.key, [as_hex(encoded_root), as_hex(encoded_inner)])

    def test_rejects_one_child_branch(self) -> None:
        leaf = [compact_encode([], leaf=True), b"v"]
        branch = self.branch(leaf, include_sibling=False)
        root, proof = self.root_for_branch(branch)

        with self.assertRaisesRegex(ProofError, "branch is not in minimal form"):
            verify_mpt(root, self.key, proof)

    def test_rejects_empty_leaf_value(self) -> None:
        root_node = [compact_encode(self.path, leaf=True), b""]
        encoded_root = rlp_encode(root_node)

        with self.assertRaisesRegex(ProofError, "leaf value is empty"):
            verify_mpt(keccak(encoded_root), self.key, [as_hex(encoded_root)])


if __name__ == "__main__":
    unittest.main()
