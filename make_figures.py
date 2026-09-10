#!/usr/bin/env python3
"""Generate vector figures for the state anchor structural benchmark."""

from __future__ import annotations

import csv
import html
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
RESULTS = ROOT / "usecase-results.csv"
TIMING_RESULTS = ROOT / "timing-results.csv"
TIMING_RAW = ROOT / "timing-raw.txt"

INK = "#202124"
MUTED = "#5F6368"
LIGHT = "#E8EAED"
BLUE = "#0072B2"
BLUE_LIGHT = "#DCEEF8"
PURPLE = "#6F4C9B"
GREEN = "#008C6A"
GREEN_LIGHT = "#DDF3EB"
VERMILLION = "#C44E00"
GRAY_LIGHT = "#F1F3F4"
WHITE = "#FFFFFF"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def text(
    x: float,
    y: float,
    lines: object | list[object],
    *,
    size: int = 28,
    weight: int = 400,
    anchor: str = "start",
    fill: str = INK,
    line_height: float = 1.25,
    italic: bool = False,
) -> str:
    if not isinstance(lines, list):
        lines = [lines]
    spans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * line_height
        spans.append(f'<tspan x="{x}" dy="{dy}">{esc(line)}</tspan>')
    style = "italic" if italic else "normal"
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{fill}" '
        f'font-size="{size}" font-weight="{weight}" font-style="{style}">'
        + "".join(spans)
        + "</text>"
    )


def box(
    x: float,
    y: float,
    width: float,
    height: float,
    lines: list[str],
    *,
    stroke: str,
    fill: str,
    dash: bool = False,
    label: str | None = None,
) -> str:
    dashed = ' stroke-dasharray="10 8"' if dash else ""
    out = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="3"{dashed}/>'
    ]
    if label:
        out.append(text(x + 20, y + 29, label.upper(), size=20, weight=600))
        baseline = y + 65
    else:
        baseline = y + 43
    out.append(text(x + width / 2, baseline, lines, size=24, weight=500, anchor="middle"))
    return "".join(out)


def arrow(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    stroke: str = INK,
    dash: bool = False,
) -> str:
    dashed = ' stroke-dasharray="9 8"' if dash else ""
    marker = "arrow-blue" if stroke == BLUE else "arrow-ink"
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{stroke}" stroke-width="3"{dashed} marker-end="url(#{marker})"/>'
    )


