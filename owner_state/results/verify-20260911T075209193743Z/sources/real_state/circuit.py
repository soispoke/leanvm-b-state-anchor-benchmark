"""Straight-line Boolean verification compiled to ordinary leanVM-b opcodes.

Wire IDs are write-once memory cells. Inputs remain witnesses; compile-time
simplification uses only public constants and identities, never witness values.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path


class Circuit:
    def __init__(self):
        self.check_witness = True
        self.zero, self.one = 2, 3
        self.values = [0, 0, 0, 1]
        self.ops = bytearray()
        self.counts = [0, 0, 0]
        self.inputs = []
        self.constants = {0: self.zero, 1: self.one}
        self._set(self.zero, 0)
        self._set(self.one, 1)

    def _set(self, out, value):
        self.ops.extend(struct.pack('<BI', 2, out) + value.to_bytes(16, 'little'))
        self.counts[2] += 1

    def _gate(self, op, a, b, out):
        self.ops.extend(struct.pack('<BIII', op, a, b, out))
        self.counts[op] += 1

    def _wire(self, value):
        wire = len(self.values)
        self.values.append(value)
        return wire

    def const(self, value):
        if value not in self.constants:
            self.constants[value] = self._wire(value)
            self._set(self.constants[value], value)
        return self.constants[value]

    def xor(self, a, b):
        if a == b:
            return self.zero
        if a == self.zero:
            return b
        if b == self.zero:
            return a
        out = self._wire(self.values[a] ^ self.values[b])
        self._gate(0, a, b, out)
        return out

    def and_(self, a, b):
        if a == self.zero or b == self.zero:
            return self.zero
        if a == self.one:
            return b
        if b == self.one or a == b:
            return a
        out = self._wire(self.values[a] & self.values[b])
        self._gate(1, a, b, out)
        return out

    def not_(self, a):
        return self.xor(a, self.one)

    def or_(self, a, b):
        return self.xor(self.xor(a, b), self.and_(a, b))

    def select(self, selector, yes, no):
        return self.xor(no, self.and_(selector, self.xor(yes, no)))

    def assert_eq(self, a, b):
        # Write into the established zero cell: mismatches cannot satisfy the VM.
        self._gate(0, a, b, self.zero)
        if self.check_witness and self.values[a] != self.values[b]:
            raise ValueError(f'honest witness violates equality at cells {a}, {b}')

    def assert_bytes(self, a, b):
        if len(a) != len(b):
            raise ValueError(f'byte lengths differ: {len(a)}, {len(b)}')
        for x, y in zip(a, b):
            for xb, yb in zip(x, y):
                self.assert_eq(xb, yb)

    def literal(self, data):
        return [[self.one if byte >> bit & 1 else self.zero for bit in range(8)]
                for byte in data]

    def witness(self, name, data):
        if any(entry['name'] == name for entry in self.inputs):
            raise ValueError(f'duplicate witness name {name}')
        base = len(self.values)
        bits = [byte >> bit & 1 for byte in data for bit in range(8)]
        self.values.extend(bits)
        self.inputs.append({'name': name, 'base': base, 'length': len(bits), 'data': bytes(data)})
        for wire in range(base, base + len(bits)):
            # x*x=x constrains a field element to {0,1} even for malicious hints.
            self._gate(1, wire, wire, wire)
        return [list(range(base + 8*i, base + 8*i + 8)) for i in range(len(data))]

    def nonzero(self, byte):
        out = self.zero
        for bit in byte:
            out = self.or_(out, bit)
        self.assert_eq(out, self.one)

    def pack_public(self, digest):
        """Bind all 256 digest bits to the VM's two public F128 cells."""
        if len(digest) != 32:
            raise ValueError('public digest must be32 bytes')
        for limb in range(2):
            acc = self.zero
            for i, byte in enumerate(digest[16*limb:16*limb+16]):
                for j, bit in enumerate(byte):
                    scale = self.const(1 << (8*i+j))
                    product = self._wire(self.values[bit] * self.values[scale])
                    self._gate(1, bit, scale, product)
                    acc = self.xor(acc, product)
            self.values[limb] = self.values[acc]
            self._gate(0, acc, self.zero, limb)

    def read_bytes(self, data):
        return bytes(sum(self.values[wire] << i for i, wire in enumerate(byte)) for byte in data)

    def export(self, directory: Path, metadata: dict):
        directory.mkdir(parents=True, exist_ok=True)
        # Header: magic, memory cells, instruction count; variable-size op records.
        (directory/'program.bin').write_bytes(b'LVMSTATE' + struct.pack('<II', len(self.values), sum(self.counts)) + self.ops)
        witness = bytearray(struct.pack('<I', len(self.inputs)))
        for entry in self.inputs:
            witness.extend(struct.pack('<II', entry['base'], entry['length']))
            for byte in entry['data']:
                for bit in range(8):
                    witness.extend((byte >> bit & 1).to_bytes(16, 'little'))
        (directory/'witness.bin').write_bytes(witness)
        (directory/'public.bin').write_bytes(b''.join(value.to_bytes(16,'little') for value in self.values[:2]))
        meta = dict(metadata, memory_cells=len(self.values), op_counts=dict(zip(('xor','mul','set'),self.counts)),
                    witness_ranges=[{k:v for k,v in x.items() if k != 'data'} for x in self.inputs])
        (directory/'program.json').write_text(json.dumps(meta, indent=2)+'\n')
