"""Measurement scheduling, provenance, failure handling and evidence checks."""
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from owner_state import run
from owner_state.instrumentation import PHASE_KEYS, SCOPE


def environment(power='AC Power', mode='2'):
    return {'power_source': power, 'power': {'returncode': 0, 'stdout': power},
            'power_settings': {'returncode': 0, 'stdout': 'powermode ' + mode},
            'rustc': {'stdout': 'rustc'}, 'cargo': {'stdout': 'cargo'},
            'hardware': {'stdout': 'hardware'}, 'os_version': {'stdout': 'os'}}


class SchedulingTests(unittest.TestCase):
    def test_six_conditions_have_balanced_positions_and_predecessors(self):
        conditions = [f'{v}/{m}' for v in run.DEFAULT_VARIANTS for m in run.MODES]
        warmup, orders = run.balanced_orders(conditions, 8, 1, 20260910)
        self.assertEqual(len(warmup), 1)
        self.assertEqual(sorted(warmup[0]), sorted(conditions))
        self.assertEqual(len(orders), 8)
        for order in orders:
            self.assertEqual(sorted(order), sorted(conditions))
        predecessors = Counter()
        for order in orders[:6]:
            predecessors.update(zip(order, order[1:]))
        self.assertEqual(len(predecessors), 30)
        self.assertEqual(set(predecessors.values()), {1})
        for position in range(6):
            self.assertEqual(set(Counter(order[position] for order in orders[:6]).values()), {1})
            counts = Counter(order[position] for order in orders)
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertEqual((warmup, orders), run.balanced_orders(conditions, 8, 1, 20260910))
        self.assertNotEqual(orders, run.balanced_orders(conditions, 8, 1, 42)[1])

    def test_three_conditions_balance_positions_and_predecessors_in_six_rounds(self):
        conditions = ['cse_dce/'+mode for mode in run.MODES]
        warmups, orders = run.balanced_orders(conditions, 80, 1, 20260911)
        self.assertEqual(len(warmups), 1)
        self.assertEqual(len(orders), 80)
        for order in orders:
            self.assertEqual(sorted(order), sorted(conditions))
        for start in range(0, 78, 6):
            cycle = orders[start:start+6]
            predecessors = Counter(pair for order in cycle for pair in zip(order, order[1:]))
            self.assertEqual(len(predecessors), 6)
            self.assertEqual(set(predecessors.values()), {2})
            for position in range(3):
                self.assertEqual(set(Counter(row[position] for row in cycle).values()), {2})
        self.assertEqual((warmups, orders), run.balanced_orders(conditions, 80, 1, 20260911))

    def test_invalid_schedule(self):
        for conditions, blocks, warmups in (([], 8, 1), (['a', 'a'], 8, 1), (['a'], 0, 1), (['a'], 8, -1)):
            with self.assertRaises(ValueError):
                run.balanced_orders(conditions, blocks, warmups, 1)


class EnvironmentTests(unittest.TestCase):
    def test_power_requires_actual_source_line(self):
        self.assertEqual(run.power_source("Now drawing from 'AC Power'\nBattery Power exists too"), 'AC Power')
        self.assertIsNone(run.power_source('AC Power settings'))
        run.check_environment(environment())
        run.check_environment(environment(), environment())
        for candidate in (environment('Battery Power'), environment(None), environment(mode='0')):
            with self.assertRaises(ValueError):
                run.check_environment(candidate, environment())

    def test_process_environment_clears_inherited_profile_and_mutation_flags(self):
        with patch.dict(os.environ, {'REAL_STATE_MUTATE_CELL': '123', 'FLOCK_COMMIT_TIMING': '1',
                                     'FLOCK_NO_PREFAULT': '1', 'LEANVM_PROFILE': '1', 'RAYON_NUM_THREADS': '99'}):
            env = run.process_environment(Path('/tmp/inputs'), 'prove')
        self.assertEqual(env['RAYON_NUM_THREADS'], '11')
        self.assertEqual(env['LEANVM_PHASE_PROFILE'], '1')
        self.assertFalse(any(key.startswith('FLOCK_') for key in env))
        self.assertNotIn('LEANVM_PROFILE', env)
        self.assertNotIn('REAL_STATE_MUTATE_CELL', env)
        env = run.process_environment(Path('/tmp/inputs'), 'execute', {'cell': 4, 'replacement': 0})
        self.assertEqual(env['REAL_STATE_MUTATE_VALUE'], '0')