def svg_document(width: int, height: int, title_value: str, description: str, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{esc(title_value)}</title>
<desc id="desc">{esc(description)}</desc>
<defs>
  <marker id="arrow-ink" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M 0 0 L 12 6 L 0 12 z" fill="{INK}"/>
  </marker>
  <marker id="arrow-blue" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M 0 0 L 12 6 L 0 12 z" fill="{BLUE}"/>
  </marker>
</defs>
<rect width="100%" height="100%" fill="{WHITE}"/>
<g font-family="Arial, Helvetica, sans-serif">{body}</g>
</svg>
'''


def write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def make_mechanism_figure() -> None:
    rows = {row["case"]: row for row in csv.DictReader(RESULTS.read_text().splitlines())}
    account_calls = int(rows["account_storage_word"]["direct_state_anchor_hashes"])
    tornado_calls = int(rows["tornado_recent_root"]["direct_state_anchor_hashes"])

    width, height = 1800, 1100
    parts: list[str] = []
    parts.append(text(60, 60, "Mechanism and benchmark scope", size=24, weight=600))
    parts.append(
        text(
            60,
            98,
            "The intended private relation is conceptual. The experiment validates real Ethereum proofs and runs only modeled hash counts in leanVM-b.",
            size=22,
            fill=MUTED,
        )
    )
    parts.append(f'<line x1="900" y1="140" x2="900" y2="970" stroke="{LIGHT}" stroke-width="3"/>')

    parts.append(text(60, 155, "a", size=28, weight=600))
    parts.append(text(105, 155, "Target private spend relation", size=24, weight=600))
    parts.append(text(105, 186, "not implemented", size=21, fill=MUTED))

    parts.append(box(70, 230, 350, 100, ["Pool root"], stroke=GREEN, fill=GREEN_LIGHT, label="public input"))
    parts.append(
        box(
            500,
            230,
            350,
            100,
            ["Execution state root"],
            stroke=BLUE,
            fill=BLUE_LIGHT,
            label="public input",
        )
    )
    parts.append(arrow(245, 330, 245, 395))
    parts.append(arrow(675, 330, 675, 395, stroke=BLUE))
    parts.append(
        box(
            55,
            395,
            380,
            145,
            ["Prove note membership", "cm = H(owner_addr, secret, …)"],
            stroke=MUTED,
            fill=GRAY_LIGHT,
            dash=True,
            label="hypothetical",
        )
    )
    parts.append(
        box(
            480,
            395,
            390,
            145,
            ["Prove account and storage", "owner_addr → H(verification key)"],
            stroke=MUTED,
            fill=GRAY_LIGHT,
            dash=True,
            label="hypothetical",
        )
    )
    parts.append(text(460, 620, "Both statements use the same hidden owner_addr", size=22, weight=600, anchor="middle"))
    parts.append(arrow(245, 540, 345, 690, dash=True))
    parts.append(arrow(675, 540, 575, 690, dash=True))
    parts.append(
        box(
            195,
            690,
            530,
            125,
            ["Authorize the complete transaction", "then expose nullifier and outputs"],
            stroke=MUTED,
            fill=GRAY_LIGHT,
            dash=True,
            label="not implemented",
        )
    )
    parts.append(
        text(
            80,
            885,
            [
                "The pool root and state root authenticate separate claims.",
                "A private proof must link them without revealing owner_addr.",
            ],
            size=22,
            fill=MUTED,
        )
    )

    parts.append(text(935, 155, "b", size=28, weight=600))
    parts.append(text(980, 155, "What the experiment ran", size=24, weight=600))
    parts.append(text(980, 186, "two examples from eight benchmark cases", size=21, fill=MUTED))
    parts.append(
        box(
            970,
            230,
            740,
            125,
            ["Tornado account + current index + root slot", f"{tornado_calls} modeled calls from a direct state root"],
            stroke=GREEN,
            fill=GREEN_LIGHT,
            label="real mainnet proof",
        )
    )
    parts.append(
        box(
            970,
            395,
            740,
            125,
            ["Safe account + slot 0 proof shape", f"{account_calls} modeled calls; slot holds a singleton, not H(vk)"],
            stroke=BLUE,
            fill=BLUE_LIGHT,
            label="real mainnet proof",
        )
    )
    parts.append(
        box(
            970,
            590,
            350,
            155,
            ["Real Keccak MPT", "and RLP header", "101 mutations rejected"],
            stroke=GREEN,
            fill=GREEN_LIGHT,
            label="Python validation",
        )
    )
    parts.append(
        box(
            1360,
            590,
            350,
            155,
            ["24 serial BLAKE3 chains", "count and output", "checks passed"],
            stroke=BLUE,
            fill=BLUE_LIGHT,
            label="leanVM-b execution",
        )
    )
    parts.append(
        box(
            970,
            815,
            740,
            130,
            ["No note membership, hidden owner link, authorization, or gas", "No end to end private proof timing"],
            stroke=MUTED,
            fill=GRAY_LIGHT,
            dash=True,
            label="scope",
        )
    )

    parts.append(
        text(
            60,
            1045,
            [
                "Panel a is an architecture sketch. Panel b shows two structural examples; Figure 2 reports all eight cases.",
                "Repeated leanVM-b calibration timing is reported in Figure 3.",
            ],
            size=21,
            fill=MUTED,
        )
    )

    document = svg_document(
        width,
        height,
        "Mechanism and benchmark scope",
        "Panel a is a conceptual private spend with separate note and Ethereum state branches linked by one hidden owner address; it was not implemented. Panel b shows the actual unrelated mainnet examples: a Tornado account, index, and root proof modeled at 248 calls, and a Safe account plus slot zero proof shape modeled at 141 calls. Python validates real Keccak proofs and the RLP header. leanVM-b runs 24 serial BLAKE3 chains, whose calibration timing is reported separately. No private relation, end to end private proof time, or gas is measured.",
        "".join(parts),
    )
    write_if_changed(FIGURES / "figure-1-private-owner-mechanism.svg", document)


def make_results_figure() -> None:
    rows = {row["case"]: row for row in csv.DictReader(RESULTS.read_text().splitlines())}
    sample = rows["account_storage_word"]
    direct_sample = int(sample["direct_state_anchor_hashes"])
    ssz_bridge = int(sample["ssz_block_anchor_hashes"]) - direct_sample
    rlp_bridge = int(sample["rlp_block_anchor_hashes"]) - direct_sample
    selected = [
        ("plain_eoa", "Plain account"),
        ("account_storage_word", "Safe account + slot 0"),
        ("safe_authorization", "Safe singleton + owner + threshold"),
        ("weth_balance", "WETH balance"),
        ("tornado_recent_root", "Tornado current index + root"),
        ("bayc_token_100_owner", "BAYC token 100 owner"),
        ("weth_and_bayc", "WETH + BAYC token 100"),
        ("native_weth_and_bayc", "ETH + WETH + BAYC token 100"),
    ]

    width, height = 1800, 1100
    parts: list[str] = []
    parts.append(text(60, 60, "Structural cost of authenticated state claims", size=24, weight=600))

    parts.append(text(60, 125, "a", size=28, weight=600))
    parts.append(text(105, 125, "Bridge overhead at the pinned block", size=24, weight=600))
    parts.append(text(105, 158, "add one value to each row in panel b", size=21, fill=MUTED))
    left_x, left_y, left_w = 105, 225, 430
    bridge_values = [
        ("Direct state root", "hypothetical exposure", 0, BLUE),
        ("EIP-7807 block root", "draft", ssz_bridge, PURPLE),
        ("Current RLP block hash", "available; 634 byte header here", rlp_bridge, VERMILLION),
    ]
    for index, (label, status, value, color) in enumerate(bridge_values):
        y = left_y + index * 140
        parts.append(text(left_x, y, label, size=23, weight=500))
        parts.append(text(left_x, y + 28, status, size=20, fill=MUTED))
        parts.append(
            f'<line x1="{left_x}" y1="{y + 70}" x2="{left_x + left_w}" y2="{y + 70}" '
            f'stroke="{LIGHT}" stroke-width="3"/>'
        )
        if value:
            bar_width = left_w * value / rlp_bridge
            parts.append(f'<rect x="{left_x}" y="{y + 51}" width="{bar_width}" height="38" fill="{color}"/>')
            value_x = left_x + bar_width + 14
        else:
            parts.append(f'<circle cx="{left_x + 5}" cy="{y + 70}" r="8" fill="{color}"/>')
            value_x = left_x + 28
        parts.append(text(value_x, y + 79, f"+{value}", size=24, weight=600))

    parts.append(
        box(
            85,
            675,
            480,
            150,
            ["Published Tornado root", "0 modeled state path calls", "registry check and private spend excluded"],
            stroke=GREEN,
            fill=GREEN_LIGHT,
            label="application specific shortcut",
        )
    )
    parts.append(
        text(
            105,
            865,
            ["This shortcut authenticates only that exact application root.", "It does not expose arbitrary Ethereum state."],
            size=21,
            fill=MUTED,
        )
    )

    parts.append(text(650, 125, "b", size=28, weight=600))
    parts.append(text(695, 125, "State path from a direct state root", size=24, weight=600))
    parts.append(text(695, 158, "one pinned mainnet snapshot", size=21, fill=MUTED))
    parts.append(text(1715, 158, "total = plotted value + panel a", size=21, anchor="end", fill=MUTED))

    plot_x, plot_y, plot_w, row_h = 1035, 215, 685, 88
    largest_total = max(int(rows[key]["direct_state_anchor_hashes"]) for key, _ in selected)
    max_x = 100 * ((largest_total + 99) // 100)
    axis_y = plot_y + row_h * len(selected) - 23
    for tick in range(0, max_x + 1, 100):
        x = plot_x + plot_w * tick / max_x
        parts.append(f'<line x1="{x}" y1="{axis_y}" x2="{x}" y2="{axis_y + 8}" stroke="{INK}" stroke-width="2"/>')
        parts.append(text(x, plot_y + row_h * len(selected) + 8, tick, size=20, anchor="middle", fill=MUTED))

    for index, (key, label) in enumerate(selected):
        value = int(rows[key]["direct_state_anchor_hashes"])
        y = plot_y + index * row_h
        parts.append(text(plot_x - 25, y + 29, label, size=21, anchor="end"))
        value_x = plot_x + plot_w * value / max_x
        baseline = y + 22
        parts.append(f'<line x1="{plot_x}" y1="{baseline}" x2="{value_x}" y2="{baseline}" stroke="{BLUE}" stroke-width="8"/>')
        parts.append(f'<circle cx="{value_x}" cy="{baseline}" r="9" fill="{BLUE}"/>')
        parts.append(text(value_x + 16, baseline + 8, value, size=21, weight=600))

    parts.append(f'<line x1="{plot_x}" y1="{axis_y}" x2="{plot_x + plot_w}" y2="{axis_y}" stroke="{INK}" stroke-width="2"/>')
    parts.append(text(plot_x + plot_w / 2, axis_y + 70, "Modeled native BLAKE3 calls", size=23, anchor="middle"))

    parts.append(
        text(
            60,
            1004,
            "Deterministic structural counts from block 25,939,968. No error bars: this is one snapshot, not a population estimate.",
            size=19,
            fill=MUTED,
        )
    )
    parts.append(
        text(
            60,
            1037,
            "Multi-claim rows hash identical encoded trie nodes once. This is a deduplication model, not an implemented multiproof.",
            size=19,
            fill=MUTED,
        )
    )
    parts.append(
        text(
            60,
            1070,
            "Keccak and SHA-256 are replaced uniformly with BLAKE3. Parsing, trie routing, private spend logic, time, and gas are excluded.",
            size=19,
            fill=MUTED,
        )
    )

    values = ", ".join(
        f"{label} {int(rows[key]['direct_state_anchor_hashes'])}" for key, label in selected
    )
    document = svg_document(
        width,
        height,
        "Structural cost of authenticated state claims",
        f"Panel a shows modeled bridge overhead at mainnet block 25,939,968: direct state root plus 0 calls, draft EIP-7807 block root plus 5, and the available current block hash plus 20 for this 634 byte RLP header. Panel b shows direct state root path counts: {values}. Publishing the exact Tornado root gives an application specific shortcut of zero modeled state path calls. Multi-claim rows hash identical encoded trie nodes once as a deduplication model, not an implemented multiproof. All values exclude parsing, trie routing, actual Keccak and SHA-256 costs, private spend logic, time, and gas.",
        "".join(parts),
    )
    write_if_changed(FIGURES / "figure-2-state-anchor-results.svg", document)


def marker(x: float, y: float, anchor: str, *, size: float = 8, opacity: float = 1.0) -> str:
    styles = {
        "direct_state": (BLUE, "circle"),
        "ssz_block": (PURPLE, "diamond"),
        "rlp_block": (VERMILLION, "square"),
    }
    color, shape = styles[anchor]
    if shape == "circle":
        return f'<circle cx="{x}" cy="{y}" r="{size}" fill="{color}" opacity="{opacity}"/>'
    if shape == "diamond":
        return (
            f'<polygon points="{x},{y - size} {x + size},{y} {x},{y + size} {x - size},{y}" '
            f'fill="{color}" opacity="{opacity}"/>'
        )
    return (
        f'<rect x="{x - size}" y="{y - size}" width="{2 * size}" height="{2 * size}" '
        f'fill="{color}" opacity="{opacity}"/>'
    )


def make_timing_figure() -> None:
    summaries = list(csv.DictReader(TIMING_RESULTS.read_text().splitlines()))
    by_key = {(row["case"], row["anchor"]): row for row in summaries}
    sample_pattern = re.compile(
        r"SAMPLE session=(\d+) pass=(\d+) order=(\d+) case=([a-z0-9_]+) "
        r"hashes=(\d+) blake3_domain=(\d+) cycles=(\d+) committed=(\d+) "
        r"log_mem=(\d+) mem_used=(\d+) proof_bytes=(\d+) prove_ns=(\d+) verify_ns=(\d+)"
    )
    raw_samples: dict[tuple[str, str], list[tuple[int, float, float]]] = {}
    for match in sample_pattern.finditer(TIMING_RAW.read_text()):
        full_name = match.group(4)
        for anchor in ("direct_state", "ssz_block", "rlp_block"):
            suffix = "_" + anchor
            if full_name.endswith(suffix):
                case = full_name[: -len(suffix)]
                raw_samples.setdefault((case, anchor), []).append(
                    (int(match.group(1)), int(match.group(12)) / 1_000_000, int(match.group(13)) / 1_000_000)
                )
                break

    anchors = ["direct_state", "ssz_block", "rlp_block"]
    cases = [
        ("plain_eoa", "Plain account"),
        ("account_storage_word", "Safe account + slot 0"),
        ("safe_authorization", "Safe singleton + owner + threshold"),
        ("weth_balance", "WETH balance"),
        ("tornado_recent_root", "Tornado current index + root"),
        ("bayc_token_100_owner", "BAYC token 100 owner"),
        ("weth_and_bayc", "WETH + BAYC token 100"),
        ("native_weth_and_bayc", "ETH + WETH + BAYC token 100"),
    ]

    width, height = 1800, 1400
    parts: list[str] = []
    parts.append(text(60, 58, "leanVM-b calibration: time, padding, and proof size", size=24, weight=600))
    parts.append(
        text(
            60,
            96,
            "60 samples per point across 6 fresh processes; 3 warmups and one untimed tamper check per case and process.",
            size=22,
            fill=MUTED,
        )
    )

    legend_x = 925
    legend_y = 130
    legend_items = [
        ("direct_state", "Direct state root", 250),
        ("ssz_block", "EIP-7807", 190),
        ("rlp_block", "Current RLP block hash", 0),
    ]
    for anchor, label, advance in legend_items:
        parts.append(marker(legend_x, legend_y, anchor, size=8))
        parts.append(text(legend_x + 18, legend_y + 7, label, size=20))
        legend_x += advance

    parts.append(text(60, 160, "a", size=28, weight=600))
    parts.append(text(105, 160, "Proving time by workload", size=24, weight=600))
    parts.append(
        text(
            1715,
            160,
            "60 runs/point; large marker = median of 6 process medians; line = 95% within-batch process bootstrap interval",
            size=20,
            anchor="end",
            fill=MUTED,
        )
    )

    plot_x, plot_y, plot_w, row_h = 550, 205, 1160, 57
    time_min = 25.0
    time_max = 65.0
    time_x = lambda value: plot_x + plot_w * (value - time_min) / (time_max - time_min)
    axis_y = plot_y + row_h * len(cases) - 17
    for tick in range(25, 66, 5):
        x = time_x(float(tick))
        parts.append(f'<line x1="{x}" y1="{axis_y}" x2="{x}" y2="{axis_y + 8}" stroke="{INK}" stroke-width="2"/>')
        parts.append(text(x, plot_y + row_h * len(cases) + 12, tick, size=20, anchor="middle", fill=MUTED))

    offsets = {"direct_state": -10, "ssz_block": 0, "rlp_block": 10}
    colors = {"direct_state": BLUE, "ssz_block": PURPLE, "rlp_block": VERMILLION}
    for case_index, (case, label) in enumerate(cases):
        center_y = plot_y + case_index * row_h + 18
        parts.append(text(plot_x - 28, center_y + 7, label, size=21, anchor="end"))
        for anchor in anchors:
            row = by_key[(case, anchor)]
            y = center_y + offsets[anchor]
            for sample_index, (session, prove_ms, _) in enumerate(raw_samples[(case, anchor)]):
                jitter = ((sample_index * 17 + session * 11) % 7 - 3) * 0.55
                parts.append(marker(time_x(prove_ms), y + jitter, anchor, size=3, opacity=0.30))
            low = time_x(float(row["prove_ms_ci_low"]))
            high = time_x(float(row["prove_ms_ci_high"]))
            median = time_x(float(row["prove_ms_median"]))
            parts.append(f'<line x1="{low}" y1="{y}" x2="{high}" y2="{y}" stroke="{colors[anchor]}" stroke-width="3"/>')
            parts.append(f'<line x1="{low}" y1="{y - 5}" x2="{low}" y2="{y + 5}" stroke="{colors[anchor]}" stroke-width="2"/>')
            parts.append(f'<line x1="{high}" y1="{y - 5}" x2="{high}" y2="{y + 5}" stroke="{colors[anchor]}" stroke-width="2"/>')
            parts.append(marker(median, y, anchor, size=6.5))

    parts.append(f'<line x1="{plot_x}" y1="{axis_y}" x2="{plot_x + plot_w}" y2="{axis_y}" stroke="{INK}" stroke-width="2"/>')
    parts.append(text(plot_x + plot_w / 2, axis_y + 62, "Proving time (ms)", size=23, anchor="middle"))
    parts.append(
        text(
            550,
            735,
            [
                "Committed witness size jumps at the same transitions:",
                "plain 125→130 calls: 196,672→239,680; Tornado 253→268: 262,208→348,224;",
                "WETH + BAYC 508→513: 393,280→565,312.",
            ],
            size=19,
            fill=MUTED,
        )
    )

    panel_y = 855
    panel_h = 300
    panel_width = 480
    panel_positions = [80, 660, 1240]
    x_min, x_max = 100.0, 700.0
    x_map = lambda left, value: left + panel_width * (value - x_min) / (x_max - x_min)

    parts.append(text(60, 825, "b", size=28, weight=600))
    parts.append(text(105, 825, "Committed witness cells (×10³)", size=24, weight=600))
    left = panel_positions[0]
    parts.append(f'<line x1="{left}" y1="{panel_y}" x2="{left}" y2="{panel_y + panel_h}" stroke="{INK}" stroke-width="2"/>')
    parts.append(f'<line x1="{left}" y1="{panel_y + panel_h}" x2="{left + panel_width}" y2="{panel_y + panel_h}" stroke="{INK}" stroke-width="2"/>')
    committed_min, committed_max = 180.0, 600.0
    committed_y = lambda value: panel_y + panel_h * (committed_max - value) / (committed_max - committed_min)
    for tick in (200, 300, 400, 500, 600):
        y = committed_y(float(tick))
        parts.append(f'<line x1="{left - 8}" y1="{y}" x2="{left}" y2="{y}" stroke="{INK}" stroke-width="2"/>')
        parts.append(text(left - 14, y + 7, tick, size=19, anchor="end", fill=MUTED))
    for case, _ in cases:
        points_for_case = []
        for anchor in anchors:
            row = by_key[(case, anchor)]
            x = x_map(left, float(row["hashes"]))
            y = committed_y(float(row["committed_cells"]) / 1000)
            points_for_case.append((x, y, anchor))
        parts.append(
            f'<polyline points="{" ".join(f"{x},{y}" for x, y, _ in points_for_case)}" '
            f'fill="none" stroke="{LIGHT}" stroke-width="2"/>'
        )
        for x, y, anchor in points_for_case:
            parts.append(marker(x, y, anchor, size=5))
    parts.append(text(left + panel_width / 2, panel_y + panel_h + 55, "Executed BLAKE3 calls", size=21, anchor="middle"))

    parts.append(text(640, 825, "c", size=28, weight=600))
    parts.append(text(685, 825, "Serialized proof size (kB)", size=24, weight=600))
    left = panel_positions[1]
    parts.append(f'<line x1="{left}" y1="{panel_y}" x2="{left}" y2="{panel_y + panel_h}" stroke="{INK}" stroke-width="2"/>')
    parts.append(f'<line x1="{left}" y1="{panel_y + panel_h}" x2="{left + panel_width}" y2="{panel_y + panel_h}" stroke="{INK}" stroke-width="2"/>')
    size_min, size_max = 455.0, 510.0
    size_y = lambda value: panel_y + panel_h * (size_max - value) / (size_max - size_min)
    for tick in (460, 480, 500):
        y = size_y(float(tick))
        parts.append(f'<line x1="{left - 8}" y1="{y}" x2="{left}" y2="{y}" stroke="{INK}" stroke-width="2"/>')
        parts.append(text(left - 14, y + 7, tick, size=19, anchor="end", fill=MUTED))
    for case, _ in cases:
        points_for_case = []
        for anchor in anchors:
            row = by_key[(case, anchor)]
            x = x_map(left, float(row["hashes"]))
            y = size_y(float(row["proof_bytes"]) / 1000)
            points_for_case.append((x, y, anchor))
        parts.append(
            f'<polyline points="{" ".join(f"{x},{y}" for x, y, _ in points_for_case)}" '
            f'fill="none" stroke="{LIGHT}" stroke-width="2"/>'
        )
        for x, y, anchor in points_for_case:
            parts.append(marker(x, y, anchor, size=5))
    parts.append(text(left + panel_width / 2, panel_y + panel_h + 55, "Executed BLAKE3 calls", size=21, anchor="middle"))

    parts.append(text(1220, 825, "d", size=28, weight=600))
    parts.append(text(1265, 825, "Warm verification time (ms)", size=24, weight=600))
    left = panel_positions[2]
    parts.append(f'<line x1="{left}" y1="{panel_y}" x2="{left}" y2="{panel_y + panel_h}" stroke="{INK}" stroke-width="2"/>')
    parts.append(f'<line x1="{left}" y1="{panel_y + panel_h}" x2="{left + panel_width}" y2="{panel_y + panel_h}" stroke="{INK}" stroke-width="2"/>')
    verify_min, verify_max = 4.5, 6.5
    verify_y = lambda value: panel_y + panel_h * (verify_max - value) / (verify_max - verify_min)
    for tick in (4.5, 5.0, 5.5, 6.0, 6.5):
        y = verify_y(tick)
        parts.append(f'<line x1="{left - 8}" y1="{y}" x2="{left}" y2="{y}" stroke="{INK}" stroke-width="2"/>')
        parts.append(text(left - 14, y + 7, tick, size=19, anchor="end", fill=MUTED))
    for row in summaries:
        x = x_map(left, float(row["hashes"]))
        low = verify_y(float(row["verify_ms_ci_high"]))
        high = verify_y(float(row["verify_ms_ci_low"]))
        median = verify_y(float(row["verify_ms_median"]))
        parts.append(f'<line x1="{x}" y1="{low}" x2="{x}" y2="{high}" stroke="{colors[row["anchor"]]}" stroke-width="2"/>')
        parts.append(marker(x, median, row["anchor"], size=5))
    parts.append(text(left + panel_width / 2, panel_y + panel_h + 55, "Executed BLAKE3 calls", size=21, anchor="middle"))

    for left in panel_positions:
        for tick in (100, 300, 500, 700):
            x = x_map(left, float(tick))
            parts.append(f'<line x1="{x}" y1="{panel_y + panel_h}" x2="{x}" y2="{panel_y + panel_h + 8}" stroke="{INK}" stroke-width="2"/>')
            parts.append(text(x, panel_y + panel_h + 24, tick, size=20, anchor="middle", fill=MUTED))

    parts.append(
        text(
            60,
            1315,
            "Apple M5 Max, 11 Rayon workers, AC power. The proving timer includes VM execution and proof witness generation.",
            size=20,
            fill=MUTED,
        )
    )
    parts.append(
        text(
            60,
            1352,
            "One-time setup, host-side input construction, and the untimed tamper check are excluded.",
            size=20,
            fill=MUTED,
        )
    )
    parts.append(
        text(
            60,
            1382,
            "Calibration programs only: no RLP, MPT, SSZ, Keccak, SHA-256, private logic, witness fetching, recursion, or gas.",
            size=20,
            fill=MUTED,
        )
    )

    document = svg_document(
        width,
        height,
        "leanVM-b calibration: time, padding, and proof size",
        "Six fresh leanVM-b processes produced sixty verified samples for each of twenty-four serial BLAKE3 workloads on one Apple M5 Max with eleven Rayon workers and AC power. Panel a plots all proving times with the median of process medians and a 95 percent within-batch process bootstrap interval across the six process medians. Median proving time rises from about 31 milliseconds at 125 calls to about 52 milliseconds near 636 calls, with visible jumps when leanVM commits a larger padded witness. Panel b shows committed witness cells, which include more than the BLAKE3 table alone. Panel c shows serialized proof sizes of about 460 to 506 kilobytes. Panel d shows warm verification medians of about 4.9 to 6.1 milliseconds. The programs execute native BLAKE3 but do not execute RLP, MPT, SSZ, Ethereum's Keccak or SHA-256 paths, private spend logic, recursion, or gas accounting.",
        "".join(parts),
    )
    write_if_changed(FIGURES / "figure-3-leanvm-timing.svg", document)


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    make_mechanism_figure()
    make_results_figure()
    make_timing_figure()
    print("wrote three state anchor benchmark SVG figures")


if __name__ == "__main__":
    main()
