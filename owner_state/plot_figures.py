"""Publication figures for the measured owner-binding relation.

python -m owner_state.plot_figures --run owner_state/results/collect-<id>
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import statistics as st
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle

from owner_state.analyze import HERE, MODES, analyze
from real_state.plot_figures import export as export_base

MM = 1 / 25.4
WIDTH = 180
INK, MUTED, RULE = '#202124', '#50575D', '#C9CED2'
COLORS = ('#007C66', '#0067A5', '#C45A00')
NAMES = ('Direct state root', 'RLP block hash', 'SSZ summary*')
STEMS = ('figure-1-owner-binding', 'figure-2-proving-results', 'figure-3-cost-breakdown')
plt.rcParams.update({
    'font.family': ['DejaVu Sans', 'sans-serif'], 'font.size': 7,
    'axes.labelsize': 7, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
    'text.color': INK, 'axes.labelcolor': INK,
    'xtick.color': INK, 'ytick.color': INK,
    'axes.linewidth': .6, 'xtick.major.width': .6, 'ytick.major.width': .6,
    'xtick.major.size': 2.5, 'ytick.major.size': 2.5,
    'svg.fonttype': 'none', 'svg.hashsalt': 'owner-binding-figures-v2',
    'pdf.fonttype': 42, 'ps.fonttype': 42,
    'savefig.facecolor': 'white', 'figure.facecolor': 'white',
})


def figure(height):
    return plt.figure(figsize=(WIDTH * MM, height * MM))


def text(fig, x, y, value, *, bold=False, size=7, color=INK, **kwargs):
    height = fig.get_size_inches()[1] / MM
    return fig.text(x / WIDTH, y / height, value, fontsize=size,
                    fontweight='bold' if bold else 'normal', color=color, **kwargs)


def title(fig, letter, value, y):
    text(fig, 5, y, letter, size=8, bold=True, va='center')
    text(fig, 11, y, value, bold=True, va='center')


def axes(fig, rect):
    x, y, w, h = rect
    height = fig.get_size_inches()[1] / MM
    ax = fig.add_axes([x / WIDTH, y / height, w / WIDTH, h / height])
    ax.spines[['top', 'right']].set_visible(False)
    return ax


def export(fig, path, description):
    # Ignore locator ticks beyond the visible limits in the shared bounds check.
    for ax in fig.axes:
        if ax.axison:
            lo, hi = sorted(ax.get_xlim())
            ax.set_xticks([v for v in ax.get_xticks() if lo <= v <= hi])
            lo, hi = sorted(ax.get_ylim())
            ax.set_yticks([v for v in ax.get_yticks() if lo <= v <= hi])
    export_base(fig, path, description)


def measured_rows(samples, mode, variant):
    return sorted((row for row in samples if row['kind'] == 'measured'
                   and row['mode'] == mode and row['variant'] == variant),
                  key=lambda row: row['block'])


def schematic(destination):
    fig = figure(139)
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, WIDTH), ylim=(0, 139))
    ax.set_axis_off()

    def box(x, y, w, h, lines, *, edge=RULE, emphasis=False):
        ax.add_patch(Rectangle((x-w/2, y-h/2), w, h, facecolor='white',
                               edgecolor=edge, lw=.7))
        ax.text(x, y, lines, ha='center', va='center', fontsize=7,
                fontweight='bold' if emphasis else 'normal', linespacing=1.55)

    def arrow(start, end):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>',
                                    mutation_scale=7, color=INK, linewidth=.7))

    title(fig, 'a', 'One address links the note to the authenticated account', 132)
    box(30, 109, 48, 24, 'Witness inputs\nOwner address + secret')
    box(119, 119, 110, 18,
        'Open the public note commitment\nH = Keccak-256(owner address || secret)')
    box(119, 96, 110, 18,
        'Authenticate that same address\nAccount and storage lookup under the selected root')
    arrow((54, 115), (64, 119))
    arrow((54, 103), (64, 96))
    text(fig, 6, 80, 'Public inputs: anchor type, anchor root/hash, note commitment H and storage slot.', color=MUTED)

    title(fig, 'b', 'Change the anchor; keep the same account and storage proofs', 69)
    centers = (32, 90, 148)
    details = ('No header check', 'Parse the RLP header\nHash with Keccak-256',
               'Check the state-root branch\n5 SHA-256 pair hashes')
    for x, name, detail, color in zip(centers, NAMES, details, COLORS):
        ax.add_patch(Rectangle((x-26, 39), 52, 24, facecolor='white', edgecolor=color, lw=.8))
        ax.plot([x-26, x+26], [56, 56], color=color, linewidth=.6)
        ax.text(x, 59.5, name, ha='center', va='center', fontsize=7, fontweight='bold')
        ax.text(x, 47.5, detail, ha='center', va='center', fontsize=7, linespacing=1.55)
        ax.plot([x, x], [39, 34], color=INK, lw=.7)
    ax.plot([32, 148], [34, 34], color=INK, lw=.7)
    arrow((90, 34), (90, 27))
    ax.text(94, 30.5, 'Same state root', fontsize=7, va='center')
    box(90, 19, 168, 16,
        'Same Keccak account and storage proofs\nState root → account → storage → authenticated word')
    text(fig, 6, 6.3, 'Binding is tested. Owner privacy and transaction authorization are not implemented.', size=6.5)
    text(fig, 6, 2.2, '*Hypothetical SSZ summary. Both state tries remain Keccak.', size=6.5, color=MUTED)
    export(fig, destination/STEMS[0], 'One note-owner relation, three state anchors; only header authentication changes')


def proving(destination, samples, summary):
    fig = figure(136)
    title(fig, 'a', 'Proving time for the same note-owner claim', 129)
    text(fig, 11, 122.5, '24 measured proofs: 8 per anchor. Dots are runs; black ticks mark medians.', color=MUTED)
    text(fig, 6, 113, 'Anchor', bold=True)
    text(fig, 165, 113, 'Median (s)', bold=True, ha='center')
    a = axes(fig, (50, 77, 97, 30))
    a.spines['left'].set_visible(False)
    a.tick_params(axis='y', left=False, labelleft=False)
    times = [row['prove_s'] for row in samples
             if row['kind']=='measured' and row['variant']=='cse_dce']
    time_lo = math.floor((min(times)-.15)*2)/2
    time_hi = math.ceil((max(times)+.15)*2)/2
    a.set(xlim=(time_lo, time_hi+.1), ylim=(-.5, 2.5),
          xticks=[time_lo+j*.5 for j in range(round((time_hi-time_lo)*2)+1)],
          xlabel='Complete proving time (s)')
    # Separate nearby dots in physical units, without changing their time values.
    x_scale = a.bbox.width / fig.dpi * 72 / (time_hi+.1-time_lo)
    y_scale = a.bbox.height / fig.dpi * 72 / 3
    for i, (mode, color, name) in enumerate(zip(MODES, COLORS, NAMES)):
        values = sorted(row['prove_s'] for row in measured_rows(samples, mode, 'cse_dce'))
        placed = []
        for value in values:
            for level in (0, 1, -1, 2, -2, 3, -3, 4):
                offset = level * 5 / y_scale
                if all(((value-x)*x_scale)**2 + ((offset-y)*y_scale)**2 >= 25
                       for x, y in placed):
                    break
            if abs(offset) > .4:
                raise ValueError('Insufficient row height to show every proof marker')
            placed.append((value, offset))
        a.scatter([value for value, _ in placed], [2-i+offset for _, offset in placed],
                  s=18, facecolor=color, edgecolor='white', linewidth=.4, zorder=3)
        median = summary['conditions'][f'cse_dce/{mode}']['prove_median_s']
        a.plot([median, median], [2-i-.3, 2-i+.3], color=INK, lw=1, zorder=5)
        ym = 77+(2-i+.5)/3*30
        text(fig, 6, ym, name, bold=True, va='center')
        text(fig, 165, ym, f'{median:.2f}', bold=True, va='center', ha='center')

    title(fig, 'b', 'Both block anchors add about 10%; SSZ has no resolved advantage', 62)
    text(fig, 11, 55.5, 'Points: paired time change. Bars: 95% within-batch intervals (8 pairs).', size=6.5, color=MUTED)
    b = axes(fig, (50, 21, 97, 29))
    b.spines['left'].set_visible(False)
    b.tick_params(axis='y', left=False, labelleft=False)
    b.axvline(0, color=INK, lw=.65, linestyle=(0, (3, 3)))
    comparisons = [('cse_dce/rlp', 'cse_dce/direct', 'RLP vs direct state', COLORS[1]),
                   ('cse_dce/ssz', 'cse_dce/direct', 'SSZ vs direct state', COLORS[2]),
                   ('cse_dce/ssz', 'cse_dce/rlp', 'SSZ vs RLP', INK)]
    for i, (num, den, label, color) in enumerate(comparisons):
        result = next(row for row in summary['comparisons'] if row['numerator']==num and row['denominator']==den)
        center, lo, hi = [100*(result[key]-1) for key in ('ratio', 'ci95_low', 'ci95_high')]
        y=2-i
        b.errorbar(center, y, xerr=[[center-lo], [hi-center]], fmt='o', color=color,
                   markersize=4.5, elinewidth=1, capsize=2.5, capthick=.8)
        ym=21+(y+.5)/3*29
        text(fig, 6, ym, label, va='center')
        text(fig, 165, ym+1.5, f'{center:+.1f}%', ha='center', va='center', bold=True)
        text(fig, 165, ym-2.2, f'[{lo:+.1f}, {hi:+.1f}]', ha='center', va='center', size=6.5, color=MUTED)
    b.set(xlim=(-5, 17), ylim=(-.5, 2.5), xticks=[-5, 0, 5, 10, 15],
          xlabel='Change in proving time (%)')
    text(fig, 6, 6.3, 'Apple M5 Max · 11 workers · AC power. One mainnet fixture with a fixed proof shape.', size=6.5)
    text(fig, 6, 2.2, '*Hypothetical SSZ summary; both state tries remain Keccak.', size=6.5, color=MUTED)
    export(fig, destination/STEMS[1], 'All 24 optimized-program proof measurements and paired anchor comparisons')


def costs(destination, samples, summary):
    fig = figure(112)
    title(fig, 'a', 'Most time is spent constructing the proof', 106)
    text(fig, 11, 99.5, 'Arithmetic means of 8 runs per anchor. Phase times do not overlap.', color=MUTED)
    phase_colors=('#5DAB97', '#BDC7CE', '#3D6F95')
    fig.legend(handles=[Patch(facecolor=color, label=name) for color, name in zip(phase_colors,
               ('VM execution', 'Witness tables', 'Proof work + cleanup'))],
               loc='center left', bbox_to_anchor=(31/WIDTH, 92.5/112), ncol=3, frameon=False,
               fontsize=7, borderaxespad=0, handlelength=1.2, handletextpad=.5, columnspacing=1.6)
    a=axes(fig, (36, 64, 111, 22))
    a.spines['left'].set_visible(False)
    a.tick_params(axis='y', length=0, pad=6)
    for i, mode in enumerate(MODES):
        item=summary['conditions'][f'cse_dce/{mode}']
        execution=item['phases_mean_s']['execution_s']
        build=item['phases_mean_s']['witness_build_s']
        remaining=item['prove_mean_s']-execution-build
        left=0
        for value, color in zip((execution, build, remaining), phase_colors):
            a.barh(2-i, value, left=left, height=.55, color=color, edgecolor='white', linewidth=.4)
            left+=value
        ym=64+(2-i+.5)/3*22
        text(fig, 152, ym+1.3, f'{item["prove_mean_s"]:.2f} s total', va='center', bold=True)
        text(fig, 152, ym-2.2, f'{100*remaining/item["prove_mean_s"]:.0f}% proof work', size=6.5, va='center', color=MUTED)
    max_mean=max(summary['conditions'][f'cse_dce/{mode}']['prove_mean_s'] for mode in MODES)
    a.set(yticks=[2, 1, 0], yticklabels=NAMES, ylim=(-.5, 2.5),
          xlim=(0, math.ceil(max_mean/2)*2), xlabel='Mean complete proving time (s)')

    title(fig, 'b', 'Some timing drift remains despite stable power settings', 50)
    deviations=[]
    for mode in MODES:
        rows=measured_rows(samples, mode, 'cse_dce')
        median=st.median(row['prove_s'] for row in rows)
        deviations.extend(100*(row['prove_s']/median-1) for row in rows)
    drift_limits=(min(-5, math.floor(min(deviations)/5)*5), max(5, math.ceil(max(deviations)/5)*5))
    for i, (mode, name, color) in enumerate(zip(MODES, NAMES, COLORS)):
        b=axes(fig, (27+i*51, 14, 43, 24))
        b.set_title(name, fontsize=7, pad=5, fontweight='bold')
        rows=measured_rows(samples, mode, 'cse_dce')
        median=st.median(row['prove_s'] for row in rows)
        b.plot([row['block'] for row in rows], [100*(row['prove_s']/median-1) for row in rows],
               color=color, lw=.8, marker='o', markersize=3.1, markeredgewidth=.65)
        b.axhline(0, color=RULE, lw=.6, zorder=0)
        b.set(xticks=[1, 4, 8], xlim=(.7, 8.3), ylim=drift_limits, xlabel='Measurement round')
        if i==0:
            b.set_ylabel('From median (%)')
        else:
            b.tick_params(axis='y', labelleft=False)
    text(fig, 6, 2.2, '*Hypothetical SSZ summary; both state tries remain Keccak.', size=6.5, color=MUTED)
    export(fig, destination/STEMS[2], 'Exclusive proof costs and timing drift for the 24 optimized-program proofs')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE/'figures')
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    samples, _, summary=analyze(args.run)
    with tempfile.TemporaryDirectory(prefix='owner-figures-') as temporary:
        destination=Path(temporary) if args.check else args.output
        destination.mkdir(parents=True, exist_ok=True)
        schematic(destination)
        proving(destination, samples, summary)
        costs(destination, samples, summary)
        if args.check:
            for stem in STEMS:
                if (destination/(stem+'.svg')).read_bytes() != (args.output/(stem+'.svg')).read_bytes():
                    raise ValueError(f'figure differs: {stem}')
    print(f'Figures {"checked" if args.check else "written"}: {args.output}')


if __name__=='__main__':
    main()