class ResultTests(unittest.TestCase):
    def test_prefixed_records_and_ambiguity(self):
        value = {'action': 'verify', 'witness_loaded': False}
        for prefix in ('', 'test real_state_bench::real_state_benchmark ... '):
            result, rejected = run.parse_output(prefix + 'RESULT ' + json.dumps(value) + '\nok\n')
            self.assertEqual(result, value)
            self.assertIsNone(rejected)
        with self.assertRaises(ValueError):
            run.parse_output('RESULT {}\nRESULT {}\n')
        with self.assertRaises(ValueError):
            run.parse_output('RESULT {}\nREJECTED bad\n')

    def test_macos_memory_units(self):
        parsed = run.parse_memory('123 maximum resident set size\n456 peak memory footprint\n')
        self.assertEqual(parsed, {'max_rss_bytes': 123, 'peak_footprint_bytes': 456})

    def test_wrapper_counts_and_nonzero_exit_are_checked(self):
        meta = {'memory_cells': 10, 'op_counts': {'xor': 2, 'mul': 3, 'set': 4}}
        result = {'action': 'prove', 'counts': [2, 3, 7, 0, 1, 0], 'cycles': 13,
                  'cells': 13, 'wrong_public_rejected': True, 'mutated_proof_rejected': True}
        entry = {'exit_code': 0, 'result': result, 'phases': {}}
        self.assertTrue(run.validate_result(entry, 'prove', meta))
        self.assertFalse(run.validate_result(dict(entry, exit_code=1), 'prove', meta))
        self.assertFalse(run.validate_result(dict(entry, result=dict(result, cycles=12)), 'prove', meta))
        entry = {'exit_code': 0, 'rejection': 'REJECTED mutation_cell=4 execute_ms=1 reason=write-once conflict'}
        self.assertTrue(run.validate_result(entry, 'execute', meta, {'cell': 4}))
        self.assertFalse(run.validate_result(entry, 'execute', meta, {'cell': 5}))

    def test_requested_memory_metrics_must_both_be_positive(self):
        meta = {'memory_cells': 10, 'op_counts': {'xor': 2, 'mul': 3, 'set': 4}}
        for action in ('prove', 'verify'):
            entry = {'exit_code': 0, 'memory_measurement': 'macos-time-l', 'phases': {},
                     'result': {'action': action, 'counts': [2, 3, 7, 0, 1, 0], 'cycles': 13, 'cells': 13,
                                'wrong_public_rejected': True, 'mutated_proof_rejected': True,
                                'witness_loaded': False}}
            self.assertTrue(run.validate_result(dict(entry, memory={'max_rss_bytes': 1, 'peak_footprint_bytes': 2}), action, meta))
            for memory in ({}, {'max_rss_bytes': 1}, {'peak_footprint_bytes': 2},
                           {'max_rss_bytes': 0, 'peak_footprint_bytes': 2},
                           {'max_rss_bytes': 1, 'peak_footprint_bytes': -1},
                           {'max_rss_bytes': True, 'peak_footprint_bytes': 2}):
                with self.subTest(action=action, memory=memory):
                    self.assertFalse(run.validate_result(dict(entry, memory=memory), action, meta))

    def test_runner_parses_real_emitted_phase_schema_with_rounded_outer(self):
        phases = {key: 1.0 for key in PHASE_KEYS}
        phases.update(profile_schema=1, scope=SCOPE, internal_total_ms=10.5001, internal_residual_ms=0.5001)
        result = {'action': 'prove', 'prove_including_execute_ms': 10.5}
        output = 'PHASES ' + json.dumps(phases) + '\nRESULT ' + json.dumps(result) + '\n'
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / 'process.log'
            def execute(*args, **kwargs):
                kwargs['stdout'].write(output)
                return type('Completed', (), {'returncode': 0})()
            with patch.object(run.subprocess, 'run', side_effect=execute):
                entry = run.run_process(Path('/tmp/runner'), Path('/tmp/input'), 'prove', log, measure_memory=False)
            self.assertNotIn('parse_error', entry)
            self.assertAlmostEqual(entry['phases']['outer_prove_residual_ms'], -0.0001)
            self.assertEqual(entry['phases']['outer_timer_resolution_ms'], 0.001)
            with self.assertRaises(FileExistsError):
                run.run_process(Path('/tmp/runner'), Path('/tmp/input'), 'prove', log, measure_memory=False)


