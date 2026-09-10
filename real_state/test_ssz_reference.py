"""SSZ reference and adversarial branch checks, without third-party dependencies.

Optional independent differential check:
  PYTHONPATH=/path/to/pinned/remerkleable python3 -m unittest real_state.test_ssz_reference
"""

import hashlib
import json
from pathlib import Path
import unittest

from real_state import ssz_reference as ssz


REPO = Path(__file__).resolve().parents[1]


class SSZReferenceTests(unittest.TestCase):
    def setUp(self):
        self.ref = ssz.make_reference(REPO / "fixtures/mainnet-0x18bd000.json")
        self.leaf = ssz.hex_bytes(self.ref["state_root"])
        self.siblings = [ssz.hex_bytes(item) for item in self.ref["siblings"]]
        self.root = ssz.hex_bytes(self.ref["ssz_root"])

    def test_snapshot_is_reproducible(self):
        self.assertEqual(self.ref, json.loads((REPO / "real_state/ssz-reference.json").read_text()))

    def test_real_root_in_hypothetical_summary(self):
        self.assertTrue(ssz.verify_state_branch(self.leaf, self.siblings, self.root))
        self.assertNotEqual(self.root, ssz.hex_bytes(self.ref["historical_block_hash"]))
        self.assertEqual(self.ref["gindex"], 41)
        self.assertEqual([(41 >> i) & 1 == 1 for i in range(5)], self.ref["sibling_on_left"])
        self.assertEqual(self.siblings[-1], bytes.fromhex("ffff03" + "00" * 29))
        self.assertFalse(self.ref["fields"][2]["synthetic"])
        self.assertEqual([item["name"] for item in self.ref["fields"] if item["synthetic"]], [
            "transactions", "receipts_root", "gas_limits", "base_fees_per_gas",
            "excess_gas", "requests_hash", "block_access_list", "slot_number",
        ])

    def test_each_mutation_rejects(self):
        flip = lambda value: bytes([value[0] ^ 1]) + value[1:]
        self.assertFalse(ssz.verify_state_branch(flip(self.leaf), self.siblings, self.root))
        self.assertFalse(ssz.verify_state_branch(self.leaf, self.siblings, flip(self.root)))
        for index in range(5):
            with self.subTest(sibling=index):
                siblings = self.siblings.copy()
                siblings[index] = flip(siblings[index])
                self.assertFalse(ssz.verify_state_branch(self.leaf, siblings, self.root))
            with self.subTest(direction=index):
                directions = list(ssz.SIBLING_ON_LEFT)
                directions[index] = not directions[index]
                self.assertNotEqual(ssz.branch_root(self.leaf, self.siblings, directions), self.root)

    def test_wrong_active_fields_rejected_even_with_matching_root(self):
        siblings = self.siblings.copy()
        siblings[-1] = ssz.active_fields_root(17)
        corresponding_root = ssz.branch_root(self.leaf, siblings, ssz.SIBLING_ON_LEFT)
        self.assertFalse(ssz.verify_state_branch(self.leaf, siblings, corresponding_root))

    def test_malformed_branch_rejects(self):
        self.assertFalse(ssz.verify_state_branch(self.leaf, self.siblings[:-1], self.root))
        self.assertFalse(ssz.verify_state_branch(self.leaf, self.siblings + [ssz.ZERO], self.root))
        self.assertFalse(ssz.verify_state_branch(self.leaf[:-1], self.siblings, self.root))
        siblings = self.siblings.copy()
        siblings[0] = siblings[0][:-1]
        self.assertFalse(ssz.verify_state_branch(self.leaf, siblings, self.root))

    def test_progressive_tree_known_small_cases(self):
        h = lambda a, b: hashlib.sha256(a + b).digest()
        a, b, c, d, e, f = [bytes([i]) * 32 for i in range(1, 7)]
        z = ssz.ZERO
        self.assertEqual(ssz.merkleize_progressive([]), z)
        self.assertEqual(ssz.merkleize_progressive([a]), h(a, z))
        self.assertEqual(ssz.merkleize_progressive([a, b]), h(a, h(h(h(b, z), h(z, z)), z)))
        self.assertEqual(ssz.merkleize_progressive([a, b, c, d, e]), h(a, h(h(h(b, c), h(d, e)), z)))
        self.assertEqual(ssz.merkleize_progressive([a, b, c, d, e, f]),
                         h(a, h(h(h(b, c), h(d, e)), h(ssz.merkleize([f], 16), z))))

    def test_optional_remerkleable_differential(self):
        try:
            from remerkleable.basic import uint64, uint256
            from remerkleable.byte_arrays import ByteList, Bytes32
            from remerkleable.progressive import ProgressiveByteList, ProgressiveContainer, ProgressiveList, subtree_fill_progressive, to_gindex_progressive
            from remerkleable.tree import RootNode
        except ImportError:
            self.skipTest("optional pinned ethereum/remerkleable checkout not on PYTHONPATH")
        for length in (0, 1, 2, 5, 6, 17, 18, 21, 22, 85, 86, 256):
            chunks = [hashlib.sha256(str(i).encode()).digest() for i in range(length)]
            with self.subTest(length=length):
                native = subtree_fill_progressive([RootNode(chunk) for chunk in chunks]).root
                self.assertEqual(ssz.merkleize_progressive(chunks), native)
        annotations = {name: Bytes32 for name in ssz.FIELD_NAMES}
        Summary = type("Summary", (ProgressiveContainer(active_fields=[1] * 18),), {"__annotations__": annotations})
        summary = Summary(**{item["name"]: ssz.hex_bytes(item["root"]) for item in self.ref["fields"]})
        self.assertEqual(summary.hash_tree_root(), self.root)
        self.assertEqual(int(to_gindex_progressive(2)[0]), 41)
        node = summary.get_backing()
        self.assertEqual(node.getter(41).root, self.leaf)
        gindex = 41
        for sibling in self.siblings:
            self.assertEqual(node.getter(gindex ^ 1).root, sibling)
            gindex >>= 1
        # Check typed roots as well as the summary's all-Bytes32 tree topology.
        GasAmounts = type("GasAmounts", (ProgressiveContainer(active_fields=[1, 1]),),
                          {"__annotations__": {"regular": uint64, "blob": uint64}})
        Fees = type("Fees", (ProgressiveContainer(active_fields=[1, 1]),),
                    {"__annotations__": {"regular": uint256, "blob": uint256}})
        typed = {"gas_limits": GasAmounts, "gas_used": GasAmounts,
                 "excess_gas": GasAmounts, "base_fees_per_gas": Fees}
        fields = {item["name"]: item for item in self.ref["fields"]}
        for name, kind in typed.items():
            self.assertEqual(kind(**fields[name]["value"]).hash_tree_root(), ssz.hex_bytes(fields[name]["root"]))
        self.assertEqual(ByteList[32](ssz.hex_bytes(fields["extra_data"]["value"])).hash_tree_root(),
                         ssz.hex_bytes(fields["extra_data"]["root"]))
        for name in ("transactions", "receipts_root", "withdrawals"):
            values = [ProgressiveByteList(ssz.hex_bytes(value)) for value in fields[name]["value"]]
            self.assertEqual(ProgressiveList[ProgressiveByteList](*values).hash_tree_root(),
                             ssz.hex_bytes(fields[name]["root"]))
        self.assertEqual(ProgressiveByteList(ssz.hex_bytes(fields["block_access_list"]["value"])).hash_tree_root(),
                         ssz.hex_bytes(fields["block_access_list"]["root"]))


if __name__ == "__main__":
    unittest.main()
