"""Build publication figures directly from the preserved real-proof evidence.

python -m pip install -r real_state/figure-requirements.txt
python -m real_state.plot_figures
python -m real_state.plot_figures --check
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import statistics
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle, Patch

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / 'real_state'
MODES = ('direct', 'rlp', 'ssz')
LABELS = ('Direct state', 'RLP block hash', 'SSZ summary*')
COLORS = ('#009E73', '#0072B2', '#D55E00')
INK, MUTED, GRID = '#202124', '#555B61', '#DCE0E3'
MM = 1 / 25.4
MARKERS = ('o', '^', 's')
STEMS = ('figure-1-proof-paths', 'figure-2-measured-results', 'figure-s1-resources')
plt.rcParams.update({
    'font.family': ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif'], 'font.size': 6.5,
    'axes.labelsize': 6.5, 'axes.titlesize': 7,
    'xtick.labelsize': 6, 'ytick.labelsize': 6.5,
    'text.color': INK, 'axes.labelcolor': INK,
    'xtick.color': INK, 'ytick.color': INK,
    'axes.linewidth': .5, 'xtick.major.width': .5,
    'ytick.major.width': .5, 'xtick.major.size': 2.5,
    'svg.fonttype': 'none', 'svg.hashsalt': 'leanvm-owner-state-figures-v2',
    'pdf.fonttype': 42, 'ps.fonttype': 42,
    'savefig.facecolor': 'white', 'figure.facecolor': 'white',
    'hatch.linewidth': .4,
})


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_data():
    rows = []
    orders = (('direct', 'rlp', 'ssz'), ('ssz', 'direct', 'rlp'), ('rlp', 'ssz', 'direct'))
    for mode in MODES:
        for repetition in (1, 2, 3):
            path = HERE / 'results' / f'{mode}-prove-{repetition}.txt'
            text = path.read_text()
            matches = re.findall(r'^RESULT (\{.*\})$', text, re.MULTILINE)
            if len(matches) != 1 or 'test result: ok. 1 passed; 0 failed;' not in text:
                raise ValueError(f'Expected one successful proof result: {path}')
            result = json.loads(matches[0])
            if not (result['wrong_public_rejected'] and result['mutated_proof_rejected']):
                raise ValueError('Proof tamper checks did not pass')
            rows.append({
                'anchor': mode, 'repetition': repetition,
                'chronological_process': 3 * (repetition - 1) + orders[repetition-1].index(mode) + 1,
                'prove_seconds': result['prove_including_execute_ms'] / 1000,
                'verify_ms': result['verify_ms'], 'assembly_ms': result['assembly_ms'],
                'vm_cycles': result['cycles'], 'xor_instructions': result['counts'][0],
                'mul_instructions': result['counts'][1],
                'other_instructions': sum(result['counts'][2:]),
                'committed_witness_cells': result['committed'],
                'proof_bytes': result['proof_bytes'],
                'peak_footprint_bytes': int(re.search(r'(\d+)\s+peak memory footprint', text)[1]),
                'maximum_resident_bytes': int(re.search(r'(\d+)\s+maximum resident set size', text)[1]),
                'source': str(path.relative_to(ROOT)), 'source_sha256': sha(path),
            })
    with (HERE / 'results/summary.csv').open() as stream:
        summaries = {row['anchor']: row for row in csv.DictReader(stream)}
    for mode in MODES:
        samples = [row for row in rows if row['anchor'] == mode]
        summary = summaries[mode]
        checks = {
            'prove_median_s': statistics.median(row['prove_seconds'] for row in samples),
            'prove_min_s': min(row['prove_seconds'] for row in samples),
            'prove_max_s': max(row['prove_seconds'] for row in samples),
            'verify_median_ms': statistics.median(row['verify_ms'] for row in samples),
        }
        for key, expected in checks.items():
            if abs(float(summary[key]) - expected) > .000001:
                raise ValueError(f'{mode}: raw data differs from {key}')
        for key in ('vm_cycles', 'xor_instructions', 'mul_instructions',
                    'other_instructions', 'committed_witness_cells', 'proof_bytes'):
            if len({row[key] for row in samples}) != 1:
                raise ValueError(f'{mode}: deterministic field varies: {key}')
        if samples[0]['vm_cycles'] != sum(samples[0][key] for key in
                ('xor_instructions', 'mul_instructions', 'other_instructions')):
            raise ValueError('Instruction decomposition differs from VM cycles')
    return rows


def panel_title(fig, letter, title, x_mm, y_mm):
    width, height = fig.get_size_inches() / MM
    fig.text(x_mm / width, y_mm / height, letter, fontsize=8, fontweight='bold', va='center')
    fig.text((x_mm+5) / width, y_mm / height, title, fontsize=7, fontweight='bold', va='center')


def export(fig, path, description):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    for text in fig.findobj(matplotlib.text.Text):
        if not text.get_visible() or not text.get_text():
            continue
        box = text.get_window_extent(renderer)
        if box.x0 < -1 or box.y0 < -1 or box.x1 > width+1 or box.y1 > height+1:
            raise ValueError(f'Text exceeds figure bounds: {text.get_text()!r}')
    fig.savefig(path.with_suffix('.svg'), metadata={'Date': None, 'Description': description})
    # Matplotlib leaves trailing spaces in multiline SVG path attributes.
    svg = path.with_suffix('.svg')
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    fig.savefig(path.with_suffix('.pdf'), metadata={
        'Title': description, 'Creator': 'real_state.plot_figures; Matplotlib',
        'CreationDate': None, 'ModDate': None,
    })
    fig.savefig(path.with_suffix('.png'), dpi=600, metadata={'Description': description})
    plt.close(fig)


def schematic(destination):
    programs = json.loads((HERE/'programs.json').read_text())
    profile = json.loads((HERE/'profile.json').read_text())
    header_length = next(item['length']//8 for item in programs['rlp']['metadata']['witness_ranges']
                         if item['name']=='header')
    node_counts = [len(profile[kind]['nodes']) for kind in ('account','storage')]
    fig = plt.figure(figsize=(183*MM, 149*MM))
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 183), ylim=(0, 149))
    ax.set_axis_off()

    def box(x, y, width, height, text, color=None, dashed=False, size=6.5, bold=False):
        ax.add_patch(Rectangle((x-width/2, y-height/2), width, height,
                               facecolor='white', edgecolor=color or '#7C8389', lw=.7,
                               linestyle=(0,(3,2)) if dashed else 'solid'))
        if color:
            ax.add_patch(Rectangle((x-width/2, y+height/2-1), width, 1,
                                   facecolor=color, edgecolor='none'))
        ax.text(x, y-.25, text, ha='center', va='center', fontsize=size,
                fontweight='bold' if bold else 'normal', linespacing=1.55)

    def arrow(start, end, color=INK):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=6,
                                     linewidth=.7, color=color, shrinkA=1, shrinkB=1))

    panel_title(fig, 'a', 'Owner binding: where authenticated state enters', 5, 143)
    box(43,124,74,24,'Note commitment\nH = hash(owner_addr, secret)\nContext; opening not measured',dashed=True)
    box(140,124,74,24,'Account and stored word\nLookup(root, owner_addr, slot) = value\nMeasured state lookup',color=INK)
    arrow((80,121),(103,121))
    ax.text(91.5,126,'same address',ha='center',fontsize=5.8)
    ax.text(6,106,'Focus: the state-dependent part of (i). Authorization in (ii) is outside this comparison.',fontsize=6.5)

    panel_title(fig, 'b', 'Change the anchor; keep the account and storage proof', 5, 97)
    centers = (32, 91.5, 151)
    names = ('Direct state root', 'RLP block hash', 'SSZ summary root*')
    details = ('No block-header check\nState root supplied directly',
               f'Canonical RLP; {header_length}-byte header\nExtract stateRoot\nKeccak-256',
               f"State-root branch; gindex {profile['ssz_gindex']}\n5 SHA-256 pair hashes\n{profile['ssz_active_fields']}-field activity bitmap")
    for x, name, detail, color in zip(centers, names, details, COLORS):
        box(x,85,52,10,name,color,bold=True)
        arrow((x,80),(x,75))
        box(x,65,52,20,detail)
        ax.plot([x,x],[55,49],color=INK,lw=.7)
    ax.plot([25,151],[49,49],color=INK,lw=.7)
    arrow((25,49),(25,35))
    ax.text(92,44,'The same account and storage tries remain in every condition',ha='center',fontsize=6.2)
    ax.add_patch(Rectangle((5,12),173,25,facecolor='#F1F3F4',edgecolor='none',zorder=-1))
    box(25,25,30,20,'State root')
    box(67,25,40,20,f'Account MPT\n{node_counts[0]} nodes\nKey: Keccak(address)')
    box(118,25,40,20,f'Storage MPT\n{node_counts[1]} nodes\nKey: Keccak(slot)')
    box(163,25,28,20,'Stored word\nKey stand-in')
    arrow((40,25),(47,25));arrow((87,25),(98,25));arrow((138,25),(149,25))
    ax.text(92.5,36,'storageRoot',ha='center',fontsize=5.5)
    ax.text(6,7,'Mainnet block 25,939,968; Safe slot 0. RLP, trie routing and all required hashes run inside the VM.',fontsize=6)
    ax.text(6,2.5,'*Hypothetical SSZ summary with the real state root. Fixed public shape; owner hiding is not demonstrated.',fontsize=6)
    export(fig, destination / STEMS[0], 'State lookup for note-owner binding: measured relation and three anchor paths')


def chart_axes(fig, x, y, width, height, labels=LABELS):
    fw,fh=fig.get_size_inches()/MM
    ax=fig.add_axes([x/fw,y/fh,width/fw,height/fh])
    ax.set_ylim(-.6,2.6)
    ax.set_yticks([2,1,0],labels)
    ax.tick_params(axis='y',length=0,pad=4)
    for side in ('left','right','top'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#7C8389')
    ax.grid(axis='x',color=GRID,linewidth=.45)
    ax.set_axisbelow(True)
    return ax


def raw_points(ax, by_mode, key, scale, xmax, ticks):
    ax.set_xlim(0,xmax);ax.set_xticks(ticks)
    medians=[]
    for y,samples,color in zip([2,1,0],by_mode,COLORS):
        values=[sample[key]/scale for sample in samples]
        medians.append(statistics.median(values))
        ax.plot([min(values),max(values)],[y,y],color='#ADB3B8',lw=.8,zorder=2)
        ax.plot([medians[-1],medians[-1]],[y-.28,y+.28],color=INK,lw=1,zorder=3)
        for j,(value,marker) in enumerate(zip(values,MARKERS)):
            ax.scatter(value,y+(-.16,0,.16)[j],s=23,marker=marker,
                       color=color,edgecolor='white',linewidth=.4,zorder=4)
    return medians


def sample_legend(fig, y):
    handles=[Line2D([],[],color=INK,marker=m,linestyle='none',markersize=4,label=f'Repetition {i}')
             for i,m in enumerate(MARKERS,1)]
    handles.extend([Line2D([],[],color=INK,marker='|',linestyle='none',markersize=7,label='Median'),
                    Line2D([],[],color='#ADB3B8',lw=.8,label='Observed range')])
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,y),
               ncol=5,frameon=False,fontsize=6,handlelength=1.4,columnspacing=1.5)


def measured(destination, rows):
    fig=plt.figure(figsize=(183*MM,127*MM))
    by_mode=[[row for row in rows if row['anchor']==mode] for mode in MODES]
    baseline=by_mode[0][0]['vm_cycles']
    panel_title(fig,'a','Work added by the anchor',5,120)
    panel_title(fig,'b','Same padded commitment',112,120)
    a=chart_axes(fig,29,78,67,30)
    a.set_xlim(0,9);a.set_xticks([0,2,4,6,8])
    for y,samples,color in zip([2,1,0],by_mode,COLORS):
        total=samples[0]['vm_cycles'];extra=total-baseline
        a.barh(y,baseline/1e6,height=.48,color='#C8CDD1',zorder=2)
        a.barh(y,extra/1e6,left=baseline/1e6,height=.48,color=color,zorder=2)
        a.text(.01,y,f'{total/1e6:.3f} M',transform=a.get_yaxis_transform(),
               ha='left',va='center',fontsize=6.5)
        a.text(1.015,y,'baseline' if not extra else f'+{extra/baseline:.1%}',
               transform=a.get_yaxis_transform(),ha='left',va='center',fontsize=6.2)
    a.set_xlabel('Executed VM instructions (million)',labelpad=3)
    a.legend(handles=[Patch(facecolor='#C8CDD1',label='Direct-state baseline'),
                      Patch(facecolor='#7C8389',label='Added work')],
             loc='lower left',bbox_to_anchor=(-.005,1.035),frameon=False,ncol=2,
             borderaxespad=0,handlelength=1,handleheight=.7,columnspacing=.9,fontsize=5.8)
    b=fig.add_axes([123/183,78/127,53/183,30/127])
    b.bar([0,1,2],[samples[0]['committed_witness_cells']/1e6 for samples in by_mode],
          color=COLORS,width=.55,zorder=2)
    b.set_ylim(0,215);b.set_yticks([0,100,200]);b.set_xticks([0,1,2],['Direct','RLP','SSZ*'])
    b.set_ylabel('Witness cells (million)',labelpad=3)
    b.spines[['right','top']].set_visible(False)
    b.grid(axis='y',color=GRID,linewidth=.45);b.set_axisbelow(True)
    b.text(.5,1.065,'182.455 M in every condition',transform=b.transAxes,
           ha='center',fontsize=6.3)

    panel_title(fig,'c','Proving time: every process, with descriptive medians',5,61)
    c=chart_axes(fig,29,23,121,29)
    medians=raw_points(c,by_mode,'prove_seconds',1,36,[0,5,10,15,20,25,30,35])
    c.set_xlabel('Proving time, including execution and witness generation (s)',labelpad=3)
    for y,median in zip([2,1,0],medians):
        c.text(1.07,y,f'{median:.2f} s',transform=c.get_yaxis_transform(),va='center',fontsize=7)
    c.text(1.07,1.04,'median',transform=c.transAxes,fontsize=6,color=MUTED)
    sample_legend(fig,.065)
    fig.text(.03,.034,'n = 3 per anchor; battery power; unoptimized Boolean hashes. Timing does not establish an anchor ranking.',fontsize=6)
    fig.text(.03,.014,'*Hypothetical SSZ summary containing the real mainnet state root.',fontsize=6)
    export(fig,destination/STEMS[1],'State lookup costs: added instructions, identical padded commitments and all nine proving times')


def supplementary(destination, rows):
    fig=plt.figure(figsize=(183*MM,151*MM))
    by_mode=[[row for row in rows if row['anchor']==mode] for mode in MODES]
    panels=(('a','Verification time','verify_ms',1,750,[0,200,400,600],
             'Verification time (ms)',1,143,111),
            ('b','Serialized proof size','proof_bytes',1e6,1,[0,.25,.5,.75,1],
             'Serialized proof size (MB)',4,100,68),
            ('c','Process peak memory footprint','peak_footprint_bytes',2**30,45,[0,10,20,30,40],
             'macOS peak memory footprint (GiB)',2,57,25))
    for letter,title,key,scale,xmax,ticks,xlabel,decimals,title_y,y in panels:
        panel_title(fig,letter,title,5,title_y)
        ax=chart_axes(fig,29,y,121,25)
        if key=='proof_bytes':
            ax.set_xlim(0,xmax);ax.set_xticks(ticks)
            values=[samples[0][key]/scale for samples in by_mode]
            ax.barh([2,1,0],values,height=.48,color=COLORS,zorder=2)
            summary_label='size'
        else:
            values=raw_points(ax,by_mode,key,scale,xmax,ticks)
            summary_label='median'
        for yy,value in zip([2,1,0],values):
            ax.text(1.07,yy,f'{value:.{decimals}f}',transform=ax.get_yaxis_transform(),va='center',fontsize=7)
        ax.text(1.07,1.04,summary_label,transform=ax.transAxes,fontsize=6,color=MUTED)
        ax.set_xlabel(xlabel,labelpad=3)
    sample_legend(fig,.035)
    fig.text(.03,.01,'n = 3 per anchor; battery power. *Hypothetical SSZ summary containing the real mainnet state root.',fontsize=6)
    export(fig,destination/STEMS[2],'Supplementary measurements for the state lookup: verification, proof size and process memory')


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    rows=load_data()
    data=io.StringIO(newline='')
    writer=csv.DictWriter(data,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    (destination/'source-data.csv').write_text(data.getvalue())
    schematic(destination)
    measured(destination,rows)
    supplementary(destination,rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'figures')
    parser.add_argument('--check',action='store_true',help='regenerate and compare source data and SVG artwork')
    args=parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix='leanvm-figures-') as temporary:
            scratch=Path(temporary)
            build(scratch)
            for name in ['source-data.csv',*[stem+'.svg' for stem in STEMS]]:
                if (scratch/name).read_bytes() != (args.output/name).read_bytes():
                    raise ValueError(f'Figure differs from raw data or generator: {name}')
        print('PASS: all nine raw samples, deterministic metrics, source CSV and all three SVG figures agree')
    else:
        build(args.output)
        print(f'Wrote three figures as editable SVG, vector PDF and 600 dpi PNG, plus source data: {args.output}')


if __name__=='__main__':
    main()
