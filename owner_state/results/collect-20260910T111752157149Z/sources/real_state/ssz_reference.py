#!/usr/bin/env python3
"""Reference SSZ state-root inclusion proof for the EIP-7807 proposal.

This constructs a hypothetical summary, not a historical block conversion.
The original account/storage state root is real. Fields unavailable in the
fixture are explicitly synthetic; their provenance is part of the output.
Only Python's native hashlib SHA-256 is used by this independent reference.
"""

import argparse
import hashlib
import json
from pathlib import Path


ZERO = bytes(32)
EIPS_COMMIT = "d2a64c2d4cc44f2f507577d0ebfb110dcc21d358"
REMERKLEABLE_COMMIT = "2f0baeef0082d4278acaef7d822deb7009d7db7e"
FIELD_NAMES = (
    "parent_hash", "miner", "state_root", "transactions", "receipts_root",
    "number", "gas_limits", "gas_used", "timestamp", "extra_data", "mix_hash",
    "base_fees_per_gas", "withdrawals", "excess_gas", "parent_beacon_block_root",
    "requests_hash", "block_access_list", "slot_number",
)
STATE_ROOT_GINDEX = 41
SIBLING_ON_LEFT = (True, False, False, True, False)


def hash_pair(left, right):
    if len(left) != 32 or len(right) != 32:
        raise ValueError("SSZ pair children must each be 32 bytes")
    return hashlib.sha256(left + right).digest()


def hex_bytes(value, size=None):
    data = bytes.fromhex(value.removeprefix("0x"))
    if size is not None and len(data) != size:
        raise ValueError(f"expected {size} bytes, got {len(data)}")
    return data


def hex_root(value):
    return "0x" + value.hex()