class FailureRetentionTests(unittest.TestCase):
    def test_ac_failure_writes_unique_failed_report_without_running_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            def snapshot(destination, report, variant, mode):
                report['cases'][f'{variant}/{mode}'] = {'metadata': {}, 'sha256': {'public.bin': mode}}
            with (patch.object(run, 'RESULTS', base), patch.object(run, 'SOURCE_NAMES', ()),
                  patch.object(run, 'sources', return_value={}), patch.object(run, 'load_runner', return_value=(Path('/tmp/runner'), {})),
                  patch.object(run, 'snapshot_case', side_effect=snapshot),
                  patch.object(run, 'environment', return_value=environment('Battery Power')),
                  patch.object(run, 'run_process') as process):
                for _ in range(2):
                    with self.assertRaises(ValueError):
                        run.collect(blocks=1, warmups=0)
            self.assertEqual(process.call_count, 0)
            reports = list(base.glob('collect-*/report.json'))
            self.assertEqual(len(reports), 2)
            for path in reports:
                report = json.loads(path.read_text())
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(report['runs']), 1)
                self.assertFalse(report['environment_checks_passed'])
                self.assertTrue((path.parent / report['runs'][0]['environment_before']).exists())

    def test_evidence_path_cannot_escape(self):
        with self.assertRaises(ValueError):
            run.inside(Path('/tmp/evidence'), '../outside')


class EvidenceReplayTests(unittest.TestCase):
    def make_evidence(self, directory, command='verify'):
        meta = {'memory_cells': 10, 'op_counts': {'xor': 2, 'mul': 3, 'set': 4}}
        condition = 'cse_dce/direct'
        case = directory / 'cases' / condition
        case.mkdir(parents=True)
        run.write_json(case / 'program.json', meta)
        (case / 'public.bin').write_bytes(bytes(32))
        entry = {'variant': 'cse_dce', 'mode': 'direct', 'condition': condition,
                 'exit_code': 0, 'passed': True, 'log': 'result.log', 'rejection': None,
                 'verifier_files': ['program.bin', 'proof.bin', 'public.bin']}
        if command == 'verify':
            entry['result'] = {'action': 'verify', 'counts': [2, 3, 7, 0, 1, 0],
                               'cycles': 13, 'cells': 13, 'witness_loaded': False}
        else:
            entry.update(result=None, mutation={'cell': 4},
                         rejection='REJECTED mutation_cell=4 execute_ms=1 reason=write-once conflict')
        report = {'schema': 'leanvm-owner-run-v1', 'status': 'complete', 'command': command,
                  'source_sha256': {}, 'cases': {condition: {'metadata': meta,
                      'sha256': {name: run.digest(case / name) for name in ('program.json', 'public.bin')}}},
                  'runs': [entry]}
        self.write_evidence(directory, report)
        return report

    def write_evidence(self, directory, report):
        entry = report['runs'][0]
        text = 'RESULT ' + json.dumps(entry['result']) if entry['result'] is not None else entry['rejection']
        (directory / 'result.log').write_text(text + '\n')
        entry['log_sha256'] = run.digest(directory / 'result.log')
        run.write_json(directory / 'report.json', report)

    def test_embedded_metadata_must_match_hashed_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = self.make_evidence(directory)
            run.validate_evidence(directory)
            report['cases']['cse_dce/direct']['metadata']['memory_cells'] = 11
            run.write_json(directory / 'report.json', report)
            with self.assertRaisesRegex(ValueError, 'embedded metadata'):
                run.validate_evidence(directory)

    def test_verify_semantics_are_replayed_even_when_log_hash_matches(self):
        changes = ({'witness_loaded': True}, {'cycles': 12}, {'action': 'execute'})
        for changed in changes:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                report = self.make_evidence(directory)
                report['runs'][0]['result'].update(changed)
                self.write_evidence(directory, report)
                with self.assertRaisesRegex(ValueError, 'semantic result'):
                    run.validate_evidence(directory)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = self.make_evidence(directory)
            report['runs'][0]['verifier_files'].append('witness.bin')
            self.write_evidence(directory, report)
            with self.assertRaisesRegex(ValueError, 'three allowed files'):
                run.validate_evidence(directory)

    def test_negative_rejection_cell_and_reason_are_replayed(self):
        for replacement in ('REJECTED mutation_cell=5 execute_ms=1 reason=write-once conflict',
                            'REJECTED mutation_cell=4 execute_ms=1 reason=unexpected panic'):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                report = self.make_evidence(directory, 'negative')
                run.validate_evidence(directory)
                report['runs'][0]['rejection'] = replacement
                self.write_evidence(directory, report)
                with self.assertRaisesRegex(ValueError, 'semantic result'):
                    run.validate_evidence(directory)


if __name__ == '__main__':
    unittest.main()
