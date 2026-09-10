"""Validate phase accounting and the narrow, reproducible upstream patch."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from owner_state import instrumentation as instrumentation


def record(**overrides):
    value = {key: float(i + 1) for i, key in enumerate(instrumentation.PHASE_KEYS)}
    value.update(profile_schema=1, scope=instrumentation.SCOPE,
                 internal_total_ms=57.0, internal_residual_ms=2.0)
    value.update(overrides)
    return 'PHASES ' + json.dumps(value) + '\n'


class PhaseOutputTests(unittest.TestCase):
    def test_libtest_prefix_and_outer_accounting(self):
        for prefix in ('', 'test owner_state_bench ... '):
            phases = instrumentation.parse_phases(prefix + record(), outer_prove_ms=60.0)
            self.assertEqual(phases['outer_prove_residual_ms'], 3.0)
            self.assertEqual(sum(phases[key] for key in instrumentation.PHASE_KEYS), 55.0)

    def test_missing_duplicate_and_ambiguous_records_fail(self):
        for text in ('', record() + record(), record().replace('"execute_ms": 1.0',
                                                            '"execute_ms": 1.0, "execute_ms": 1.0')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                instrumentation.parse_phases(text)

    def test_invalid_duration_or_accounting_fails(self):
        for overrides in ({'execute_ms': -1}, {'execute_ms': float('nan')},
                          {'execute_ms': True}, {'execute_ms': '1.0'},
                          {'internal_total_ms': 56.0}, {'scope': 'unknown'},
                          {'profile_schema': 2}, {'unexpected_ms': 1}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                instrumentation.parse_phases(record(**overrides))
        with self.assertRaises(ValueError):
            instrumentation.parse_phases(record(), outer_prove_ms=56.9)


class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = instrumentation.ROOT / 'vendor/leanVM-b' / instrumentation.SOURCE_PATH
        if not path.exists():
            raise unittest.SkipTest('pinned baseline checkout required for patch application checks')
        cls.source = path.read_text()
        cls.changed = instrumentation.instrument_source(cls.source)

    def test_patch_matches_generator_and_preserves_other_functions(self):
        self.assertEqual(instrumentation.PATCH.read_text(), instrumentation.make_patch(self.source))
        original_prefix, original_body = self.source.split(instrumentation.BEGIN, 1)
        changed_prefix, changed_body = self.changed.split(instrumentation.BEGIN, 1)
        self.assertEqual(original_prefix, changed_prefix)
        original_body, original_suffix = original_body.split(instrumentation.END, 1)
        changed_body, changed_suffix = changed_body.split(instrumentation.END, 1)
        self.assertEqual(original_suffix, changed_suffix)
        # Recover the original function by deleting only clock/report additions
        # and undoing the return-expression capture; the proof work is identical.
        changed_body = changed_body[changed_body.index('    let prof = '):]
        changed_body = changed_body.split('    let phase_finalize_ms = ', 1)[0]
        changed_body = re.sub(r'^    let phase_start = phase_clock\(\);\n', '', changed_body,
                              flags=re.MULTILINE)
        changed_body = re.sub(r'^    let phase_\w+_ms = phase_elapsed\(phase_start\);\n', '', changed_body,
                              flags=re.MULTILINE)
        changed_body = changed_body.replace('    let result = (\n', '    (\n')
        self.assertTrue(changed_body.endswith('    );\n'))
        changed_body = changed_body[:-7] + '    )\n}\n'
        self.assertEqual(original_body, changed_body)

    def test_only_original_return_expression_is_replaced(self):
        removed = [line[1:] for line in instrumentation.PATCH.read_text().splitlines()
                   if line.startswith('-') and not line.startswith('---')]
        self.assertEqual(removed, ['    (', '    )'])

    def test_patch_applies_once_to_copy_and_checks_exact_source(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            target = checkout / instrumentation.SOURCE_PATH
            target.parent.mkdir(parents=True)
            target.write_text(self.source)
            before = target.read_bytes()
            expected = instrumentation.sha256(self.changed.encode())
            self.assertEqual(instrumentation.check_or_apply(checkout), expected)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(instrumentation.check_or_apply(checkout, apply=True), expected)
            self.assertEqual(target.read_text(), self.changed)
            with self.assertRaises(ValueError):
                instrumentation.check_or_apply(checkout, apply=True)
        with self.assertRaises(ValueError):
            instrumentation.instrument_source(self.source + '// unrelated change\n')
        with self.assertRaises(ValueError):
            instrumentation.check_or_apply(instrumentation.ROOT / 'vendor/leanVM-b', apply=True)

    @unittest.skipUnless(shutil.which('rustfmt'), 'rustfmt required for Rust syntax validation')
    def test_patched_module_parses_as_rust(self):
        result = subprocess.run(['rustfmt', '--edition', '2024', '--emit', 'stdout',
                                 '--config', 'skip_children=true'], input=self.changed,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('rustc'), 'rustc required for actual JSON emitter validation')
    def test_actual_rust_emitter_is_opt_in_and_matches_parser(self):
        # Compile the exact added emitter/clock expressions independently of the
        # expensive prover. This checks Rust formatting and its machine record.
        body = self.changed.split(instrumentation.BEGIN, 1)[1].split(instrumentation.END, 1)[0]
        init = body.split('    let prof = ', 1)[0]
        tail = body[body.index('    let phase_finalize_ms = '):]
        durations = ''.join(f'    let phase_{key} = 0.0;\n' for key in instrumentation.PHASE_KEYS[:-1])
        program = ('fn main() {\n' + init + durations
                   + '    let phase_start = phase_clock();\n    let result = ();\n' + tail)
        with tempfile.TemporaryDirectory() as directory:
            rust = Path(directory) / 'emitter.rs'
            executable = Path(directory) / 'emitter'
            rust.write_text(program)
            compiled = subprocess.run(['rustc', '--edition', '2024', str(rust), '-o', str(executable)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            env = os.environ.copy()
            env.pop('LEANVM_PHASE_PROFILE', None)
            disabled = subprocess.run([str(executable)], env=env, capture_output=True, text=True, check=True)
            self.assertEqual(disabled.stderr, '')
            env['LEANVM_PHASE_PROFILE'] = '1'
            enabled = subprocess.run([str(executable)], env=env, capture_output=True, text=True, check=True)
            phases = instrumentation.parse_phases(enabled.stderr)
            self.assertGreaterEqual(phases['internal_total_ms'], phases['finalize_ms'])
            self.assertEqual(enabled.stderr.count('PHASES '), 1)


if __name__ == '__main__':
    unittest.main()
