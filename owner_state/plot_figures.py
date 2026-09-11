"""Publication figures for the complete owner-binding relation.

python -m owner_state.plot_figures --run owner_state/results/collect-<id>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics as st
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle

from owner_state.analyze import HERE, MODES, VARIANTS, analyze
from real_state.plot_figures import export as export_base

MM = 1/25.4
INK, MUTED, GRID = '#202124', '#60676D', '#E2E5E8'
COLORS = ('#009E73', '#0072B2', '#D55E00')
LABELS = ('Direct state', 'RLP block hash', 'SSZ summary*')
PHASES = ('execution_s', 'witness_build_s', 'commitment_s', 'bus_s', 'constraints_s', 'opening_s', 'other_s')
PHASE_LABELS = ('Execution', 'Witness build', 'Commitment', 'Bus proof', 'Constraints', 'Opening', 'Other / cleanup')
PHASE_COLORS = ('#009E73', '#9AD5C4', '#0072B2', '#6DAED5', '#CC79A7', '#D55E00', '#B7BDC2')
STEMS = ('figure-1-owner-binding', 'figure-2-proving-results', 'figure-3-cost-breakdown')
plt.rcParams.update({
    'font.family': ['DejaVu Sans', 'sans-serif'], 'font.size': 7,
    'axes.labelsize': 7, 'xtick.labelsize': 6.5, 'ytick.labelsize': 6.5,
    'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': INK, 'ytick.color': INK,
    'axes.linewidth': .55, 'xtick.major.width': .5, 'ytick.major.width': .5,
    'xtick.major.size': 2.5, 'ytick.major.size': 2.5,
    'svg.fonttype': 'none', 'svg.hashsalt': 'owner-binding-measured-v1',
    'pdf.fonttype': 42, 'ps.fonttype': 42,
    'savefig.facecolor': 'white', 'figure.facecolor': 'white',
})


def export(fig, path, description):
    # Auto locators may create labels beyond fixed axis limits. Matplotlib
    # does not draw them, but the shared bounds check inspects every label.
    for ax in fig.axes:
        if not ax.axison:
            continue
        low, high=sorted(ax.get_xlim())
        ax.set_xticks([value for value in ax.get_xticks() if low<=value<=high])
        low, high=sorted(ax.get_ylim())
        ax.set_yticks([value for value in ax.get_yticks() if low<=value<=high])
    export_base(fig,path,description)


def axes(fig, rect, *, grid='y'):
    width, height = fig.get_size_inches()/MM
    x, y, w, h = rect
    ax = fig.add_axes([x/width, y/height, w/width, h/height])
    ax.spines[['top', 'right']].set_visible(False)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=.5)
        ax.set_axisbelow(True)
    return ax


def title(fig, letter, text, x, y):
    w, h = fig.get_size_inches()/MM
    fig.text(x/w, y/h, letter, fontsize=9, fontweight='bold', va='center')
    fig.text((x+5)/w, y/h, text, fontsize=7.5, fontweight='bold', va='center')


def footer(fig, text):
    fig.text(.035, .027, text, fontsize=6.3, color=MUTED, va='bottom')


def schematic(destination):
    fig = plt.figure(figsize=(183*MM, 150*MM))
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 183), ylim=(0, 150))
    ax.set_axis_off()
    def box(x, y, w, h, text, *, color=INK, fill='white', size=7):
        ax.add_patch(Rectangle((x-w/2, y-h/2), w, h, facecolor=fill, edgecolor=color, lw=.65))
        ax.text(x, y, text, ha='center', va='center', fontsize=size, linespacing=1.55)
    def arrow(a, b, color=INK):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=6, color=color, lw=.7))
    title(fig, 'a', 'The same address opens the note and selects the account', 6, 143)
    box(32, 123, 49, 23, 'Witness inputs\nowner address (20 bytes)\nsecret (32 bytes)', fill='#F3F5F6')
    box(105, 129, 77, 14, 'Keccak-256(owner address || secret)\nMust equal the public note commitment H')
    arrow((56.5, 129), (66.5, 129))
    box(105, 108, 77, 14, 'Account lookup at the chosen anchor\nUses Keccak-256 of that same address')
    arrow((56.5, 117), (66.5, 108))
    ax.text(151, 129, 'Measured', va='center', fontsize=7, color=COLORS[0], fontweight='bold')
    ax.text(151, 108, 'Measured', va='center', fontsize=7, color=COLORS[0], fontweight='bold')
    ax.text(7.5, 96, 'Public statement: anchor type, anchor root/hash, H and storage slot; bound through one Keccak digest.', fontsize=6.5)
    title(fig, 'b', 'Only the route from the anchor to stateRoot changes', 6, 86)
    centers = (32, 91.5, 151)
    details = ('Direct state root\nNo header work', 'RLP block hash\n634-byte canonical header\nKeccak-256; extract stateRoot',
               'SSZ summary root*\n5 SHA-256 pair hashes\nCheck stateRoot branch')
    for x, text, color in zip(centers, details, COLORS):
        box(x, 68, 51, 24, text, color=color, size=6.5)
        ax.plot([x, x], [56, 50], color=color, lw=.8)
    ax.plot([32, 151], [50, 50], color=INK, lw=.7)
    arrow((32, 50), (32, 44))
    box(32, 33, 51, 22, 'Account MPT; 10 nodes\nCanonical RLP + Keccak\nOutputs storageRoot')
    box(91.5, 33, 51, 22, 'Storage MPT\n2 nodes; slot 0\nCanonical RLP + Keccak')
    box(151, 33, 51, 22, 'Authenticated word\nAvailable inside the relation\nNo authorization check', size=6.5)
    arrow((57.5, 33), (66, 33))
    arrow((117, 33), (125.5, 33))
    ax.text(96, 46.5, 'Same stateRoot', ha='center', fontsize=6, color=MUTED)
    ax.text(7.5, 15, 'Binding is tested. Owner privacy is not established by this proof backend.', fontsize=7, fontweight='bold')
    ax.text(7.5, 7, '*Hypothetical SSZ summary containing the real state root. Both state tries remain Keccak MPTs.', fontsize=6.3, color=MUTED)
    export(fig, destination/STEMS[0], 'Measured note-owner binding and three state anchor paths')


def proving(destination, samples, summary):
    measured = [row for row in samples if row['kind'] == 'measured']
    fig = plt.figure(figsize=(183*MM, 158*MM))
    title(fig, 'a', 'Every measured proof, paired by block', 6, 151)
    a = axes(fig, (19, 88, 72, 53))
    for i, (mode, color) in enumerate(zip(MODES, COLORS)):
        x0, x1 = i*3, i*3+1
        for block in range(1, 9):
            pair = [next(row for row in measured if row['mode']==mode and row['variant']==variant and row['block']==block)['prove_s']
                    for variant in VARIANTS]
            offset = (block-4.5)*.026
            a.plot([x0+offset, x1+offset], pair, lw=.45, color=color, alpha=.35)
            a.scatter(x0+offset, pair[0], s=12, facecolor='white', edgecolor=color, linewidth=.7, zorder=3)
            a.scatter(x1+offset, pair[1], s=12, facecolor=color, edgecolor='white', linewidth=.3, zorder=3)
        for x, variant in zip((x0, x1), VARIANTS):
            median = summary['conditions'][f'{variant}/{mode}']['prove_median_s']
            a.plot([x-.22, x+.22], [median, median], color=INK, lw=1.2, zorder=4)
    a.set(xticks=[.5, 3.5, 6.5], xticklabels=['Direct', 'RLP', 'SSZ*'], ylabel='Complete prove time (s)', ylim=(0, None))
    a.legend(handles=[Line2D([], [], marker='o', linestyle='none', mfc='white', mec=INK, ms=3.5, label='Baseline'),
                      Line2D([], [], marker='o', linestyle='none', color=INK, ms=3.5, label='Optimized')],
             loc='lower left', ncol=2, fontsize=6, frameon=False, bbox_to_anchor=(-.09, 1.01))
    title(fig, 'b', 'Does optimization reduce proving time?', 100, 151)
    b = axes(fig, (123, 94, 52, 46), grid='x')
    b.axvline(0, color=INK, lw=.65, zorder=1)
    for i, (mode, color) in enumerate(zip(MODES, COLORS)):
        comparison = next(item for item in summary['comparisons'] if item['comparison']=='optimization' and item['numerator']==f'cse_dce/{mode}')
        center, low, high = [100*(comparison[key]-1) for key in ('ratio', 'ci95_low', 'ci95_high')]
        b.errorbar(center, 2-i, xerr=[[center-low], [high-center]], fmt='o', ms=4, color=color, lw=1, capsize=2)
        b.text(.98, (2-i+.2)/3.0, f'{center:+.1f}% [{low:+.1f}, {high:+.1f}]',
               transform=b.transAxes, ha='right', va='top', fontsize=6, color=MUTED)
    b.set(yticks=[2, 1, 0], yticklabels=['Direct', 'RLP', 'SSZ*'], ylim=(-.65, 2.6), xlabel='Optimized / baseline time − 1 (%)')
    b.margins(x=.22)
    fig.text(101/183, 76/158, 'Point: geometric mean of 8 paired ratios\nBar: 95% within-batch interval', fontsize=6.2, color=MUTED, linespacing=1.5)
    title(fig, 'c', 'Instruction savings leave padding unchanged', 6, 73)
    c = axes(fig, (23, 22, 68, 41), grid='x')
    y, labels = [], []
    for i, (mode, color) in enumerate(zip(MODES, COLORS)):
        for j, variant in enumerate(VARIANTS):
            position = 5-i*2-j
            count = summary['conditions'][f'{variant}/{mode}']['instructions']/1e6
            c.barh(position, count, height=.65, color=color if j else 'white', edgecolor=color, linewidth=.8)
            c.text(9.65, position, f'{count:.3f}', ha='right', va='center', fontsize=6)
            y.append(position); labels.append(('B' if j==0 else 'O') + '  ' + ('Direct', 'RLP', 'SSZ*')[i])
    c.set(yticks=y, yticklabels=labels, xlabel='VM instructions (million)', xlim=(0, 10))
    boundary=(2**23-1)/1e6  # The bytecode also contains one unexecuted sentinel.
    c.axvline(boundary,color=INK,lw=.65,linestyle=(0,(2,2)))
    c.text(boundary,6.15,'2²³ bytecode boundary',ha='center',va='bottom',fontsize=5.7,color=MUTED)
    title(fig, 'd', 'Committed witness size', 100, 73)
    d = axes(fig, (121, 22, 54, 41), grid='x')
    for i, (mode, color) in enumerate(zip(MODES, COLORS)):
        for j, variant in enumerate(VARIANTS):
            count = summary['conditions'][f'{variant}/{mode}']['committed_cells']/1e6
            d.barh(5-i*2-j, count, height=.65, color=color if j else 'white', edgecolor=color, linewidth=.8)
            d.text(count+1, 5-i*2-j, f'{count:.2f}', va='center', fontsize=6)
    maximum = max(value['committed_cells']/1e6 for value in summary['conditions'].values())
    d.set(yticks=y, yticklabels=labels, xlabel='Committed field cells (million)', xlim=(0, maximum*1.26))
    footer(fig, '48 proofs; 8 blocks × 6 conditions. B, baseline; O, optimized. *Hypothetical SSZ summary. All samples retained.')
    export(fig, destination/STEMS[1], 'Owner-binding proof times, paired optimization effects, instruction counts and commitments')


def costs(destination, samples, summary):
    measured = [row for row in samples if row['kind']=='measured']
    fig = plt.figure(figsize=(183*MM, 167*MM))
    title(fig, 'a', 'Where complete proving time is spent', 6, 160)
    a = axes(fig, (23, 100, 151, 47), grid='x')
    labels=[]
    for i, mode in enumerate(MODES):
        for j, variant in enumerate(VARIANTS):
            bottom=0
            condition=summary['conditions'][f'{variant}/{mode}']
            for key, color in zip(PHASES, PHASE_COLORS):
                value=condition['phases_mean_s'][key]
                a.barh(5-i*2-j, value, left=bottom, color=color, height=.7, edgecolor='white', linewidth=.25)
                bottom+=value
            a.text(bottom+.18, 5-i*2-j, f'{bottom:.2f} s', va='center', fontsize=6.3)
            labels.append(('B' if j==0 else 'O')+'  '+('Direct','RLP','SSZ*')[i])
    maximum=max(value['prove_mean_s'] for value in summary['conditions'].values())
    a.set(yticks=list(range(5,-1,-1)), yticklabels=labels, xlabel='Arithmetic mean wall time (s)', xlim=(0, maximum*1.14))
    fig.legend(handles=[Patch(facecolor=color,label=label) for color,label in zip(PHASE_COLORS,PHASE_LABELS)],
               loc='upper left', bbox_to_anchor=(.11,.927), ncol=4, frameon=False, fontsize=6, handlelength=1.2,
               handletextpad=.4, columnspacing=1.2, labelspacing=.4)
    title(fig, 'b', 'Hashing dominates guest instructions', 6, 84)
    b=axes(fig,(21,35,68,39),grid='x')
    component_colors=('#455C6E','#CC79A7','#BBC3C8')
    for i, mode in enumerate(MODES):
        values=summary['conditions'][f'cse_dce/{mode}']['instruction_sections']
        total=sum(values.values()); left=0
        for key,color in zip(('keccak256','sha256','relation'),component_colors):
            share=values[key]/total*100
            b.barh(2-i,share,left=left,height=.55,color=color,edgecolor='white',linewidth=.25)
            left+=share
        share=(values['keccak256']+values['sha256'])/total*100
        b.text(50,2-i,f'{share:.1f}% hashes',ha='center',va='center',color='white',fontsize=6.3)
    b.set(yticks=[2,1,0],yticklabels=['Direct','RLP','SSZ*'],xlabel='Optimized instructions (%)',xlim=(0,100))
    b.legend(handles=[Patch(facecolor=color,label=label) for color,label in zip(component_colors,('Keccak','SHA-256','Other'))],
             loc='upper left',bbox_to_anchor=(-.12,-.27),ncol=3,frameon=False,fontsize=6,handlelength=1)
    title(fig, 'c', 'Observe variation across the batch', 99, 84)
    c=axes(fig,(114,35,60,39),grid='y')
    for mode,color in zip(MODES,COLORS):
        for variant in VARIANTS:
            group=sorted((row for row in measured if row['mode']==mode and row['variant']==variant),key=lambda row:row['block'])
            median=st.median(row['prove_s'] for row in group)
            c.plot([row['block'] for row in group],[100*(row['prove_s']/median-1) for row in group],
                   color=color,linestyle='--' if variant=='baseline' else '-',marker='o',markersize=2.4,
                   markerfacecolor='white' if variant=='baseline' else color,linewidth=.8,alpha=.85)
    c.axhline(0,color=MUTED,lw=.5)
    c.set(xticks=[1,2,3,4,5,6,7,8],xlabel='Measured block',ylabel='Change from condition median (%)')
    c.legend(handles=[Line2D([],[],color=color,lw=1,label=label) for color,label in zip(COLORS,('Direct','RLP','SSZ*'))],
             loc='upper left',bbox_to_anchor=(-.13,-.27),ncol=3,frameon=False,fontsize=6,handlelength=1)
    fig.text(.035,.08,'Phase clocks are exclusive. Hash instruction counts are not an additive breakdown of proof-construction time.',fontsize=6.3,color=MUTED)
    footer(fig,'B, baseline (dashed in c); O, optimized (solid). 8 fresh processes per condition; AC power; 11 Rayon workers.')
    export(fig,destination/STEMS[2],'Exclusive proving phases, guest hash instruction share and within-batch timing variation')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=HERE/'figures')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    samples,_,summary=analyze(args.run)
    with tempfile.TemporaryDirectory(prefix='owner-figures-') as temporary:
        destination=Path(temporary) if args.check else args.output
        destination.mkdir(parents=True,exist_ok=True)
        schematic(destination)
        proving(destination,samples,summary)
        costs(destination,samples,summary)
        if args.check:
            # SVG encodes plot data and typography deterministically; PDF/PNG
            # binary encodings can vary across plotting/library platforms.
            for stem in STEMS:
                if (destination/(stem+'.svg')).read_bytes() != (args.output/(stem+'.svg')).read_bytes():
                    raise ValueError(f'figure differs: {stem}')
    print(f'Figures {"checked" if args.check else "written"}: {args.output}')


if __name__=='__main__':
    main()
