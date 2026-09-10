#!/usr/bin/env python3
"""Render the SVG publication masters as PNG review copies at twice the dimensions."""

from __future__ import annotations

import shutil
import os
import struct
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
EXPORTS = {
    "figure-1-private-owner-mechanism": (1800, 1100),
    "figure-2-state-anchor-results": (1800, 1100),
    "figure-3-leanvm-timing": (1800, 1400),
}
SHARP_NODE = Path(os.environ.get("SHARP_NODE", shutil.which("node") or "/nonexistent/node"))
SHARP_MODULE = Path(os.environ.get("SHARP_MODULE", str(ROOT / "node_modules" / "sharp")))


def find_browser() -> str:
    candidates = [
        shutil.which("brave-browser"),
        shutil.which("brave"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("Brave, Chrome, or Chromium is required to render the PNG copies")


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"not a valid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def render_with_sharp(stem: str, size: tuple[int, int]) -> str:
    width, height = size
    source = (FIGURES / f"{stem}.svg").resolve()
    output = (FIGURES / f"{stem}.png").resolve()
    script = """
const sharp = require(process.argv[1]);
const source = process.argv[2];
const output = process.argv[3];
const width = Number(process.argv[4]);
const height = Number(process.argv[5]);
sharp(source, { density: 144 })
  .resize(width, height, { fit: 'fill' })
  .png()
  .toFile(output)
  .catch(error => { console.error(error); process.exit(1); });
"""
    run = subprocess.run(
        [
            str(SHARP_NODE),
            "-e",
            script,
            str(SHARP_MODULE),
            str(source),
            str(output),
            str(width * 2),
            str(height * 2),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if run.returncode != 0:
        raise RuntimeError(f"sharp failed to render {source}:\n{run.stdout}{run.stderr}")
    observed = png_dimensions(output)
    expected = (width * 2, height * 2)
    if observed != expected:
        raise RuntimeError(f"{output} is {observed}, expected {expected}")
    return f"rendered {output.name} at {observed[0]} × {observed[1]}"


def render_with_browser(browser: str, stem: str, size: tuple[int, int]) -> str:
    width, height = size
    source = (FIGURES / f"{stem}.svg").resolve()
    output = (FIGURES / f"{stem}.png").resolve()
    with tempfile.TemporaryDirectory(prefix=f"state-anchor-{stem}-") as profile:
        run = subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--force-device-scale-factor=2",
                f"--window-size={width},{height}",
                f"--user-data-dir={profile}",
                f"--screenshot={output}",
                source.as_uri(),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    if run.returncode != 0:
        raise RuntimeError(f"browser failed to render {source}:\n{run.stdout}{run.stderr}")
    expected = (width * 2, height * 2)
    observed = png_dimensions(output)
    if observed != expected:
        raise RuntimeError(f"{output} is {observed}, expected {expected}")
    return f"rendered {output.name} at {observed[0]} × {observed[1]}"


def main() -> None:
    use_sharp = SHARP_NODE.is_file() and SHARP_MODULE.is_dir()
    browser = None if use_sharp else find_browser()
    with ThreadPoolExecutor(max_workers=len(EXPORTS)) as executor:
        if use_sharp:
            results = list(executor.map(lambda item: render_with_sharp(item[0], item[1]), EXPORTS.items()))
        else:
            assert browser is not None
            results = list(
                executor.map(
                    lambda item: render_with_browser(browser, item[0], item[1]),
                    EXPORTS.items(),
                )
            )
    print("\n".join(results))


if __name__ == "__main__":
    main()
