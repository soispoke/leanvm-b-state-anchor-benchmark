"""Hash candidates using only the pinned VM's existing Boolean gates.

Keccak is the original circuit with compiler-local expression reuse. SHA-256
also replaces each interior carry with a one-multiplication Boolean identity.
This trades one multiplication for one XOR; it does not promise fewer total
instructions or smaller padded tables. Input values never direct compilation.
"""

from contextlib import nullcontext

from real_state.hashes import (
    Byte, Circuit, Word, _SHA256_IV, _SHA256_K, _const, _ror, _shr, _xor3,
    keccak256 as _keccak256, sha256 as _sha256_ripple,
)


def _scope(c: Circuit, name: str, length: int):
    factory = getattr(c, 'hash_scope', None)
    return factory(name, length) if factory is not None else nullcontext()


def _full_adder(c: Circuit, a: int, b: int, carry: int) -> tuple[int, int]:
    """Return sum and carry: carry' = carry ^ ((a^carry)&(b^carry))."""
    left = c.xor(a, carry)
    right = c.xor(b, carry)
    return c.xor(left, b), c.xor(carry, c.and_(left, right))


def _add(c: Circuit, a: Word, b: Word) -> Word:
    """32-bit addition modulo 2**32; discard the final carry explicitly."""
    if len(a) != 32 or len(b) != 32:
        raise ValueError('addition expects two 32-bit words')
    output = [c.xor(a[0], b[0])]
    carry = c.and_(a[0], b[0])
    for i in range(1, 31):
        bit, carry = _full_adder(c, a[i], b[i], carry)
        output.append(bit)
    output.append(c.xor(c.xor(a[31], b[31]), carry))
    return output


def _full_adder_hybrid(c: Circuit, a: int, b: int, carry: int) -> tuple[int, int]:
    # These are public wire identities, never the underlying witness values.
    if any(wire == c.zero or wire == c.one for wire in (a, b, carry)):
        different = c.xor(a, b)
        return (c.xor(different, carry),
                c.xor(c.and_(a, b), c.and_(different, carry)))
    return _full_adder(c, a, b, carry)


def _add_hybrid(c: Circuit, a: Word, b: Word) -> Word:
    """Keep the original carry when public constants allow more folding."""
    if len(a) != 32 or len(b) != 32:
        raise ValueError('addition expects two 32-bit words')
    output = [c.xor(a[0], b[0])]
    carry = c.and_(a[0], b[0])
    for i in range(1, 31):
        bit, carry = _full_adder_hybrid(c, a[i], b[i], carry)
        output.append(bit)
    output.append(c.xor(c.xor(a[31], b[31]), carry))
    return output


def _sum(c: Circuit, *words: Word, adder=_add) -> Word:
    result = words[0]
    for word in words[1:]:
        result = adder(c, result, word)
    return result


def keccak256(c: Circuit, data: list[Byte]) -> list[Byte]:
    """Unchanged Ethereum Keccak-256, with optional per-hash CSE scope."""
    with _scope(c, 'keccak256', len(data)):
        return _keccak256(c, data)


def sha256_ripple(c: Circuit, data: list[Byte]) -> list[Byte]:
    """Original two-multiplication carry, with the same CSE scope."""
    with _scope(c, 'sha256', len(data)):
        return _sha256_ripple(c, data)


def sha256(c: Circuit, data: list[Byte]) -> list[Byte]:
    """SHA-256 with one-MUL carry, retaining all padding and round checks."""
    with _scope(c, 'sha256', len(data)):
        return _sha256_one_mul(c, data)


def sha256_hybrid(c: Circuit, data: list[Byte]) -> list[Byte]:
    """One-MUL carry only when all three input wires are nonconstant."""
    with _scope(c, 'sha256', len(data)):
        return _sha256_one_mul(c, data, adder=_add_hybrid)


def _sha256_one_mul(c: Circuit, data: list[Byte], adder=_add) -> list[Byte]:
    if any(len(byte) != 8 for byte in data):
        raise ValueError('each input byte must contain eight bit wires')
    bit_length = len(data) * 8
    if bit_length >= 1 << 64:
        raise ValueError('SHA-256 input length must be below 2**64 bits')
    suffix = [0x80] + [0] * ((55 - len(data)) % 64)
    suffix += list(bit_length.to_bytes(8, 'big'))
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
                                 schedule[i - 7], small1, adder=adder))
        a, b, c_word, d, e, f, g, h = state
        for i in range(64):
            big1 = _xor3(c, _ror(e, 6), _ror(e, 11), _ror(e, 25))
            choice = [c.xor(z, c.and_(x, c.xor(y, z)))
                      for x, y, z in zip(e, f, g)]
            temp1 = _sum(c, h, big1, choice, constants[i], schedule[i], adder=adder)
            big0 = _xor3(c, _ror(a, 2), _ror(a, 13), _ror(a, 22))
            majority = [c.xor(c.and_(x, y), c.and_(z, c.xor(x, y)))
                        for x, y, z in zip(a, b, c_word)]
            temp2 = adder(c, big0, majority)
            a, b, c_word, d, e, f, g, h = (
                adder(c, temp1, temp2), a, b, c_word, adder(c, d, temp1), e, f, g)
        state = [adder(c, old, new)
                 for old, new in zip(state, (a, b, c_word, d, e, f, g, h))]
    return [word[i:i + 8] for word in state for i in (24, 16, 8, 0)]
