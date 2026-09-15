"""Descriptive checks of serial variation; no observations or estimates are replaced.

This diagnostic was added after the 80-round collection. It does not change the
predeclared t intervals or establish a new uncertainty model.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import statistics as st

from owner_state.analyze import analyze, csv_text


def products(directory):
    _, _, summary = analyze(directory)
    rows = []
    for comparison in summary['comparisons']:
        logs = [math.log(value) for value in comparison['block_ratios']]
        width = len(logs)//4
        rows.append({
            'numerator': comparison['numerator'], 'denominator': comparison['denominator'],
            'pairs': len(logs), 'quarter_size': width,
            'first_quarter_change_pct': 100*math.expm1(st.mean(logs[:width])),
            'last_quarter_change_pct': 100*math.expm1(st.mean(logs[-width:])),
            'lag1_log_ratio_correlation': st.correlation(logs[:-1], logs[1:]),
        })
    return csv_text(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = products(args.run)
    if args.check:
        if args.output.read_text() != data:
            raise ValueError('run-order diagnostics differ from raw evidence')
    else:
        args.output.write_text(data)


if __name__ == '__main__':
    main()
