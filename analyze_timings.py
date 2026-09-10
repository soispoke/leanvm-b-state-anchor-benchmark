#!/usr/bin/env python3
"""Validate repeated timing samples and write robust per-case summaries."""

from __future__ import annotations

import csv
import io
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "timing-raw.txt"
RESULTS = ROOT / "usecase-results.csv"
OUTPUT = ROOT / "timing-results.csv"
BOOTSTRAP_REPLICATES = 20_000

ANCHORS = {
    "direct_state": "direct_state_anchor_hashes",
    "ssz_block": "ssz_block_anchor_hashes",
    "rlp_block": "rlp_block_anchor_hashes",
}

SAMPLE = re.compile(
    r"SAMPLE session=(\d+) pass=(\d+) order=(\d+) case=([a-z0-9_]+) "
    r"hashes=(\d+) blake3_domain=(\d+) cycles=(\d+) committed=(\d+) "
    r"log_mem=(\d+) mem_used=(\d+) proof_bytes=(\d+) prove_ns=(\d+) verify_ns=(\d+)"
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap_session_median(session_medians: list[float], seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    count = len(session_medians)
    estimates = [
        statistics.median(rng.choices(session_medians, k=count))
        for _ in range(BOOTSTRAP_REPLICATES)
    ]
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def split_case(name: str) -> tuple[str, str]:
    for anchor in ANCHORS:
        suffix = "_" + anchor
        if name.endswith(suffix):
            return name[: -len(suffix)], anchor
    raise ValueError(f"unknown timing case suffix: {name}")


def one_value(records: list[dict[str, int]], key: str, case: str) -> int:
    values = {record[key] for record in records}
    if len(values) != 1:
        raise ValueError(f"{case} has inconsistent {key}: {sorted(values)}")
    return values.pop()


def rounded(value: float) -> float:
    return round(value, 6)


def main() -> None:
    raw = RAW.read_text()
    configs = re.findall(
        r"TIMING_CONFIG session=(\d+) cases=(\d+) repeats=(\d+) warmups=(\d+) "
        r"order=deterministic_shuffled_passes",
        raw,
    )
    if not configs:
        raise SystemExit("timing transcript has no configuration records")
    sessions = {int(config[0]) for config in configs}
    case_counts = {int(config[1]) for config in configs}
    repeat_counts = {int(config[2]) for config in configs}
    warmup_counts = {int(config[3]) for config in configs}
    if sessions != set(range(len(configs))):
        raise SystemExit(f"timing sessions are not contiguous: {sorted(sessions)}")
    if len(case_counts) != 1 or len(repeat_counts) != 1 or len(warmup_counts) != 1:
        raise SystemExit("timing session configurations disagree")
    repeats = repeat_counts.pop()
    configured_cases = case_counts.pop()

    records_by_case: dict[str, list[dict[str, int]]] = defaultdict(list)
    seen: set[tuple[int, int, str]] = set()
    for match in SAMPLE.finditer(raw):
        fields = [
            "session",
            "pass",
            "order",
            "name",
            "hashes",
            "blake3_domain",
            "cycles",
            "committed",
            "log_mem",
            "mem_used",
            "proof_bytes",
            "prove_ns",
            "verify_ns",
        ]
        record: dict[str, int] = {
            key: int(value)
            for key, value in zip(fields, match.groups())
            if key != "name"
        }
        name = match.group(4)
        identity = (record["session"], record["pass"], name)
        if identity in seen:
            raise SystemExit(f"duplicate timing sample: {identity}")
        seen.add(identity)
        records_by_case[name].append(record)

    structural_rows = list(csv.DictReader(RESULTS.read_text().splitlines()))
    expected: dict[str, int] = {}
    case_order: dict[str, int] = {}
    for index, row in enumerate(structural_rows):
        case_order[row["case"]] = index
        for anchor, column in ANCHORS.items():
            expected[f"{row['case']}_{anchor}"] = int(row[column])
    if set(records_by_case) != set(expected):
        raise SystemExit(
            "timing cases do not match structural results: "
            f"missing={sorted(set(expected) - set(records_by_case))}, "
            f"extra={sorted(set(records_by_case) - set(expected))}"
        )
    if configured_cases != len(expected):
        raise SystemExit(f"timing config declares {configured_cases} cases, expected {len(expected)}")
    for session in sessions:
        for sample in range(repeats):
            pass_records = [
                record
                for records in records_by_case.values()
                for record in records
                if record["session"] == session and record["pass"] == sample
            ]
            if {record["order"] for record in pass_records} != set(range(configured_cases)):
                raise SystemExit(f"session {session} pass {sample} has an invalid execution order")

    rows: list[dict[str, int | float | str]] = []
    for name, expected_hashes in expected.items():
        records = records_by_case[name]
        expected_samples = len(sessions) * repeats
        if len(records) != expected_samples:
            raise SystemExit(f"{name} has {len(records)} samples, expected {expected_samples}")
        expected_pairs = {(session, sample) for session in sessions for sample in range(repeats)}
        observed_pairs = {(record["session"], record["pass"]) for record in records}
        if observed_pairs != expected_pairs:
            raise SystemExit(f"{name} does not cover every session and pass")
        if {record["hashes"] for record in records} != {expected_hashes}:
            raise SystemExit(f"{name} hash count disagrees with structural results")
        if {record["cycles"] for record in records} != {20 + 24 * expected_hashes}:
            raise SystemExit(f"{name} cycle count is wrong")
        expected_domain = 1 << (expected_hashes - 1).bit_length()
        if {record["blake3_domain"] for record in records} != {expected_domain}:
            raise SystemExit(f"{name} BLAKE3 domain is wrong")

        prove_ms = [record["prove_ns"] / 1_000_000 for record in records]
        verify_ms = [record["verify_ns"] / 1_000_000 for record in records]
        session_prove_medians = [
            statistics.median(
                record["prove_ns"] / 1_000_000
                for record in records
                if record["session"] == session
            )
            for session in sorted(sessions)
        ]
        session_verify_medians = [
            statistics.median(
                record["verify_ns"] / 1_000_000
                for record in records
                if record["session"] == session
            )
            for session in sorted(sessions)
        ]
        seed = sum((index + 1) * ord(char) for index, char in enumerate(name))
        prove_ci_low, prove_ci_high = bootstrap_session_median(session_prove_medians, seed)
        verify_ci_low, verify_ci_high = bootstrap_session_median(session_verify_medians, seed + 1)
        base_case, anchor = split_case(name)
        rows.append(
            {
                "case": base_case,
                "anchor": anchor,
                "hashes": expected_hashes,
                "blake3_domain": expected_domain,
                "cycles": 20 + 24 * expected_hashes,
                "committed_cells": one_value(records, "committed", name),
                "log_mem": one_value(records, "log_mem", name),
                "mem_used": one_value(records, "mem_used", name),
                "sessions": len(sessions),
                "samples": len(records),
                "prove_ms_median": rounded(statistics.median(session_prove_medians)),
                "prove_ms_ci_low": rounded(prove_ci_low),
                "prove_ms_ci_high": rounded(prove_ci_high),
                "prove_ms_q1": rounded(percentile(prove_ms, 0.25)),
                "prove_ms_q3": rounded(percentile(prove_ms, 0.75)),
                "verify_ms_median": rounded(statistics.median(session_verify_medians)),
                "verify_ms_ci_low": rounded(verify_ci_low),
                "verify_ms_ci_high": rounded(verify_ci_high),
                "verify_ms_q1": rounded(percentile(verify_ms, 0.25)),
                "verify_ms_q3": rounded(percentile(verify_ms, 0.75)),
                "proof_bytes": one_value(records, "proof_bytes", name),
            }
        )

    anchor_order = {name: index for index, name in enumerate(ANCHORS)}
    rows.sort(key=lambda row: (case_order[str(row["case"])], anchor_order[str(row["anchor"])]))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    content = buffer.getvalue()
    if not OUTPUT.exists() or OUTPUT.read_text() != content:
        OUTPUT.write_text(content)
    print(
        f"wrote {len(rows)} summaries from {len(sessions)} sessions and "
        f"{len(seen)} verified timing samples to {OUTPUT}"
    )


if __name__ == "__main__":
    main()
