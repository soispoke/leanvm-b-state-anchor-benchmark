"""Boolean Keccak-256 and SHA-256 circuits, including byte padding.

Bytes and words are lists of wires, least significant bit first. Only their
public lengths control Python execution; input wire values are never read.
The backend supplies zero/one wire IDs and xor(a, b), and_(a, b) gates.

Algorithms: https://keccak.team/keccak_specs_summary.html (Keccak-f[1600]);
https://doi.org/10.6028/NIST.FIPS.180-4 (SHA-256, sections 4.1.2 and 6.2).
Ethereum Keccak uses the original 0x01 suffix, not SHA3's 0x06 suffix.
"""

from typing import Protocol

Byte = list[int]
Word = list[int]


class Circuit(Protocol):
    zero: int
    one: int

    def xor(self, a: int, b: int) -> int: ...

    def and_(self, a: int, b: int) -> int: ...


def _const(c: Circuit, value: int, width: int) -> Word:
    return [c.one if (value >> bit) & 1 else c.zero for bit in range(width)]


def _xor(c: Circuit, a: Word, b: Word) -> Word:
    return [c.xor(x, y) for x, y in zip(a, b)]


def _xor3(c: Circuit, a: Word, b: Word, d: Word) -> Word:
    return [c.xor(c.xor(x, y), z) for x, y, z in zip(a, b, d)]


def _rol(a: Word, amount: int) -> Word:
    amount %= len(a)
    return a[-amount:] + a[:-amount] if amount else a[:]


_KECCAK_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
# Indexed [x][y], matching A[x + 5*y].
_KECCAK_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _keccak_f(c: Circuit, a: list[Word]) -> list[Word]:
    for rc in _KECCAK_RC:
        columns = [
            _xor(c, _xor(c, _xor(c, _xor(c, a[x], a[x + 5]),
                                    a[x + 10]), a[x + 15]), a[x + 20])
            for x in range(5)
        ]
        delta = [_xor(c, columns[(x - 1) % 5],
                      _rol(columns[(x + 1) % 5], 1)) for x in range(5)]
        b = [None] * 25
        for y in range(5):
            for x in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(
                    _xor(c, a[x + 5 * y], delta[x]), _KECCAK_ROT[x][y])
        a = [
            [c.xor(left, c.and_(c.xor(middle, c.one), right))
             for left, middle, right in zip(
                 b[x + 5 * y], b[(x + 1) % 5 + 5 * y],
                 b[(x + 2) % 5 + 5 * y])]
            for y in range(5) for x in range(5)
        ]
        # XOR with known zero bits is just a wire copy.
        a[0] = [c.xor(bit, c.one) if (rc >> i) & 1 else bit
                for i, bit in enumerate(a[0])]
    return a


def keccak256(c: Circuit, data: list[Byte]) -> list[Byte]:
    """Ethereum's byte-oriented Keccak-256, with a public fixed input length."""
    if any(len(byte) != 8 for byte in data):
        raise ValueError("each input byte must contain eight bit wires")
    padding = 136 - len(data) % 136
    suffix = [0x81] if padding == 1 else [0x01] + [0] * (padding - 2) + [0x80]
    padded = list(data) + [_const(c, value, 8) for value in suffix]
    a = [[c.zero] * 64 for _ in range(25)]
    for offset in range(0, len(padded), 136):
        for lane in range(17):
            start = offset + 8 * lane
            bits = [bit for byte in padded[start:start + 8] for bit in byte]
            a[lane] = _xor(c, a[lane], bits)
        a = _keccak_f(c, a)
    output = [bit for lane in a[:4] for bit in lane]
    return [output[i:i + 8] for i in range(0, 256, 8)]


_SHA256_IV = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)
_SHA256_K = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5,
    0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC,
    0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7,
    0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3,
    0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5,
    0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)


def _ror(a: Word, amount: int) -> Word:
    return a[amount:] + a[:amount]


def _shr(c: Circuit, a: Word, amount: int) -> Word:
    return a[amount:] + [c.zero] * amount


def _add(c: Circuit, a: Word, b: Word) -> Word:
    """Ripple-carry addition modulo 2**32 using only XOR and AND gates."""
    output = [c.xor(a[0], b[0])]
    carry = c.and_(a[0], b[0])
    for i in range(1, 32):
        different = c.xor(a[i], b[i])
        output.append(c.xor(different, carry))
        if i != 31:
            carry = c.xor(c.and_(a[i], b[i]), c.and_(different, carry))
    return output


def _sum(c: Circuit, *words: Word) -> Word:
    result = words[0]
    for word in words[1:]:
        result = _add(c, result, word)
    return result


def sha256(c: Circuit, data: list[Byte]) -> list[Byte]:
    """SHA-256 including its length trailer, with a public fixed input length."""
    if any(len(byte) != 8 for byte in data):
        raise ValueError("each input byte must contain eight bit wires")
    bit_length = len(data) * 8
    if bit_length >= 1 << 64:
        raise ValueError("SHA-256 input length must be below 2**64 bits")
    suffix = [0x80] + [0] * ((55 - len(data)) % 64)
    suffix += list(bit_length.to_bytes(8, "big"))
    padded = list(data) + [_const(c, value, 8) for value in suffix]
    state = [_const(c, value, 32) for value in _SHA256_IV]
    constants = [_const(c, value, 32) for value in _SHA256_K]
    for offset in range(0, len(padded), 64):
        schedule = [
            [bit for byte in reversed(padded[i:i + 4]) for bit in byte]
            for i in range(offset, offset + 64, 4)
        ]
        for i in range(16, 64):
            x, y = schedule[i - 15], schedule[i - 2]
            small0 = _xor3(c, _ror(x, 7), _ror(x, 18), _shr(c, x, 3))
            small1 = _xor3(c, _ror(y, 17), _ror(y, 19), _shr(c, y, 10))
            schedule.append(_sum(c, schedule[i - 16], small0,
                                 schedule[i - 7], small1))
        a, b, c_word, d, e, f, g, h = state
        for i in range(64):
            big1 = _xor3(c, _ror(e, 6), _ror(e, 11), _ror(e, 25))
            choice = [c.xor(z, c.and_(x, c.xor(y, z)))
                      for x, y, z in zip(e, f, g)]
            temp1 = _sum(c, h, big1, choice, constants[i], schedule[i])
            big0 = _xor3(c, _ror(a, 2), _ror(a, 13), _ror(a, 22))
            majority = [c.xor(c.and_(x, y), c.and_(z, c.xor(x, y)))
                        for x, y, z in zip(a, b, c_word)]
            temp2 = _add(c, big0, majority)
            a, b, c_word, d, e, f, g, h = (
                _add(c, temp1, temp2), a, b, c_word, _add(c, d, temp1), e, f, g)
        state = [_add(c, old, new)
                 for old, new in zip(state, (a, b, c_word, d, e, f, g, h))]
    return [word[i:i + 8] for word in state for i in (24, 16, 8, 0)]
