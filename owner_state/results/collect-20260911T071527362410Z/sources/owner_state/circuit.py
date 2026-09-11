"""Exact compiler optimizations over unchanged XOR/MUL/SET constraints.

CSE is scoped to each hash. DCE preserves every write to an initialized cell,
including equality checks, Boolean witness checks and public-input binding.
Neither optimization inspects witness values to choose instructions.
"""
from array import array
from collections import Counter
from contextlib import contextmanager
import struct

from real_state.circuit import Circuit as BaseCircuit


class Circuit(BaseCircuit):
    def __init__(self, *, cse=False, dce=False):
        self.tags = array('I')
        self.tag = 0
        self.sections = [{'kind': 'relation', 'length_bytes': None}]
        self.cse_enabled = cse
        self.dce_enabled = dce
        self.cache = None
        self.inverse = None
        self.finalized = False
        self.optimization = None
        super().__init__()

    def _set(self, out, value):
        if self.finalized:
            raise ValueError("cannot append to a finalized circuit")
        super()._set(out, value)
        self.tags.append(self.tag)

    def _gate(self, op, a, b, out):
        if self.finalized:
            raise ValueError("cannot append to a finalized circuit")
        super()._gate(op, a, b, out)
        self.tags.append(self.tag)

    @contextmanager
    def hash_scope(self, kind, length):
        prior = self.tag, self.cache, self.inverse
        self.tag = len(self.sections)
        self.sections.append({'kind': kind, 'length_bytes': length})
        self.cache = {} if self.cse_enabled else None
        self.inverse = {} if self.cse_enabled else None
        try:
            yield
        finally:
            self.tag, self.cache, self.inverse = prior

    def xor(self, a, b):
        if self.cache is None or a == b or a == self.zero or b == self.zero:
            return super().xor(a, b)
        if a == self.one and b in self.inverse:
            return self.inverse[b]
        if b == self.one and a in self.inverse:
            return self.inverse[a]
        key = (0, min(a, b), max(a, b))
        if key not in self.cache:
            self.cache[key] = super().xor(a, b)
            if a == self.one or b == self.one:
                self.inverse[self.cache[key]] = b if a == self.one else a
        return self.cache[key]

    def and_(self, a, b):
        if self.cache is None or a == b or a in (self.zero, self.one) or b in (self.zero, self.one):
            return super().and_(a, b)
        key = (1, min(a, b), max(a, b))
        if key not in self.cache:
            self.cache[key] = super().and_(a, b)
        return self.cache[key]

    def finalize(self):
        if self.finalized:
            return
        self.finalized = True
        before = {'instructions': sum(self.counts), 'memory_cells': len(self.values)}
        original_sections = [Counter() for _ in self.sections]
        after_sections = [Counter() for _ in self.sections]
        offsets = array('I')
        initialized = bytearray(len(self.values))
        initialized[:2] = b'\x01\x01'
        for entry in self.inputs:
            initialized[entry['base']:entry['base'] + entry['length']] = b'\x01' * entry['length']
        effects = bytearray()
        cursor = 0
        for tag in self.tags:
            offsets.append(cursor)
            op = self.ops[cursor]
            if op == 2:
                out, = struct.unpack_from('<I', self.ops, cursor + 1)
                cursor += 21
            else:
                a, b, out = struct.unpack_from('<III', self.ops, cursor + 1)
                cursor += 13
            effects.append(initialized[out])
            initialized[out] = 1
            original_sections[tag][('xor', 'mul', 'set')[op]] += 1
        if cursor != len(self.ops):
            raise ValueError('instruction stream and tags disagree')
        keep = bytearray(b'\x01') * len(offsets)
        used = bytearray(len(self.values))
        if self.dce_enabled:
            live = bytearray(len(self.values))
            live[:4] = b'\x01' * 4
            for index in range(len(offsets) - 1, -1, -1):
                off = offsets[index]
                op = self.ops[off]
                if op == 2:
                    out, = struct.unpack_from('<I', self.ops, off + 1)
                else:
                    a, b, out = struct.unpack_from('<III', self.ops, off + 1)
                if not (effects[index] or live[out]):
                    keep[index] = 0
                    continue
                live[out] = effects[index]
                used[out] = 1
                if op != 2:
                    live[a] = live[b] = used[a] = used[b] = 1
        else:
            used[:] = b'\x01' * len(used)
        used[:4] = b'\x01' * 4
        for entry in self.inputs:
            used[entry['base']:entry['base'] + entry['length']] = b'\x01' * entry['length']
        remap = array('I', [0xFFFFFFFF]) * len(used)
        values = []
        for old, present in enumerate(used):
            if present:
                remap[old] = len(values)
                values.append(self.values[old])
        ops = bytearray()
        tags = array('I')
        counts = [0, 0, 0]
        for index, off in enumerate(offsets):
            if not keep[index]:
                continue
            op = self.ops[off]
            if op == 2:
                out, = struct.unpack_from('<I', self.ops, off + 1)
                ops.extend(struct.pack('<BI', 2, remap[out]) + self.ops[off+5:off+21])
            else:
                a, b, out = struct.unpack_from('<III', self.ops, off + 1)
                ops.extend(struct.pack('<BIII', op, remap[a], remap[b], remap[out]))
            counts[op] += 1
            tags.append(self.tags[index])
            after_sections[self.tags[index]][('xor', 'mul', 'set')[op]] += 1
        for entry in self.inputs:
            if entry['length']:
                last = entry['base'] + entry['length'] - 1
                if remap[last] - remap[entry['base']] != entry['length'] - 1:
                    raise ValueError('witness range is not contiguous after compaction')
            entry['base'] = remap[entry['base']] if entry['length'] else len(values)
        self.values, self.ops, self.tags, self.counts = values, ops, tags, counts
        self.optimization = {
            'cse': self.cse_enabled, 'dce': self.dce_enabled, 'before_dce': before,
            'after_dce': {'instructions': sum(counts), 'memory_cells': len(values)},
            'sections': [dict(section, before=dict(before_count), after=dict(after_count))
                         for section, before_count, after_count in zip(self.sections, original_sections, after_sections)],
        }

    def export(self, directory, metadata):
        self.finalize()
        super().export(directory, dict(metadata, optimization=self.optimization))
