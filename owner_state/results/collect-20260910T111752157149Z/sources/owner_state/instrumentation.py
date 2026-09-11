"""Opt-in, exclusive wall-time phases for the pinned leanVM-b prover.

Apply only to a separate checkout, after real_state/leanvm-witness-api.patch:
  python -m owner_state.instrumentation vendor/leanVM-b-profiled --apply

Set LEANVM_PHASE_PROFILE=1 for measurements. Leave LEANVM_PROFILE and all
FLOCK_*_TIMING switches unset: their nested printing perturbs phase timing.
The patch changes only cpu::prove, leaves its work in its original order, and
emits one PHASES JSON record after timing has ended. It does not instrument the
interpreter loop or alter the verifier, statement, proof, or constraints.

The internal total ends before JSON formatting/output and local destructors.
Measure the outer prove() call as well; its difference from internal_total_ms
includes logging, local cleanup, and call/timer overhead. It is not 'pure
proof-construction time'. Background BLAKE3 setup still overlaps preparation
and proving, including for the mandatory padding instance in no-BLAKE3 runs.

Hash diagnostics should use separate generated component programs, recording
exact instructions, committed cells, and execution wall time. Do not subtract
their standalone times from end-to-end proofs, or sum them as a proof-cost
breakdown: shared tables, padding, allocation, and setup are nonlinear.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = Path(__file__).with_name('profile.patch')
SOURCE_PATH = Path('src/cpu/mod.rs')
BASE_SHA256 = 'a4715841708068e119965a505ba5880efea1944b35df0559b1b4e4f18d0ee1c2'
PHASE_KEYS = (
    'execute_ms', 'build_ms', 'transcript_setup_ms', 'commit_ms', 'bus_ms',
    'constraints_ms', 'claim_prep_ms', 'reduction_ms', 'pcs_open_ms', 'finalize_ms',
)
SCOPE = 'cpu_prove_before_logging_and_local_drops'
BEGIN = 'pub fn prove(program: &Program, public_input: [F128; 2]) -> (Proof, Stats) {\n'
END = '\n/// The public-input binding claim'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def instrument_source(source: str) -> str:
    """Generate exactly the allowed change; reject any other upstream version."""
    if sha256(source.encode()) != BASE_SHA256:
        raise ValueError('source is not the pinned CPU module plus the witness API patch')
    start = source.index(BEGIN)
    end = source.index(END, start)
    body = source[start:end]

    def replace_once(old: str, new: str) -> None:
        nonlocal body
        if body.count(old) != 1:
            raise ValueError(f'expected exactly one instrumentation seam: {old!r}')
        body = body.replace(old, new, 1)

    replace_once(BEGIN, BEGIN + '''    // Benchmark-only clocks; no proof data or transcript depends on them.
    let phase_prof = std::env::var_os("LEANVM_PHASE_PROFILE").is_some();
    let phase_clock = || phase_prof.then(std::time::Instant::now);
    let phase_elapsed = |start: Option<std::time::Instant>| {
        start.map_or(0.0, |s| s.elapsed().as_secs_f64() * 1e3)
    };
    let phase_total_start = phase_clock();
''')
    seams = (
        ('execute', '    let exec = program.execute(public_input);\n',
         '    let exec = program.execute(public_input);\n'),
        ('build', '    let w = program.build(&exec);\n',
         '    let w = program.build(&exec);\n'),
        ('transcript_setup', '    let counts = w.row_counts;\n',
         '    announce_public(&mut ps, w.log_mem, w.row_counts);\n'),
        ('commit', '    let committed = pcs::commit(&mut ps, &w.q);\n',
         '    let committed = pcs::commit(&mut ps, &w.q);\n'),
        ('bus', '    let l = &w.layout;\n',
         '    let bus_claims = leaf::prove_balance(&l.push, &l.pull, &l.count, &w.cols, &mut ps);\n'),
        ('constraints', '    let sch = schema();\n',
         '    if prof {\n        eprintln!("[prove] constraints : {:>7.2} ms", ms(t));\n'),
        ('claim_prep', '    let mut claims = bus_claims;\n',
         '    let slots = slot_claims(&w.layout, &claims);\n'),
        ('reduction', '    use flock_prover::r1cs_hashes::blake3::Compression;\n',
         '    let ring = crate::blake3_flock::ring_switch_open(blocks.len(), offset, &reduced);\n'),
        ('pcs_open', '    let mixed_open = pcs::open(&mut ps, &committed, &w.q, &slots, &ring);\n',
         '    let mixed_open = pcs::open(&mut ps, &committed, &w.q, &slots, &ring);\n'),
    )
    for phase, first, last in seams:
        replace_once(first, '    let phase_start = phase_clock();\n' + first)
        stop = f'    let phase_{phase}_ms = phase_elapsed(phase_start);\n'
        # Constraint stop precedes the legacy log; all other stops follow work.
        replace_once(last, stop + last if phase == 'constraints' else last + stop)
    replace_once('    crate::blake3_flock::write_stack_proof(&mut ps, zc, lc, mixed_open);\n',
                 '    let phase_start = phase_clock();\n'
                 '    crate::blake3_flock::write_stack_proof(&mut ps, zc, lc, mixed_open);\n')
    replace_once('    (\n        ps.into_proof(),\n', '    let result = (\n        ps.into_proof(),\n')
    fields = ','.join('\\"' + key + '\\":{:.9}' for key in PHASE_KEYS)
    args = ',\n            '.join('phase_' + key for key in PHASE_KEYS)
    summed = ' + '.join('phase_' + key for key in PHASE_KEYS)
    tail = '''    );
    let phase_finalize_ms = phase_elapsed(phase_start);
    let phase_internal_total_ms = phase_elapsed(phase_total_start);
    if phase_prof {
        let phase_accounted_ms = SUM;
        // Gaps include timer overhead and background-setup thread launch.
        // The spawned setup's CPU time is not added to overlapping wall time.
        let phase_internal_residual_ms = phase_internal_total_ms - phase_accounted_ms;
        eprintln!(
            "PHASES {{\\"profile_schema\\":1,\\"scope\\":\\"SCOPE\\",FIELDS,\\"internal_total_ms\\":{:.9},\\"internal_residual_ms\\":{:.9}}}",
            ARGS,
            phase_internal_total_ms,
            phase_internal_residual_ms,
        );
    }
    result
}
'''.replace('SUM', summed).replace('SCOPE', SCOPE).replace('FIELDS', fields).replace('ARGS', args)
    replace_once('    )\n}\n', tail)
    return source[:start] + body + source[end:]


def make_patch(source: str) -> str:
    changed = instrument_source(source)
    return ''.join(difflib.unified_diff(source.splitlines(keepends=True),
                                      changed.splitlines(keepends=True),
                                      fromfile='a/src/cpu/mod.rs',
                                      tofile='b/src/cpu/mod.rs', n=3))


def check_or_apply(checkout: Path, *, apply: bool = False) -> str:
    """Check exact source and patch; optionally apply to the specified copy."""
    checkout = checkout.resolve()
    if checkout == (ROOT / 'vendor/leanVM-b').resolve() and apply:
        raise ValueError('preserve the baseline checkout; apply to a separate profiled copy')
    path = checkout / SOURCE_PATH
    source = path.read_text()
    expected_patch = make_patch(source)
    if PATCH.read_text() != expected_patch:
        raise ValueError('profile.patch differs from the deterministic instrumentation')
    subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=checkout, check=True,
                   capture_output=True, text=True)
    changed = instrument_source(source)
    if apply:
        subprocess.run(['git', 'apply', str(PATCH)], cwd=checkout, check=True,
                       capture_output=True, text=True)
        if path.read_text() != changed:
            raise ValueError('applied instrumentation did not match expected source')
    return sha256(changed.encode())


def parse_phases(output: str, *, outer_prove_ms: float | None = None) -> dict:
    """Read exactly one record, including when libtest has prefixed its line."""
    records = re.findall(r'PHASES (\{[^\n]*\})', output)
    if len(records) != 1:
        raise ValueError(f'expected one PHASES record, found {len(records)}')
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate PHASES key: {key}')
            result[key] = value
        return result
    phases = json.loads(records[0], object_pairs_hook=unique_keys)
    expected = set(PHASE_KEYS) | {'profile_schema', 'scope', 'internal_total_ms', 'internal_residual_ms'}
    if set(phases) != expected or phases['profile_schema'] != 1 or phases['scope'] != SCOPE:
        raise ValueError('unexpected PHASES schema or timing scope')
    for key in (*PHASE_KEYS, 'internal_total_ms', 'internal_residual_ms'):
        value = phases[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'invalid phase duration: {key}')
    accounted = sum(phases[key] for key in PHASE_KEYS) + phases['internal_residual_ms']
    if not math.isclose(accounted, phases['internal_total_ms'], rel_tol=1e-10, abs_tol=1e-6):
        raise ValueError('exclusive phases and residual do not reconcile to the internal total')
    if outer_prove_ms is not None:
        if (isinstance(outer_prove_ms, bool) or not math.isfinite(outer_prove_ms)
                or outer_prove_ms < phases['internal_total_ms']):
            raise ValueError('outer prove duration must contain the internal timing scope')
        phases['outer_prove_residual_ms'] = outer_prove_ms - phases['internal_total_ms']
    return phases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--apply', action='store_true', help='apply after checking, to a separate checkout')
    args = parser.parse_args()
    digest = check_or_apply(args.checkout, apply=args.apply)
    print(json.dumps({'applied': args.apply, 'profiled_cpu_sha256': digest}))


if __name__ == '__main__':
    main()
