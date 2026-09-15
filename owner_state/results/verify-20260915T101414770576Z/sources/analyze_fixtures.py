#!/usr/bin/env python3
"""Validate pinned Ethereum proofs and count uniform BLAKE3 work.

The Ethereum fixtures are verified with their real Keccak MPT roots. The cost
model then replaces each byte-string hash with leanVM-b's length-bound native
hash, which absorbs 32 bytes of new data per BLAKE3 opcode. RLP parsing and
trie navigation are reported as bytes and nodes, not priced as hashes.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_utils import keccak


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "mainnet-0x18bd000.json"


class ProofError(ValueError):
    pass


def hex_bytes(value: str, size: int | None = None) -> bytes:
    raw = bytes.fromhex(value.removeprefix("0x"))
    if size is not None:
        if len(raw) > size:
            raise ProofError(f"value does not fit in {size} bytes")
        raw = raw.rjust(size, b"\x00")
    return raw


def quantity_bytes(value: str) -> bytes:
    number = int(value, 16)
    if number == 0:
        return b""
    return number.to_bytes((number.bit_length() + 7) // 8, "big")


def mapping_key(key: bytes, base_slot: int) -> bytes:
    return keccak(key.rjust(32, b"\x00") + base_slot.to_bytes(32, "big"))


def abi_address_array(value: str) -> list[str]:
    raw = hex_bytes(value)
    if len(raw) < 64:
        raise ProofError("truncated ABI address array")
    offset = int.from_bytes(raw[:32], "big")
    if offset + 32 > len(raw):
        raise ProofError("invalid ABI array offset")
    length = int.from_bytes(raw[offset : offset + 32], "big")
    start = offset + 32
    if start + 32 * length != len(raw):
        raise ProofError("invalid ABI address array length")
    return ["0x" + raw[start + 32 * i + 12 : start + 32 * (i + 1)].hex() for i in range(length)]


def rlp_encode(value: bytes | list[Any]) -> bytes:
    if isinstance(value, bytes):
        if len(value) == 1 and value[0] < 0x80:
            return value
        if len(value) < 56:
            return bytes([0x80 + len(value)]) + value
        size = len(value).to_bytes((len(value).bit_length() + 7) // 8, "big")
        return bytes([0xB7 + len(size)]) + size + value

    payload = b"".join(rlp_encode(item) for item in value)
    if len(payload) < 56:
        return bytes([0xC0 + len(payload)]) + payload
    size = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([0xF7 + len(size)]) + size + payload


def _read_length(data: bytes, pos: int, length_of_length: int) -> tuple[int, int]:
    end = pos + length_of_length
    if end > len(data) or length_of_length == 0 or data[pos] == 0:
        raise ProofError("invalid RLP length")
    return int.from_bytes(data[pos:end], "big"), end


def _rlp_decode_one(data: bytes, pos: int) -> tuple[bytes | list[Any], int]:
    if pos >= len(data):
        raise ProofError("truncated RLP")
    prefix = data[pos]
    if prefix <= 0x7F:
        return bytes([prefix]), pos + 1
    if prefix <= 0xB7:
        length = prefix - 0x80
        start, end = pos + 1, pos + 1 + length
        if end > len(data) or (length == 1 and data[start] < 0x80):
            raise ProofError("noncanonical or truncated RLP string")
        return data[start:end], end
    if prefix <= 0xBF:
        length, start = _read_length(data, pos + 1, prefix - 0xB7)
        end = start + length
        if length < 56 or end > len(data):
            raise ProofError("noncanonical or truncated long RLP string")
        return data[start:end], end
    if prefix <= 0xF7:
        length = prefix - 0xC0
        start, end = pos + 1, pos + 1 + length
    else:
        length, start = _read_length(data, pos + 1, prefix - 0xF7)
        end = start + length
        if length < 56:
            raise ProofError("noncanonical long RLP list")
    if end > len(data):
        raise ProofError("truncated RLP list")
    items: list[Any] = []
    cursor = start
    while cursor < end:
        item, cursor = _rlp_decode_one(data, cursor)
        items.append(item)
    if cursor != end:
        raise ProofError("RLP list length mismatch")
    return items, end


def rlp_decode(data: bytes) -> bytes | list[Any]:
    value, end = _rlp_decode_one(data, 0)
    if end != len(data):
        raise ProofError("trailing RLP bytes")
    return value


def nibbles(data: bytes) -> list[int]:
    out: list[int] = []
    for byte in data:
        out.extend((byte >> 4, byte & 0x0F))
    return out


def compact_path(encoded: bytes) -> tuple[bool, list[int]]:
    path = nibbles(encoded)
    if not path or path[0] > 3:
        raise ProofError("invalid compact trie path")
    is_leaf = bool(path[0] & 2)
    odd = bool(path[0] & 1)
    if odd:
        return is_leaf, path[1:]
    if len(path) < 2 or path[1] != 0:
        raise ProofError("invalid compact trie padding")
    return is_leaf, path[2:]


def validate_child_ref(reference: Any) -> None:
    if isinstance(reference, list):
        if len(rlp_encode(reference)) >= 32:
            raise ProofError("large trie child must be referenced by hash")
        validate_trie_node(reference)
        return
    if not isinstance(reference, bytes):
        raise ProofError("invalid trie child reference type")
    if len(reference) not in (0, 32):
        raise ProofError("invalid trie child reference length")


def validate_trie_node(node: Any) -> None:
    if not isinstance(node, list):
        raise ProofError("trie node is not an RLP list")
    if len(node) == 17:
        for reference in node[:16]:
            validate_child_ref(reference)
        if not isinstance(node[16], bytes):
            raise ProofError("trie branch value is not a byte string")
        populated = sum(reference != b"" for reference in node[:16])
        populated += int(node[16] != b"")
        if populated < 2:
            raise ProofError("trie branch is not in minimal form")
        return
    if len(node) != 2 or not isinstance(node[0], bytes):
        raise ProofError("invalid short trie node")
    is_leaf, segment = compact_path(node[0])
    if is_leaf:
        if not isinstance(node[1], bytes):
            raise ProofError("trie leaf value is not a byte string")
        if node[1] == b"":
            raise ProofError("trie leaf value is empty")
        return
    if not segment:
        raise ProofError("extension path is empty")
    validate_child_ref(node[1])
    if node[1] == b"":
        raise ProofError("extension child is empty")
    if isinstance(node[1], list) and len(node[1]) != 17:
        raise ProofError("extension child must be a branch")


def verify_mpt(root: bytes, key: bytes, proof_hex: list[str]) -> bytes:
    if len(root) != 32:
        raise ProofError("trie root must be 32 bytes")

    wanted = nibbles(keccak(key))
    proof = [hex_bytes(item) for item in proof_hex]
    proof_index = 0
    expected: bytes | list[Any] = root
    offset = 0
    at_root = True
    extension_child = False

    while True:
        if isinstance(expected, bytes):
            if len(expected) != 32:
                raise ProofError("invalid trie child reference length")
            if proof_index == len(proof):
                raise ProofError("proof ended before a value")
            encoded = proof[proof_index]
            index = proof_index
            proof_index += 1
            if keccak(encoded) != expected:
                raise ProofError(f"node {index} hash mismatch")
            if not at_root and len(encoded) < 32:
                raise ProofError("short trie child must be embedded")
            decoded = rlp_decode(encoded)
            node = decoded
        elif isinstance(expected, list):
            if len(rlp_encode(expected)) >= 32:
                raise ProofError("large trie child must be referenced by hash")
            node = expected
        else:
            raise ProofError("trie node is not an RLP list")

        validate_trie_node(node)
        if extension_child and len(node) != 17:
            raise ProofError("extension child must be a branch")
        extension_child = False
        at_root = False
        if len(node) == 17:
            if offset == len(wanted):
                if proof_index != len(proof):
                    raise ProofError("extra nodes after branch value")
                if node[16] == b"":
                    raise ProofError("proof is an exclusion proof")
                return node[16]
            expected = node[wanted[offset]]
            offset += 1
            if expected == b"":
                raise ProofError("proof is an exclusion proof")
            continue
        is_leaf, segment = compact_path(node[0])
        if wanted[offset : offset + len(segment)] != segment:
            raise ProofError("trie path mismatch")
        offset += len(segment)
        if is_leaf:
            if offset != len(wanted) or proof_index != len(proof):
                raise ProofError("leaf does not consume the complete key")
            return node[1]
        expected = node[1]
        extension_child = True


def account_leaf(proof: dict[str, Any]) -> bytes:
    return rlp_encode(
        [
            quantity_bytes(proof["nonce"]),
            quantity_bytes(proof["balance"]),
            hex_bytes(proof["storageHash"], 32),
            hex_bytes(proof["codeHash"], 32),
        ]
    )


def verify_account(state_root: bytes, address: str, proof: dict[str, Any]) -> None:
    found = verify_mpt(state_root, hex_bytes(address, 20), proof["accountProof"])
    if found != account_leaf(proof):
        raise ProofError("account leaf does not match RPC fields")

    storage_root = hex_bytes(proof["storageHash"], 32)
    for item in proof["storageProof"]:
        key = hex_bytes(item["key"], 32)
        found = verify_mpt(storage_root, key, item["proof"])
        if found != rlp_encode(quantity_bytes(item["value"])):
            raise ProofError(f"storage leaf mismatch for {item['key']}")


def block_header(block: dict[str, Any]) -> bytes:
    fixed = lambda name, size: hex_bytes(block[name], size)
    qty = lambda name: quantity_bytes(block[name])
    fields: list[bytes] = [
        fixed("parentHash", 32),
        fixed("sha3Uncles", 32),
        fixed("miner", 20),
        fixed("stateRoot", 32),
        fixed("transactionsRoot", 32),
        fixed("receiptsRoot", 32),
        fixed("logsBloom", 256),
        qty("difficulty"),
        qty("number"),
        qty("gasLimit"),
        qty("gasUsed"),
        qty("timestamp"),
        hex_bytes(block["extraData"]),
        fixed("mixHash", 32),
        fixed("nonce", 8),
        qty("baseFeePerGas"),
        fixed("withdrawalsRoot", 32),
        qty("blobGasUsed"),
        qty("excessBlobGas"),
        fixed("parentBeaconBlockRoot", 32),
        fixed("requestsHash", 32),
    ]
    return rlp_encode(fields)


def compression_steps(encoded: bytes) -> int:
    """leanVM-b hash_slice absorbs 32 bytes per native BLAKE3 call."""
    return math.ceil(len(encoded) / 32)


def proof_nodes(proof: dict[str, Any]) -> list[bytes]:
    nodes = [hex_bytes(node) for node in proof["accountProof"]]
    for item in proof["storageProof"]:
        nodes.extend(hex_bytes(node) for node in item["proof"])
    return nodes


def verify_recorded_storage(case: dict[str, Any]) -> None:
    proof_items = case["proof"]["storageProof"]
    if not proof_items:
        return
    keys = [case["storage_key"]] if "storage_key" in case else case["storage_keys"]
    results = (
        [case["eth_getStorageAt_result"]]
        if "eth_getStorageAt_result" in case
        else case["eth_getStorageAt_results"]
    )
    if len(keys) != len(results) or len(keys) != len(proof_items):
        raise ProofError("recorded storage observation count mismatch")
    for key, result, proof_item in zip(keys, results, proof_items):
        if hex_bytes(key, 32) != hex_bytes(proof_item["key"], 32):
            raise ProofError("recorded storage key does not match the proof")
        if int(result, 16) != int(proof_item["value"], 16):
            raise ProofError("recorded storage value does not match the proof")


@dataclass(frozen=True)
class Case:
    name: str
    proofs: tuple[dict[str, Any], ...]
    key_hashes: int
    direct_app_root: bool = False


def metrics(case: Case) -> dict[str, int | str]:
    path_nodes = [node for proof in case.proofs for node in proof_nodes(proof)]
    unique_nodes = list(dict.fromkeys(path_nodes))
    path_compressions = sum(compression_steps(node) for node in path_nodes if len(node) >= 32)
    unique_compressions = sum(compression_steps(node) for node in unique_nodes if len(node) >= 32)
    return {
        "case": case.name,
        "accounts": len(case.proofs),
        "storage_slots": sum(len(proof["storageProof"]) for proof in case.proofs),
        "path_nodes": len(path_nodes),
        "path_bytes": sum(map(len, path_nodes)),
        "path_compressions": path_compressions,
        "unique_nodes": len(unique_nodes),
        "unique_bytes": sum(map(len, unique_nodes)),
        "unique_compressions": unique_compressions,
        "saved_compressions": path_compressions - unique_compressions,
        "key_hashes": case.key_hashes,
    }


def expect_failure(action: Any, label: str) -> None:
    try:
        action()
    except ProofError:
        return
    raise AssertionError(f"negative test did not fail: {label}")


def main() -> None:
    fixture = json.loads(FIXTURE.read_text())
    block = fixture["block"]
    state_root = hex_bytes(block["stateRoot"], 32)
    cases = fixture["cases"]

    named_proofs: dict[str, dict[str, Any]] = {}
    for name, item in cases.items():
        proof = item["proof"]
        address = item.get("address", item.get("contract"))
        verify_account(state_root, address, proof)
        verify_recorded_storage(item)
        named_proofs[name] = proof

    header = block_header(block)
    if keccak(header) != hex_bytes(block["hash"], 32):
        raise ProofError("RLP header does not reproduce the block hash")

    if cases["weth_balance"]["eth_call_result"] != cases["weth_balance"]["eth_getStorageAt_result"]:
        raise ProofError("WETH balanceOf does not match the selected slot")
    weth_case = cases["weth_balance"]
    expected_weth_key = mapping_key(hex_bytes(weth_case["holder"], 20), 3)
    if expected_weth_key != hex_bytes(weth_case["storage_key"], 32):
        raise ProofError("WETH balance mapping key is wrong")

    bayc = cases["bayc_token_100_owner"]
    if int(bayc["eth_getStorageAt_results"][0], 16) != 10_000:
        raise ProofError("BAYC entries array does not have the expected length")
    if int(bayc["eth_getStorageAt_results"][1], 16) != 101:
        raise ProofError("BAYC index mapping does not point to entry 100")
    if bayc["eth_call_result"] != bayc["eth_getStorageAt_results"][2]:
        raise ProofError("BAYC ownerOf does not match the selected owner slot")
    token_id = int(bayc["token_id"], 16)
    expected_index_key = mapping_key(token_id.to_bytes(32, "big"), 3)
    entries_base = int.from_bytes(keccak((2).to_bytes(32, "big")), "big")
    entry_index = int(bayc["eth_getStorageAt_results"][1], 16) - 1
    expected_owner_key = ((entries_base + 2 * entry_index + 1) % (1 << 256)).to_bytes(32, "big")
    if hex_bytes(bayc["storage_keys"][0], 32) != (2).to_bytes(32, "big"):
        raise ProofError("BAYC array length slot is wrong")
    if hex_bytes(bayc["storage_keys"][1], 32) != expected_index_key:
        raise ProofError("BAYC token index mapping key is wrong")
    if hex_bytes(bayc["storage_keys"][2], 32) != expected_owner_key:
        raise ProofError("BAYC owner entry slot is wrong")

    combined_holder = cases["native_eth_account"]["address"].lower()
    if weth_case["holder"].lower() != combined_holder or bayc["holder"].lower() != combined_holder:
        raise ProofError("combined ETH, WETH, and BAYC cases do not use the same holder")
    returned_bayc_owner = "0x" + hex_bytes(bayc["eth_call_result"], 32)[12:].hex()
    if returned_bayc_owner.lower() != combined_holder:
        raise ProofError("BAYC owner value does not match the combined case holder")

    safe = cases["safe_authorization"]
    owners = [owner.lower() for owner in abi_address_array(safe["getOwners_result"])]
    if safe["owner"].lower() not in owners:
        raise ProofError("Safe getOwners does not contain the selected owner")
    if int(safe["getThreshold_result"], 16) != 1:
        raise ProofError("Safe threshold is not one")
    if int(safe["eth_getStorageAt_results"][1], 16) != 1 or int(safe["eth_getStorageAt_results"][2], 16) != 1:
        raise ProofError("Safe owner link or threshold storage does not match its getters")
    if int(safe["eth_getStorageAt_results"][0], 16) != int("29fcb43b46531bca003ddc8fcb67ffe91900c762", 16):
        raise ProofError("Safe singleton storage is not the expected v1.4.1 singleton")
    expected_owner_key = mapping_key(hex_bytes(safe["owner"], 20), 2)
    if hex_bytes(safe["storage_keys"][0], 32) != (0).to_bytes(32, "big"):
        raise ProofError("Safe singleton slot is wrong")
    if hex_bytes(safe["storage_keys"][1], 32) != expected_owner_key:
        raise ProofError("Safe owner mapping key is wrong")
    if hex_bytes(safe["storage_keys"][2], 32) != (4).to_bytes(32, "big"):
        raise ProofError("Safe threshold slot is wrong")

    tornado = cases["tornado_recent_root"]
    current_index = int(tornado["currentRootIndex_result"], 16)
    if tornado["root_history_size"] != 100:
        raise ProofError("Tornado root history size is not 100")
    if current_index != 40 or int(tornado["eth_getStorageAt_results"][0], 16) & 0xFFFFFFFF != current_index:
        raise ProofError("Tornado current root index does not match packed storage")
    if tornado["getLastRoot_result"] != tornado["eth_getStorageAt_results"][1]:
        raise ProofError("Tornado getLastRoot does not match the selected roots entry")
    if int(tornado["storage_keys"][0], 16) != 3 or int(tornado["storage_keys"][1], 16) != 4 + current_index:
        raise ProofError("Tornado index or fixed roots array slot is wrong")

    first = named_proofs["weth_balance"]
    expect_failure(
        lambda: verify_account(bytes([state_root[0] ^ 1]) + state_root[1:], cases["weth_balance"]["contract"], first),
        "changed state root",
    )
    expect_failure(
        lambda: verify_account(state_root, "0x" + "00" * 20, first),
        "changed account key",
    )
    negative_tests = 2
    for case_name, item in cases.items():
        address = item.get("address", item.get("contract"))
        original = item["proof"]
        locations = [("account", 0, i) for i in range(len(original["accountProof"]))]
        for storage_index, storage in enumerate(original["storageProof"]):
            locations.extend(("storage", storage_index, i) for i in range(len(storage["proof"])))
        for kind, storage_index, node_index in locations:
            changed = json.loads(json.dumps(original))
            target = (
                changed["accountProof"]
                if kind == "account"
                else changed["storageProof"][storage_index]["proof"]
            )
            raw = bytearray(hex_bytes(target[node_index]))
            raw[-1] ^= 1
            target[node_index] = "0x" + raw.hex()
            expect_failure(
                lambda changed=changed, address=address: verify_account(state_root, address, changed),
                f"changed {case_name} {kind} node {node_index}",
            )
            negative_tests += 1

    eoa = named_proofs["plain_eoa"]
    holder = named_proofs["native_eth_account"]
    weth = named_proofs["weth_balance"]
    nft = named_proofs["bayc_token_100_owner"]
    safe_proof = named_proofs["safe_authorization"]
    account_storage_word = {
        **safe_proof,
        "storageProof": safe_proof["storageProof"][:1],
    }
    tornado_proof = named_proofs["tornado_recent_root"]
    sweep = [
        Case("plain_eoa", (eoa,), 1),
        Case("account_storage_word", (account_storage_word,), 2),
        Case("weth_balance", (weth,), 3),
        Case("bayc_token_100_owner", (nft,), 5),
        Case("safe_authorization", (safe_proof,), 5),
        Case("tornado_recent_root", (tornado_proof,), 3, True),
        Case("weth_and_bayc", (weth, nft), 8),
        Case("native_weth_and_bayc", (holder, weth, nft), 9),
    ]

    rlp_bridge = compression_steps(header)
    # EIP-7807 places state_root at field index 2. Its progressive tree path has
    # one field 0 sibling, one recursive tail sibling, and two siblings inside
    # the four-leaf field 1 to 4 subtree. EIP-7495 adds the active fields mix-in.
    ssz_bridge = 1 + 1 + 2 + 1
    rows: list[dict[str, int | str]] = []
    for case in sweep:
        row = metrics(case)
        state = int(row["unique_compressions"]) + int(row["key_hashes"])
        row.update(
            {
                "direct_app_anchor_hashes": 0 if case.direct_app_root else "N/A",
                "direct_state_anchor_hashes": state,
                "ssz_block_anchor_hashes": state + ssz_bridge,
                "rlp_block_anchor_hashes": state + rlp_bridge,
            }
        )
        rows.append(row)

    columns = list(rows[0].keys())
    writer = csv.DictWriter(sys.stdout, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    print(
        f"VALIDATION block={block['number']} hash={block['hash']} state_root={block['stateRoot']} "
        f"rlp_header_bytes={len(header)} rlp_bridge_hashes={rlp_bridge} ssz_bridge_hashes={ssz_bridge} "
        f"proofs={len(named_proofs)} negative_tests={negative_tests}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
