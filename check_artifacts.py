#!/usr/bin/env python3
"""Check that generated counts, leanVM-b cases, and recorded runs agree."""

from __future__ import annotations

import csv
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent
PNG_DIMENSIONS = {
    "figure-1-private-owner-mechanism": (3600, 2200),
    "figure-2-state-anchor-results": (3600, 2200),
    "figure-3-leanvm-timing": (3600, 2800),
}


def fail(message: str) -> None:
    raise SystemExit(message)


def unique_mapping(pairs: list[tuple[str, object]], label: str) -> dict[str, object]:
    names = [name for name, _ in pairs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        fail(f"duplicate {label}: {duplicates}")
    return dict(pairs)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        fail(f"not a valid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def check() -> None:
    unit_tests = subprocess.run(
        [sys.executable, str(ROOT / "test_analyze_fixtures.py"), "-q"],
        check=True,
        capture_output=True,
        text=True,
    )
    unit_test_match = re.search(r"Ran (\d+) tests?", unit_tests.stdout + unit_tests.stderr)
    if unit_test_match is None:
        fail("could not determine the MPT unit test count")
    unit_test_count = int(unit_test_match.group(1))
    run = subprocess.run(
        [sys.executable, str(ROOT / "analyze_fixtures.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    recorded_csv = (ROOT / "usecase-results.csv").read_text()
    if run.stdout != recorded_csv:
        fail("usecase-results.csv does not match analyze_fixtures.py")
    recorded_validation = [
        line
        for line in (ROOT / "usecase-validation.txt").read_text().splitlines()
        if line.startswith("VALIDATION ")
    ]
    if recorded_validation != [run.stderr.strip()]:
        fail("usecase-validation.txt does not contain exactly the current validation line")

    rows = list(csv.DictReader(recorded_csv.splitlines()))
    row_names = [row["case"] for row in rows]
    if len(row_names) != len(set(row_names)):
        fail("usecase-results.csv contains duplicate case names")
    expected: dict[str, int] = {}
    for row in rows:
        prefix = row["case"]
        expected[f"{prefix}_direct_state"] = int(row["direct_state_anchor_hashes"])
        expected[f"{prefix}_ssz_block"] = int(row["ssz_block_anchor_hashes"])
        expected[f"{prefix}_rlp_block"] = int(row["rlp_block_anchor_hashes"])

    source = (ROOT / "usecase_hash_bench.rs").read_text()
    declared = unique_mapping(
        [
            (name, int(hashes))
            for name, hashes in re.findall(
                r'Case\s*\{\s*name:\s*"([a-z0-9_]+)",\s*hashes:\s*(\d+)',
                source,
            )
        ],
        "Rust case names",
    )
    if declared != expected:
        fail(f"Rust cases do not match the CSV: expected={expected}, declared={declared}")

    raw = (ROOT / "usecase-leanvm-results.txt").read_text()
    if "Result: all 24 chain proofs verified" not in raw:
        fail("recorded leanVM-b transcript does not contain its success summary")
    observed = unique_mapping(
        [
            (name, (int(hashes), int(cycles)))
            for name, hashes, cycles in re.findall(
                r"RESULT case=([a-z0-9_]+) hashes=(\d+) cycles=(\d+)",
                raw,
            )
        ],
        "recorded RESULT names",
    )
    if set(observed) != set(expected):
        fail(
            "recorded leanVM-b cases do not match the Rust cases: "
            f"missing={sorted(set(expected) - set(observed))}, "
            f"extra={sorted(set(observed) - set(expected))}"
        )
    for name, hashes in expected.items():
        observed_hashes, cycles = observed[name]
        if observed_hashes != hashes:
            fail(f"{name} records {observed_hashes} hashes, expected {hashes}")
        if cycles != 20 + 24 * hashes:
            fail(f"{name} records {cycles} cycles, expected {20 + 24 * hashes}")

    timing_source = ROOT / "timing_hash_bench.rs"
    timing_declared = unique_mapping(
        [
            (name, int(hashes))
            for name, hashes in re.findall(
                r'Case\s*\{\s*name:\s*"([a-z0-9_]+)",\s*hashes:\s*(\d+)',
                timing_source.read_text(),
            )
        ],
        "timing Rust case names",
    )
    if timing_declared != expected:
        fail(f"timing Rust cases do not match the CSV: expected={expected}, declared={timing_declared}")

    timing_raw = (ROOT / "timing-raw.txt").read_text()
    recorded_hashes = {
        label: re.search(rf"^{label}=([0-9a-f]{{64}})$", timing_raw, re.MULTILINE)
        for label in (
            "timing_source_sha256",
            "runner_source_sha256",
            "analysis_source_sha256",
        )
    }
    expected_hashes = {
        "timing_source_sha256": sha256(timing_source),
        "runner_source_sha256": sha256(ROOT / "run_timings.py"),
        "analysis_source_sha256": sha256(ROOT / "analyze_timings.py"),
    }
    for label, expected_hash in expected_hashes.items():
        match = recorded_hashes[label]
        if match is None or match.group(1) != expected_hash:
            fail(f"timing transcript has a stale or missing {label}")
    recorded_timing = (ROOT / "timing-results.csv").read_bytes()
    timing_analysis = subprocess.run(
        [sys.executable, str(ROOT / "analyze_timings.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    if (ROOT / "timing-results.csv").read_bytes() != recorded_timing:
        fail("timing-results.csv does not match the recorded timing samples")
    timing_rows = list(csv.DictReader((ROOT / "timing-results.csv").read_text().splitlines()))
    timing_samples = sum(int(row["samples"]) for row in timing_rows)
    if len(timing_rows) != len(expected):
        fail(f"timing-results.csv has {len(timing_rows)} rows, expected {len(expected)}")
    if timing_samples != 1_440:
        fail(f"timing-results.csv summarizes {timing_samples} samples, expected 1440")
    if "1440 verified timing samples" not in timing_analysis.stdout:
        fail("timing analyzer did not report the expected sample count")

    recorded_svgs = {p: p.read_bytes() for p in (ROOT / "figures").glob("*.svg")}
    subprocess.run(
        [sys.executable, str(ROOT / "make_figures.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    for path, original in recorded_svgs.items():
        if path.read_bytes() != original:
            fail(f"{path.name} does not match the recorded data")
    for stem, dimensions in PNG_DIMENSIONS.items():
        svg = ROOT / "figures" / f"{stem}.svg"
        png = ROOT / "figures" / f"{stem}.png"
        ElementTree.parse(svg)
        if not png.exists():
            fail(f"missing PNG export: {png}")
        if png_dimensions(png) != dimensions:
            fail(f"{png.name} has dimensions {png_dimensions(png)}, expected {dimensions}")

    print(
        f"OK: {unit_test_count} MPT unit tests, {len(rows)} structural cases, "
        f"{len(expected)} leanVM-b chain runs, {timing_samples} timing samples, "
        "CSV files, transcripts, and three figures agree"
    )


def main() -> None:
    global ROOT
    source = ROOT
    try:
        with tempfile.TemporaryDirectory(prefix="state-anchor-check-") as directory:
            ROOT = Path(directory)
            for path in source.iterdir():
                if path.is_file() and not path.name.startswith("."):
                    shutil.copy2(path, ROOT / path.name)
            for name in ("fixtures", "figures"):
                shutil.copytree(source / name, ROOT / name)
            check()
    finally:
        ROOT = source


if __name__ == "__main__":
    main()
