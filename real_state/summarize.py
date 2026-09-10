"""Recompute the initial three-process timing summaries from preserved logs."""
import csv
import io
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def summarize():
    rows = []
    for mode in ('direct', 'rlp', 'ssz'):
        records, footprints = [], []
        for repetition in (1, 2, 3):
            text = (ROOT/'results'/f'{mode}-prove-{repetition}.txt').read_text()
            matches = re.findall(r'^RESULT (\{.*\})$', text, re.MULTILINE)
            if len(matches) != 1:
                raise ValueError(f'{mode}/{repetition}: expected one result')
            record = json.loads(matches[0])
            if record['action'] != 'prove' or not record['wrong_public_rejected'] or not record['mutated_proof_rejected']:
                raise ValueError('proof validation was not successful')
            records.append(record)
            footprints.append(int(re.search(r'(\d+)\s+peak memory footprint', text).group(1)))
        for key in ('cycles', 'counts', 'cells', 'mem_used', 'log_mem', 'committed', 'proof_bytes'):
            if any(row[key] != records[0][key] for row in records):
                raise ValueError(f'{mode}: deterministic field {key} changed')
        proving = [row['prove_including_execute_ms']/1000 for row in records]
        rows.append(dict(
            anchor=mode, samples=len(records), cycles=records[0]['cycles'],
            committed_cells=records[0]['committed'], proof_bytes=records[0]['proof_bytes'],
            prove_median_s=round(statistics.median(proving),6),
            prove_min_s=round(min(proving),6), prove_max_s=round(max(proving),6),
            verify_median_ms=round(statistics.median(row['verify_ms'] for row in records),3),
            assembly_median_ms=round(statistics.median(row['assembly_ms'] for row in records),3),
            peak_footprint_gib=round(max(footprints)/2**30,3),
        ))
    result = io.StringIO(newline='')
    writer = csv.DictWriter(result,fieldnames=rows[0],lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return result.getvalue()


if __name__ == '__main__':
    print(summarize(),end='')
