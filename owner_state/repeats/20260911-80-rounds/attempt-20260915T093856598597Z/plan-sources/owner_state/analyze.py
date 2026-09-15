"""Derive owner-binding source data and within-batch comparisons from raw logs.

python -m owner_state.analyze --run owner_state/results/collect-<id>
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import statistics as st
from pathlib import Path

from owner_state.run import ROOT, MODES, digest, validate_evidence

HERE = ROOT / 'owner_state'
VARIANTS = ('baseline', 'cse_dce')
DIAGNOSTICS = HERE / 'diagnostics/20260911-full-restart'
T_975_DF7 = 2.3646242510103
# Fixed before the 80-round collection; independently checked by integrating
# the Student-t density. Keeping the historical constant preserves old exports.
T_975_DF79 = 1.9904502102301282
T_CRITICAL = {8: T_975_DF7, 80: T_975_DF79}
PHASE_GROUPS = {
    'execution_s': ('execute_ms',),
    'witness_build_s': ('build_ms',),
    'commitment_s': ('commit_ms',),
    'bus_s': ('bus_ms',),
    'constraints_s': ('constraints_ms',),
    'opening_s': ('pcs_open_ms',),
    'other_s': ('transcript_setup_ms', 'claim_prep_ms', 'reduction_ms',
                'finalize_ms', 'internal_residual_ms', 'outer_prove_residual_ms'),
}


def paired_ratio(numerator, denominator):
    """Predeclared two-sided t interval on 8 or 80 paired block log ratios."""
    n = len(numerator)
    if n not in T_CRITICAL or len(denominator) != n or any(not math.isfinite(x) or x<=0 for x in [*numerator,*denominator]):
        raise ValueError('this analysis contract requires 8 or 80 positive paired observations')
    logs = [math.log(a / b) for a, b in zip(numerator, denominator)]
    center = st.mean(logs)
    radius = T_CRITICAL[n] * st.stdev(logs) / math.sqrt(n)
    return {'pairs': n, 'ratio': math.exp(center), 'ci95_low': math.exp(center - radius),
            'ci95_high': math.exp(center + radius),
            'block_ratios': [math.exp(value) for value in logs]}


def export_numbers(value):
    """Stable derived-data precision across platform libm implementations.

    Raw logs retain every recorded digit. Twelve significant digits greatly
    exceed measurement precision and remove irrelevant last-bit differences
    in logarithms, exponentials and derived floating-point arithmetic.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('nonfinite derived measurement')
        return float(format(value, '.12g'))
    if isinstance(value, dict):
        return {key: export_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [export_numbers(item) for item in value]
    return value


def csv_text(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(export_numbers(rows))
    return out.getvalue()


def analyze(directory):
    directory = directory.resolve()
    report = validate_evidence(directory)
    variants = tuple(report['variants'])
    blocks = report['blocks']
    if (report['command'] != 'collect' or report['warmups_per_condition'] != 1
            or (variants, blocks) not in ((VARIANTS, 8), (('cse_dce',), 80))):
        raise ValueError('the report differs from the predeclared 8-round or 80-round design')
    expected = {f'{variant}/{mode}' for variant in variants for mode in MODES}
    if set(report['cases']) != expected or any(row['condition'] not in expected for row in report['runs']):
        raise ValueError('unexpected or missing condition in analysis')
    samples = []
    for sequence, entry in enumerate(report['runs'], 1):
        result, phases = entry['result'], entry['phases']
        row = {key: entry[key] for key in ('condition', 'variant', 'mode', 'kind', 'block', 'position')}
        row.update(sequence=sequence, prove_s=result['prove_including_execute_ms']/1000,
                   verify_ms=result['verify_ms'], assembly_ms=result['assembly_ms'],
                   process_s=entry['process_seconds'], instructions=result['cycles'],
                   memory_cells=result['cells'], log_mem=result['log_mem'],
                   xor=result['counts'][0], mul=result['counts'][1],
                   committed_cells=result['committed'], proof_bytes=result['proof_bytes'],
                   max_rss_bytes=entry['memory']['max_rss_bytes'],
                   peak_footprint_bytes=entry['memory']['peak_footprint_bytes'])
        for group, fields in PHASE_GROUPS.items():
            row[group] = sum(phases[field] for field in fields)/1000
        row['four_major_proving_stages_s'] = sum(row[group] for group in
                                                 ('commitment_s', 'bus_s', 'constraints_s', 'opening_s'))
        row['prove_after_execution_and_build_s'] = row['prove_s'] - row['execution_s'] - row['witness_build_s']
        if not math.isclose(sum(row[group] for group in PHASE_GROUPS), row['prove_s'], abs_tol=1e-8):
            raise ValueError('display phase groups do not reconcile to outer prove time')
        for key, value in phases.items():
            if key.endswith('_ms'):
                row['phase_' + key] = value
        row.update(log=str((directory/entry['log']).relative_to(ROOT)), log_sha256=entry['log_sha256'])
        samples.append(row)
    measured = [row for row in samples if row['kind'] == 'measured']
    conditions = {}
    costs = []
    for condition, case in report['cases'].items():
        group = sorted((row for row in measured if row['condition'] == condition), key=lambda row: row['block'])
        if [row['block'] for row in group] != list(range(1, blocks+1)):
            raise ValueError('incomplete or duplicate measured block')
        for key in ('instructions', 'memory_cells', 'log_mem', 'xor', 'mul', 'committed_cells', 'proof_bytes'):
            if len({row[key] for row in group}) != 1:
                raise ValueError(f'expected deterministic {key} in {condition}')
        timing = [row['prove_s'] for row in group]
        summary = {key: group[0][key] for key in ('instructions', 'memory_cells', 'log_mem', 'xor', 'mul',
                                               'committed_cells', 'proof_bytes')}
        summary.update(n=len(group), prove_median_s=st.median(timing), prove_mean_s=st.mean(timing),
                       prove_min_s=min(timing), prove_max_s=max(timing),
                       prove_sd_s=st.stdev(timing), verify_median_ms=st.median(row['verify_ms'] for row in group),
                       max_peak_footprint_gib=max(row['peak_footprint_bytes'] for row in group)/2**30,
                       phases_mean_s={key: st.mean(row[key] for row in group) for key in PHASE_GROUPS})
        sections = case['metadata']['optimization']['sections']
        counts = {kind: sum(sum(section['after'].values()) for section in sections if section['kind'] == kind)
                  for kind in ('keccak256', 'sha256', 'relation')}
        counts['relation'] += 4  # Rust wrapper: three SETs and one JUMP.
        if sum(counts.values()) != summary['instructions']:
            raise ValueError('hash section attribution does not sum to VM instructions')
        summary['instruction_sections'] = counts
        summary['hash_instruction_fraction'] = (counts['keccak256']+counts['sha256'])/summary['instructions']
        summary['padded_memory_rows'] = 2**summary['log_mem']
        summary['padded_xor_rows'] = 1 << (summary['xor']-1).bit_length()
        summary['padded_mul_rows'] = 1 << (summary['mul']-1).bit_length()
        conditions[condition] = summary
        for index, section in enumerate(sections):
            costs.append({'condition': condition, 'section': index, 'kind': section['kind'],
                          'length_bytes': section['length_bytes'],
                          'instructions': sum(section['after'].values()),
                          'xor': section['after'].get('xor', 0), 'mul': section['after'].get('mul', 0),
                          'set': section['after'].get('set', 0)})
    def values(condition):
        return [row['prove_s'] for row in sorted(measured, key=lambda row: row['block']) if row['condition'] == condition]
    comparisons = []
    for mode in MODES:
        numerator, denominator = f'cse_dce/{mode}', f'baseline/{mode}'
        if numerator in conditions and denominator in conditions:
            comparisons.append({'comparison': 'optimization', 'numerator': numerator, 'denominator': denominator,
                                **paired_ratio(values(numerator), values(denominator))})
    for variant in variants:
        for mode in ('rlp', 'ssz'):
            numerator, denominator = f'{variant}/{mode}', f'{variant}/direct'
            comparisons.append({'comparison': 'anchor', 'numerator': numerator, 'denominator': denominator,
                                **paired_ratio(values(numerator), values(denominator))})
        numerator, denominator = f'{variant}/ssz', f'{variant}/rlp'
        comparisons.append({'comparison': 'ssz_vs_rlp_secondary', 'numerator': numerator, 'denominator': denominator,
                            **paired_ratio(values(numerator), values(denominator))})
    summary = {'source_run': str(directory.relative_to(ROOT)), 'source_report_sha256': digest(directory/'report.json'),
               'scope': f'within this batch; 95% t intervals on paired block log ratios, df={blocks-1}, exploratory',
               'measured_proofs': len(measured), 'warmup_proofs': len(samples)-len(measured),
               'conditions': conditions, 'comparisons': comparisons}
    return samples, costs, summary


def products(directory, diagnostics=DIAGNOSTICS):
    directory, diagnostics = directory.resolve(), diagnostics.resolve()
    samples, costs, summary = analyze(directory)
    comparisons = [{key: value for key, value in entry.items() if key != 'block_ratios'}
                   for entry in summary['comparisons']]
    report = json.loads((directory/'report.json').read_text())
    environment_rows=[]
    for entry in report['runs']:
        for endpoint in ('before','after'):
            filename=entry['environment_'+endpoint]
            env=json.loads((directory/filename).read_text())
            load=re.search(r'\{\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\}',env['load'].get('stdout',''))
            battery=re.search(r'(\d+)%;',env['power'].get('stdout',''))
            environment_rows.append({'condition':entry['condition'],'kind':entry['kind'],'block':entry['block'],
                                     'endpoint':endpoint,'recorded_utc':env['recorded_utc'],'power_source':env['power_source'],
                                     'battery_percent':int(battery[1]) if battery else '',
                                     'load_1m':float(load[1]) if load else '',
                                     'load_5m':float(load[2]) if load else '',
                                     'load_15m':float(load[3]) if load else '',
                                     'record':str((directory/filename).relative_to(ROOT))})
    micro = json.loads((diagnostics/'report.json').read_text())
    if micro['binary_sha256'] != report['runner']['binary_sha256']:
        raise ValueError('selected hash diagnostics and full proofs must use the same executable')
    diagnostic_samples, diagnostic_summary = [], []
    for case, meta in micro['cases'].items():
        group = sorted((row for row in micro['runs'] if row['case']==case), key=lambda row: row['repetition'])
        if [row['repetition'] for row in group] != list(range(1, 9)):
            raise ValueError('incomplete hash diagnostic')
        for entry in group:
            if entry['exit_code'] != 0 or digest(diagnostics/entry['log']) != entry['log_sha256']:
                raise ValueError('hash diagnostic log changed or process failed')
            diagnostic_samples.append({'case': case, 'kind': meta['kind'], 'length_bytes': meta['length'],
                                       'variant': meta['variant'], 'repetition': entry['repetition'],
                                       'execute_ms': entry['result']['execute_ms'],
                                       'instructions': entry['result']['cycles'],
                                       'log': str((diagnostics/entry['log']).relative_to(ROOT)),
                                       'log_sha256': entry['log_sha256']})
        timing=[row['result']['execute_ms'] for row in group]
        diagnostic_summary.append({'case': case, 'kind': meta['kind'], 'length_bytes': meta['length'],
                                   'variant': meta['variant'], 'n': 8, 'execute_median_ms': st.median(timing),
                                   'execute_min_ms': min(timing), 'execute_max_ms': max(timing),
                                   'instructions': group[0]['result']['cycles']})
    return {'source-data.csv': csv_text(samples), 'hash-instructions.csv': csv_text(costs),
            'comparisons.csv': csv_text(comparisons), 'summary.json': json.dumps(export_numbers(summary), indent=2, allow_nan=False)+'\n',
            'environment.csv': csv_text(environment_rows),
            'hash-diagnostic-samples.csv': csv_text(diagnostic_samples),
            'hash-diagnostic-summary.csv': csv_text(diagnostic_summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE/'analysis')
    parser.add_argument('--diagnostics', type=Path, default=DIAGNOSTICS)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, contents in products(args.run, args.diagnostics).items():
        path = args.output/name
        if args.check:
            if path.read_text() != contents:
                raise ValueError(f'analysis output differs: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
    print(f'Analysis {"checked" if args.check else "written"}: {args.output}')


if __name__ == '__main__':
    main()