def uint_root(value, bits=64):
    value = int(value, 16) if isinstance(value, str) else value
    if not 0 <= value < 1 << bits:
        raise ValueError(f"out of range for uint{bits}")
    return value.to_bytes(bits // 8, "little").ljust(32, b"\0")


def merkleize(chunks, limit=None):
    """Conventional SSZ binary tree, with zero *chunks* as padding."""
    limit = len(chunks) if limit is None else limit
    if len(chunks) > limit or limit < 0 or any(len(c) != 32 for c in chunks):
        raise ValueError("invalid SSZ chunks or limit")
    capacity = 1 << max(0, (max(1, limit) - 1).bit_length())
    level = list(chunks) + [ZERO] * (capacity - len(chunks))
    while len(level) > 1:
        level = [hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkleize_progressive(chunks, num_leaves=1):
    """EIP-7916: successive binary subtrees have 1, 4, 16, ... leaves."""
    if not chunks:
        return ZERO
    return hash_pair(
        merkleize(chunks[:num_leaves], num_leaves),
        merkleize_progressive(chunks[num_leaves:], num_leaves * 4),
    )


def active_fields_root(count):
    if not 1 <= count <= 256:
        raise ValueError("invalid all-active progressive container field count")
    return ((1 << count) - 1).to_bytes(32, "little")


def container_root(field_roots):
    return hash_pair(merkleize_progressive(field_roots), active_fields_root(len(field_roots)))


def progressive_bytes_root(value):
    chunks = [value[i:i + 32].ljust(32, b"\0") for i in range(0, len(value), 32)]
    return hash_pair(merkleize_progressive(chunks), uint_root(len(value), 256))


def progressive_list_root(element_roots):
    return hash_pair(merkleize_progressive(element_roots), uint_root(len(element_roots), 256))


def byte_list32_root(value):
    if len(value) > 32:
        raise ValueError("extra_data exceeds ByteList[32]")
    return hash_pair(value.ljust(32, b"\0"), uint_root(len(value), 256))


def _rlp(value):
    """Canonical RLP encoder used only to form known withdrawal bytes."""
    if isinstance(value, list):
        payload = b"".join(_rlp(item) for item in value)
        short, long = 0xc0, 0xf7
    else:
        payload = value
        if len(payload) == 1 and payload[0] < 0x80:
            return payload
        short, long = 0x80, 0xb7
    if len(payload) < 56:
        return bytes([short + len(payload)]) + payload
    size = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([long + len(size)]) + size + payload


def _rlp_uint(value):
    number = int(value, 16)
    return number.to_bytes((number.bit_length() + 7) // 8, "big")


def _withdrawal_bytes(withdrawal):
    return _rlp([
        _rlp_uint(withdrawal["index"]), _rlp_uint(withdrawal["validatorIndex"]),
        hex_bytes(withdrawal["address"], 20), _rlp_uint(withdrawal["amount"]),
    ])


def make_reference(fixture_path):
    fixture_path = Path(fixture_path)
    fixture_bytes = fixture_path.read_bytes()
    block = json.loads(fixture_bytes)["block"]
    fields = []

    def add(name, root, provenance, value=None, synthetic=False):
        if name != FIELD_NAMES[len(fields)]:
            raise ValueError("field order does not match EIP-7807")
        fields.append({"index": len(fields), "name": name, "root": hex_root(root),
                       "provenance": provenance, "synthetic": synthetic, "value": value})

    def copied(name, rpc_name, size=32):
        value = block[rpc_name]
        add(name, hex_bytes(value, size).ljust(32, b"\0"), f"fixture block.{rpc_name}", value)

    def integer(name, rpc_name):
        add(name, uint_root(block[rpc_name]), f"fixture block.{rpc_name}", int(block[rpc_name], 16))

    copied("parent_hash", "parentHash")
    copied("miner", "miner", 20)
    copied("state_root", "stateRoot")
    add("transactions", progressive_list_root([]), "synthetic empty transaction list; fixture lacks transaction bytes", [], True)
    add("receipts_root", progressive_list_root([]), "synthetic empty receipt list; the historical Keccak receiptsRoot is not an SSZ root", [], True)
    integer("number", "number")
    add("gas_limits", container_root([uint_root(block["gasLimit"]), uint_root(0)]),
        "regular copied from fixture block.gasLimit; blob limit synthetic zero",
        {"regular": int(block["gasLimit"], 16), "blob": 0}, True)
    add("gas_used", container_root([uint_root(block["gasUsed"]), uint_root(block["blobGasUsed"])]),
        "fixture block.gasUsed and block.blobGasUsed",
        {"regular": int(block["gasUsed"], 16), "blob": int(block["blobGasUsed"], 16)})
    integer("timestamp", "timestamp")
    add("extra_data", byte_list32_root(hex_bytes(block["extraData"])), "fixture block.extraData; ByteList[32]", block["extraData"])
    copied("mix_hash", "mixHash")
    add("base_fees_per_gas", container_root([uint_root(block["baseFeePerGas"], 256), uint_root(0, 256)]),
        "regular copied from fixture block.baseFeePerGas; blob fee synthetic zero",
        {"regular": int(block["baseFeePerGas"], 16), "blob": 0}, True)
    withdrawals = [_withdrawal_bytes(item) for item in block["withdrawals"]]
    add("withdrawals", progressive_list_root([progressive_bytes_root(item) for item in withdrawals]),
        "fixture block.withdrawals; each canonical RLP withdrawal is an EIP-7916 ProgressiveByteList",
        [hex_root(item) for item in withdrawals])
    add("excess_gas", container_root([uint_root(0), uint_root(block["excessBlobGas"])]),
        "regular synthetic zero; blob copied from fixture block.excessBlobGas",
        {"regular": 0, "blob": int(block["excessBlobGas"], 16)}, True)
    copied("parent_beacon_block_root", "parentBeaconBlockRoot")
    add("requests_hash", ZERO, "synthetic pinned zero Root; not a conversion of the historical requestsHash and not asserted to be ExecutionRequests.hash_tree_root()", hex_root(ZERO), True)
    add("block_access_list", progressive_bytes_root(b"\xc0"),
        "synthetic RLP empty list; no historical block access list in fixture", "0xc0", True)
    add("slot_number", uint_root(0), "synthetic zero slot; no slot_number in execution fixture", 0, True)

    roots = [hex_bytes(field["root"], 32) for field in fields]
    # Independent of recursive merkleize_progressive: manually follow field #2
    # through the 4-leaf subtree, its continuation, field #0, then active bits.
    tail = hash_pair(merkleize(roots[5:], 16), ZERO)
    siblings = [roots[1], hash_pair(roots[3], roots[4]), tail, roots[0], active_fields_root(18)]
    root = container_root(roots)
    if branch_root(roots[2], siblings, SIBLING_ON_LEFT) != root:
        raise AssertionError("manual state-root branch disagrees with full progressive tree")
    return {
        "schema": "eip-7807-hypothetical-state-root-branch-v1",
        "description": "Real mainnet state root in a hypothetical EIP-7807 summary with explicit synthetic unrelated fields. Not the historical mainnet block's SSZ hash and not a validated execution block.",
        "fixture": fixture_path.name,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "historical_block_hash": block["hash"],
        "state_root": block["stateRoot"],
        "ssz_root": hex_root(root),
        "gindex": STATE_ROOT_GINDEX,
        "siblings": [hex_root(item) for item in siblings],
        "sibling_on_left": list(SIBLING_ON_LEFT),
        "active_fields": [1] * 18,
        "active_fields_chunk": hex_root(active_fields_root(18)),
        "sha256_pair_hashes": 5,
        "sha256_compression_blocks": 10,
        "specifications": {f"eip-{number}": f"https://github.com/ethereum/EIPs/blob/{EIPS_COMMIT}/EIPS/eip-{number}.md" for number in (7807, 7495, 7916)},
        "independent_implementation": f"https://github.com/ethereum/remerkleable/tree/{REMERKLEABLE_COMMIT}",
        "fields": fields,
    }


def branch_root(leaf, siblings, sibling_on_left):
    if len(leaf) != 32 or len(siblings) != len(sibling_on_left):
        raise ValueError("invalid branch")
    root = leaf
    for sibling, on_left in zip(siblings, sibling_on_left):
        if type(on_left) is not bool:
            raise ValueError("branch directions must be booleans")
        root = hash_pair(sibling, root) if on_left else hash_pair(root, sibling)
    return root


def verify_state_branch(state_root, siblings, ssz_root):
    if len(siblings) != 5:
        return False
    if siblings[-1] != active_fields_root(18):
        return False
    try:
        return branch_root(state_root, siblings, SIBLING_ON_LEFT) == ssz_root
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=Path(__file__).resolve().parents[1] / "fixtures/mainnet-0x18bd000.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contents = json.dumps(make_reference(args.fixture), indent=2) + "\n"
    if args.output:
        args.output.write_text(contents)
    else:
        print(contents, end="")


if __name__ == "__main__":
    main()
