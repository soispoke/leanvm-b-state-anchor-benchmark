"""Small synthetic checks for the predeclared paired analysis, without proving."""
import math
import unittest
from unittest.mock import patch

from owner_state import analyze


class PairedRatioTests(unittest.TestCase):
    def test_constant_paired_effect_is_invariant_to_shared_drift(self):
        baseline = [10.0, 25.0, 13.0, 44.0, 22.0, 19.0, 35.0, 17.0]
        optimized = [0.8 * value for value in baseline]
        result = analyze.paired_ratio(optimized, baseline)
        for key in ('ratio', 'ci95_low', 'ci95_high'):
            self.assertAlmostEqual(result[key], 0.8, places=14)
        scaled = analyze.paired_ratio([value * 1000 for value in optimized],
                                      [value * 1000 for value in baseline])
        self.assertAlmostEqual(scaled['ratio'], result['ratio'], places=14)

    def test_swapping_conditions_inverts_ratio_and_interval(self):
        numerator = [8.0, 8.8, 9.6, 10.4, 11.2, 12.0, 12.8, 13.6]
        denominator = [10.0] * 8
        forward = analyze.paired_ratio(numerator, denominator)
        reverse = analyze.paired_ratio(denominator, numerator)
        self.assertAlmostEqual(reverse['ratio'], 1 / forward['ratio'])
        self.assertAlmostEqual(reverse['ci95_low'], 1 / forward['ci95_high'])
        self.assertAlmostEqual(reverse['ci95_high'], 1 / forward['ci95_low'])
        logs = [math.log(a / b) for a, b in zip(numerator, denominator)]
        average = sum(logs) / 8
        variance = sum((value - average) ** 2 for value in logs) / 7
        self.assertAlmostEqual(forward['ci95_high'], math.exp(average + 2.3646242510103 * math.sqrt(variance / 8)))

    def test_requires_exactly_eight_positive_pairs(self):
        for first, second in (([1.0]*7, [1.0]*8), ([1.0]*8, [1.0]*7), ([0.0]+[1.0]*7, [1.0]*8)):
            with self.assertRaises(ValueError):
                analyze.paired_ratio(first, second)


def synthetic_report():
    conditions = [f'{variant}/{mode}' for variant in analyze.VARIANTS for mode in analyze.MODES]
    sections = [
        {'kind': 'keccak256', 'length_bytes': 52, 'after': {'xor': 2, 'mul': 3}},
        {'kind': 'relation', 'length_bytes': None, 'after': {'set': 4}},
    ]
    report = {'command': 'collect', 'blocks': 8, 'variants': list(analyze.VARIANTS),
              'warmups_per_condition': 1, 'cases': {
                  condition: {'metadata': {'optimization': {'sections': sections}}}
                  for condition in conditions}, 'runs': []}
    for kind, blocks in (('warmup', [1]), ('measured', range(1, 9))):
        for block in blocks:
            # Deliberately change chronological condition order every block.
            order = conditions[block % 6:] + conditions[:block % 6]
            if block % 2:
                order = list(reversed(order))
            for position, condition in enumerate(order, 1):
                variant, mode = condition.split('/')
                baseline_ms = (10000 + block * 1700) * {'direct': 1, 'rlp': 1.1, 'ssz': 1.2}[mode]
                total_ms = baseline_ms * (0.8 if variant == 'cse_dce' else 1.0)
                if kind == 'warmup':
                    total_ms *= 100  # Must not influence absolute or paired estimates.
                fractions = {'execute_ms': 0.1, 'build_ms': 0.1, 'commit_ms': 0.2,
                             'bus_ms': 0.2, 'constraints_ms': 0.1, 'pcs_open_ms': 0.1}
                for name in analyze.PHASE_GROUPS['other_s']:
                    fractions[name] = 0.2 / 6
                phases = {name: total_ms * fraction for name, fraction in fractions.items()}
                report['runs'].append({
                    'condition': condition, 'variant': variant, 'mode': mode, 'kind': kind,
                    'block': block, 'position': position, 'process_seconds': total_ms / 1000 + 1,
                    'log': f'{kind}-{block}-{variant}-{mode}.log', 'log_sha256': 'fixture',
                    'result': {'prove_including_execute_ms': total_ms, 'verify_ms': 1, 'assembly_ms': 2,
                               'cycles': 13, 'cells': 13, 'log_mem': 4, 'counts': [2, 3, 7, 0, 1, 0],
                               'committed': 1000, 'proof_bytes': 100},
                    'memory': {'max_rss_bytes': 1000, 'peak_footprint_bytes': 2000}, 'phases': phases})
    return report


class AnalysisPipelineTests(unittest.TestCase):
    def run_analysis(self, report):
        with (patch.object(analyze, 'validate_evidence', return_value=report),
              patch.object(analyze, 'digest', return_value='fixture-report-hash')):
            return analyze.analyze(analyze.ROOT / 'owner_state/results/synthetic-test')

    def test_pairs_by_block_preserves_warmups_and_uses_additive_means(self):
        samples, costs, summary = self.run_analysis(synthetic_report())
        self.assertEqual(len(samples), 54)
        self.assertEqual(summary['measured_proofs'], 48)
        self.assertEqual(summary['warmup_proofs'], 6)
        for comparison in summary['comparisons']:
            if comparison['comparison'] == 'optimization':
                for key in ('ratio', 'ci95_low', 'ci95_high'):
                    self.assertAlmostEqual(comparison[key], 0.8, places=13)
        for condition in summary['conditions'].values():
            self.assertAlmostEqual(sum(condition['phases_mean_s'].values()), condition['prove_mean_s'])
            self.assertLess(condition['prove_max_s'], 100)
            self.assertEqual(sum(condition['instruction_sections'].values()), condition['instructions'])
        self.assertEqual(len(costs), 12)

    def test_missing_or_duplicate_block_is_rejected(self):
        report = synthetic_report()
        report['runs'][-1]['block'] = 7
        with self.assertRaisesRegex(ValueError, 'incomplete or duplicate'):
            self.run_analysis(report)

    def test_nonadditive_phase_record_is_rejected(self):
        report = synthetic_report()
        report['runs'][0]['phases']['bus_ms'] += 10
        with self.assertRaisesRegex(ValueError, 'do not reconcile'):
            self.run_analysis(report)


class ExportPrecisionTests(unittest.TestCase):
    def test_last_bit_variation_does_not_change_derived_exports(self):
        original = {'ratio': 1.018792345678123, 'phase': 0.454645123456789,
                    'committed_cells': 207621052, 'kind': 'measured'}
        adjacent = {key: math.nextafter(value, math.inf) if isinstance(value, float) else value
                    for key, value in original.items()}
        self.assertEqual(analyze.export_numbers(original), analyze.export_numbers(adjacent))
        self.assertEqual(analyze.csv_text([original]), analyze.csv_text([adjacent]))
        self.assertEqual(analyze.export_numbers(original)['committed_cells'], 207621052)
        self.assertIsInstance(analyze.export_numbers(original)['committed_cells'], int)
        self.assertNotEqual(analyze.csv_text([original]),
                            analyze.csv_text([{**original, 'ratio': original['ratio'] + 1e-7}]))

    def test_nonfinite_export_values_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                analyze.export_numbers({'nested': [value]})


if __name__ == '__main__':
    unittest.main()
