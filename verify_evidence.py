#!/usr/bin/env python3
"""Verify preserved evidence and regenerate summaries without changing it."""

from __future__ import annotations

import csv
import hashlib
import math
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import analyze_timings
import make_figures
from check_artifacts import png_dimensions


ROOT = Path(__file__).resolve().parent
REPEAT = ROOT / "reruns" / "2026-09-09-independent-repeat"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify_hashes() -> None:
    seen: set[str] = set()
    for line in (ROOT / "evidence-sha256.txt").read_text().splitlines():
        expected, name = line.split("  ", 1)
        require(name not in seen, f"duplicate manifest entry: {name}")
        seen.add(name)
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        require(actual == expected, f"evidence SHA-256 mismatch: {name}")
    require(len(seen) == 28, "incomplete original evidence manifest")
    print(f"OK: {len(seen)} original evidence files match SHA-256 manifest", flush=True)


def verify_batches() -> list[str]:
    transcripts = [(directory / "timing-raw.txt").read_text() for directory in (ROOT, REPEAT)]
    metadata_keys = (
        "leanvm_commit", "cargo_lock_sha256", "timing_source_sha256",
        "runner_source_sha256", "analysis_source_sha256", "sessions",
        "repeats_per_session", "warmups_per_case_per_session", "rayon_threads",
        "platform", "machine", "logical_cpus",
    )
    for key in metadata_keys:
        values = [re.findall(rf"^{key}=(.+)$", raw, re.MULTILINE) for raw in transcripts]
        require(len(values[0]) == len(values[1]) == 1 and values[0] == values[1],
                f"batch metadata mismatch: {key}")
    for block in ("rustc", "cargo"):
        values = [re.findall(rf"{block}_begin\n(.*?)\n{block}_end", raw, re.DOTALL)
                  for raw in transcripts]
        require(len(values[0]) == len(values[1]) == 1 and values[0] == values[1],
                f"batch toolchain mismatch: {block}")
    samples = [[match.groups() for match in analyze_timings.SAMPLE.finditer(raw)]
               for raw in transcripts]
    require(len(samples[0]) == len(samples[1]) == 1440, "expected 1,440 samples per batch")
    require([sample[:-2] for sample in samples[0]] == [sample[:-2] for sample in samples[1]],
            "paired workload order or deterministic sample fields differ")
    for raw in transcripts:
        require(re.findall(r"^SESSION_BEGIN (\d+)$", raw, re.MULTILINE) == list(map(str, range(6))),
                "missing or duplicate process session")
        require(re.findall(r"^SESSION_END (\d+)$", raw, re.MULTILINE) == list(map(str, range(6))),
                "incomplete process session")
        require(raw.count("test result: ok. 1 passed; 0 failed;") == 6,
                "missing successful Rust test result")
        require("Now drawing from 'AC Power'" in raw, "AC power record missing")
    for batch in samples:
        for session in range(6):
            medians = {}
            for count in (508, 513):
                values = [int(sample[-2]) for sample in batch
                          if int(sample[0]) == session and int(sample[4]) == count]
                require(len(values) == 10, "incomplete padding boundary measurements")
                medians[count] = statistics.median(values)
            require(medians[513] > medians[508], "padding jump missing in a process session")
    print("OK: all 1,440 paired deterministic records match; padding jump in all 12 sessions", flush=True)
    return transcripts


def verify_comparison() -> None:
    original = rows(ROOT / "timing-results.csv")
    repeat = rows(REPEAT / "timing-results.csv")
    comparison = rows(REPEAT / "comparison.csv")
    require(len(original) == len(repeat) == len(comparison) == 24, "comparison row count differs")
    for first, second, saved in zip(original, repeat, comparison):
        for key in ("case", "anchor", "hashes", "committed_cells"):
            require(first[key] == second[key] == saved[key], f"comparison mismatch: {key}")
        for metric in ("prove", "verify"):
            a, b = float(first[f"{metric}_ms_median"]), float(second[f"{metric}_ms_median"])
            expected = {f"original_{metric}_ms": a, f"repeat_{metric}_ms": b,
                        f"{metric}_change_percent": (b / a - 1) * 100}
            for key, value in expected.items():
                require(math.isclose(float(saved[key]), value, rel_tol=0, abs_tol=0.000001),
                        f"comparison mismatch for {saved['case']}/{saved['anchor']}: {key}")
    shift = statistics.median(float(row["prove_change_percent"]) for row in comparison)
    jumps = []
    for batch in (original, repeat):
        medians = {int(row["hashes"]): float(row["prove_ms_median"]) for row in batch}
        jumps.append((medians[513] / medians[508] - 1) * 100)
    print(f"OK: comparison CSV; 508 → 513: {jumps[0]:.2f}% / {jumps[1]:.2f}%; "
          f"median proving shift: {shift:+.2f}%", flush=True)


def main() -> None:
    verify_hashes()
    subprocess.run([sys.executable, str(ROOT / "check_artifacts.py")], check=True)
    verify_batches()
    with tempfile.TemporaryDirectory(prefix="state-anchor-repeat-") as directory:
        output = Path(directory)
        analyze_timings.RAW = REPEAT / "timing-raw.txt"
        analyze_timings.OUTPUT = output / "timing-results.csv"
        analyze_timings.main()
        require(rows(analyze_timings.OUTPUT) == rows(REPEAT / "timing-results.csv"),
                "repeat timing summary differs from raw samples")
        make_figures.TIMING_RAW = REPEAT / "timing-raw.txt"
        make_figures.TIMING_RESULTS = REPEAT / "timing-results.csv"
        make_figures.FIGURES = output
        make_figures.make_timing_figure()
        figure = "figure-3-leanvm-timing.svg"
        require((output / figure).read_bytes() == (REPEAT / figure).read_bytes(),
                "repeat timing SVG differs from its data")
    require(png_dimensions(REPEAT / "figure-3-leanvm-timing.png") == (3600, 2800),
            "repeat PNG dimensions differ")
    verify_comparison()
    print("OK: complete evidence bundle verified (2,880 timing samples, four SVG/PNG figures)")


if __name__ == "__main__":
    main()
