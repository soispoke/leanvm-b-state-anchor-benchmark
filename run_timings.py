#!/usr/bin/env python3
"""Collect repeated leanVM-b timings with process-level session boundaries."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import platform
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PINNED_COMMIT = "8494c5d5df323f2b97ed89272942a4bee6247078"


def capture(args: list[str], *, cwd: Path | None = None) -> str:
    run = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    output = (run.stdout + run.stderr).strip()
    return output if output else "unavailable"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("leanvm", type=Path, help="leanVM-b checkout at the pinned commit")
    parser.add_argument("--sessions", type=positive, default=6)
    parser.add_argument("--repeats", type=positive, default=10)
    parser.add_argument("--warmups", type=positive, default=3)
    parser.add_argument("--threads", type=positive, default=11)
    parser.add_argument("--output", type=Path, default=ROOT / "timing-raw.txt")
    args = parser.parse_args()

    leanvm = args.leanvm.resolve()
    commit = capture(["git", "rev-parse", "HEAD"], cwd=leanvm)
    if commit != PINNED_COMMIT:
        raise SystemExit(f"leanVM-b must be at {PINNED_COMMIT}, found {commit}")
    tracked_changes = capture(["git", "status", "--short", "--untracked-files=no"], cwd=leanvm)
    if tracked_changes != "unavailable":
        raise SystemExit("leanVM-b has tracked changes; use a clean checkout for timing runs")

    source = ROOT / "timing_hash_bench.rs"
    runner = Path(__file__).resolve()
    analysis = ROOT / "analyze_timings.py"
    wrapper = leanvm / "tests" / "timing_hash_bench.rs"
    wrapper_text = f'#[path = "{source}"]\nmod timing_hash_bench;\n'
    if wrapper.exists() and wrapper.read_text() != wrapper_text:
        raise SystemExit(f"refusing to replace a different file: {wrapper}")
    wrapper.write_text(wrapper_text)

    cargo_lock = leanvm / "Cargo.lock"
    cargo_lock_hash = sha256(cargo_lock)
    metadata = [
        "TIMING_METADATA",
        f"collected_utc={dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"leanvm_commit={commit}",
        f"timing_source_sha256={sha256(source)}",
        f"runner_source_sha256={sha256(runner)}",
        f"analysis_source_sha256={sha256(analysis)}",
        f"cargo_lock_sha256={cargo_lock_hash}",
        f"sessions={args.sessions}",
        f"repeats_per_session={args.repeats}",
        f"warmups_per_case_per_session={args.warmups}",
        f"rayon_threads={args.threads}",
        f"platform={platform.platform()}",
        f"machine={platform.machine()}",
        f"logical_cpus={os.cpu_count()}",
        "rustc_begin",
        capture(["rustc", "-Vv"]),
        "rustc_end",
        "cargo_begin",
        capture(["cargo", "-V"]),
        "cargo_end",
        "hardware_begin",
        capture(["system_profiler", "SPHardwareDataType", "-detailLevel", "mini"]),
        "hardware_end",
        "power_begin",
        capture(["pmset", "-g", "batt"]),
        "power_end",
    ]

    transcript = ["\n".join(metadata)]
    env = os.environ.copy()
    env["RAYON_NUM_THREADS"] = str(args.threads)
    env["STATE_ANCHOR_TIMING_REPEATS"] = str(args.repeats)
    env["STATE_ANCHOR_TIMING_WARMUPS"] = str(args.warmups)
    for session in range(args.sessions):
        session_env = env.copy()
        session_env["STATE_ANCHOR_TIMING_SESSION"] = str(session)
        run = subprocess.run(
            [
                "cargo",
                "test",
                "--locked",
                "--release",
                "--test",
                "timing_hash_bench",
                "--",
                "--nocapture",
                "--test-threads=1",
            ],
            cwd=leanvm,
            env=session_env,
            capture_output=True,
            text=True,
            check=False,
        )
        transcript.append(f"SESSION_BEGIN {session}\n{run.stdout}{run.stderr}SESSION_END {session}")
        if run.returncode != 0:
            args.output.write_text("\n\n".join(transcript) + "\n")
            raise SystemExit(f"timing session {session} failed; partial transcript written to {args.output}")

    if sha256(cargo_lock) != cargo_lock_hash:
        raise SystemExit("Cargo.lock changed during the timing run")

    args.output.write_text("\n\n".join(transcript) + "\n")
    print(
        f"wrote {args.sessions * args.repeats * 24} samples from "
        f"{args.sessions} fresh process sessions to {args.output}"
    )


if __name__ == "__main__":
    main()
