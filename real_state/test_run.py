"""Regression checks for records emitted alongside Rust libtest's progress text."""
import unittest

from real_state.run import parse_output


class OutputTests(unittest.TestCase):
    def test_standalone_and_libtest_prefixed_records(self):
        for prefix in ('', 'test real_state_bench::real_state_benchmark ... '):
            result, rejection = parse_output(prefix + 'RESULT {"action":"verify","witness_loaded":false}\nok\n')
            self.assertEqual(result, {'action': 'verify', 'witness_loaded': False})
            self.assertIsNone(rejection)
            result, rejection = parse_output(prefix + 'REJECTED mutation_cell=4 reason=write-once conflict\nok\n')
            self.assertIsNone(result)
            self.assertTrue(rejection.startswith('REJECTED '))

    def test_missing_or_ambiguous_result(self):
        self.assertEqual(parse_output('running 0 tests\n'), (None, None))
        with self.assertRaises(ValueError):
            parse_output('RESULT {}\nRESULT {}\n')
