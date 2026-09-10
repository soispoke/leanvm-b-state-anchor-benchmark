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
STEMS = ('figure-1-proof-paths', 'figure-2-measured-results')
plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 6.5,
    'axes.labelsize': 6.5, 'axes.titlesize': 7,
    'xtick.labelsize': 6, 'ytick.labelsize': 6.5,
    'text.color': INK, 'axes.labelcolor': INK,
    'xtick.color': INK, 'ytick.color': INK,
    'axes.linewidth': .5, 'xtick.major.width': .5,
    'ytick.major.width': .5, 'xtick.major.size': 2.5,
    'svg.fonttype': 'none', 'svg.hashsalt': 'leanvm-real-state-figures-v1',
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
    fig.savefig(path.with_suffix('.pdf'), metadata={
        'Title': description, 'Creator': 'real_state.plot_figures; Matplotlib',
        'CreationDate': None, 'ModDate': None,
    })
    fig.savefig(path.with_suffix('.png'), dpi=600, metadata={'Description': description})
    plt.close(fig)


def schematic(destination):
    programs = json.loads((HERE/'programs.json').read_text())
    profile = json.loads((HERE/'profile.json').read_text())
    claim = programs['direct']['metadata']
    fixture = json.loads((ROOT/'fixtures/mainnet-0x18bd000.json').read_text())
    block_number = int(fixture['block']['number'],16)
    header_length = next(item['length']//8 for item in programs['rlp']['metadata']['witness_ranges']
                         if item['name']=='header')
    node_counts = [len(profile[kind]['nodes']) for kind in ('account','storage')]
    value = '0x'+claim['value'][-40:]
    short_value, short_account = value[:6]+'...'+value[-4:], claim['account'][:6]+'...'+claim['account'][-4:]
    fig = plt.figure(figsize=(183*MM, 115*MM))
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 183), ylim=(0, 115))
    ax.set_axis_off()

    def box(x, y, width, height, text, color=None, size=6.5, bold=False):
        ax.add_patch(Rectangle((x-width/2, y-height/2), width, height,
                               facecolor='white', edgecolor=color or '#7C8389', lw=.65))
        if color:
            ax.add_patch(Rectangle((x-width/2, y+height/2-1), width, 1,
                                   facecolor=color, edgecolor='none'))
        ax.text(x, y-.25, text, ha='center', va='center', fontsize=size,
                fontweight='bold' if bold else 'normal', linespacing=1.45)

    def arrow(start, end, color=INK):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=6,
                                     linewidth=.65, color=color, shrinkA=1, shrinkB=1))

    panel_title(fig, 'a', 'Three public anchors authenticate the same state root', 5, 109)
    centers = (32, 91.5, 151)
    names = ('Direct state root', 'Historical RLP block hash', 'Proposed SSZ summary root*')
    details = ('State root bound directly\nto the public claim',
               f'Canonical RLP header\nExtract stateRoot\nKeccak-256; {header_length} bytes',
               f"State-root branch at gindex {profile['ssz_gindex']}\n5 SHA-256 pair hashes\n{profile['ssz_active_fields']}-field activity bitmap")
    for x, name, detail, color in zip(centers, names, details, COLORS):
        box(x, 95, 52, 11, name, color, size=6.5, bold=True)
        arrow((x, 89.5), (x, 84))
        box(x, 76.5, 52, 15, detail, size=6.5)
    # Distinct entry points converge on one root without crossing labels.
    ax.plot([32,32,78,78], [69,64,64,60.5], color=INK, lw=.65)
    arrow((78,62), (78,58.5))
    arrow((91.5,69), (91.5,58.5))
    ax.plot([151,151,105,105], [69,64,64,60.5], color=INK, lw=.65)
    arrow((105,62), (105,58.5))
    box(91.5, 54, 58, 9, 'Same authenticated mainnet state root', size=6.5)

    panel_title(fig, 'b', 'A shared account-and-storage inclusion relation', 5, 42)
    box(20, 25.5, 28, 18, 'State\nroot', size=6.5)
    box(64, 25.5, 44, 18, f'Account MPT\n{node_counts[0]} nodes: RLP + Keccak\nKey = Keccak(address)', size=6.2)
    box(119, 25.5, 44, 18, f'Storage MPT\n{node_counts[1]} nodes: RLP + Keccak\nKey = Keccak(slot)', size=6.2)
    box(164, 25.5, 28, 18, f"Slot {int(claim['slot'],16)} value\n{short_value}", size=6.2)
    arrow((34,25.5), (42,25.5))
    arrow((86,25.5), (97,25.5))
    arrow((141,25.5), (150,25.5))
    ax.text(91.5, 36, 'storageRoot', ha='center', fontsize=5.5, color=INK)
    ax.text(6, 9, f'Mainnet block {block_number:,}  |  Safe {short_account}  |  Fixed public encoding shape', fontsize=6)
    ax.text(6, 4, '*Hypothetical SSZ summary containing the real state root. Every encoding and hash check shown is enforced in the VM.', fontsize=5.6)
    export(fig, destination / STEMS[0], 'Real account-and-storage inclusion through three public anchors')


def measured(destination, rows):
    fig = plt.figure(figsize=(183*MM, 157*MM))
    by_mode = [[row for row in rows if row['anchor'] == mode] for mode in MODES]

    def axes(x, y, width=61, height=29):
        ax = fig.add_axes([x/183, y/157, width/183, height/157])
        ax.set_ylim(-.58, 2.58)
        ax.set_yticks([2,1,0], LABELS)
        ax.tick_params(axis='y', length=0, pad=4)
        for side in ('left','right','top'):
            ax.spines[side].set_visible(False)
        ax.spines['bottom'].set_color('#7C8389')
        ax.grid(axis='x', color=GRID, linewidth=.45)
        ax.set_axisbelow(True)
        return ax

    def raw_points(ax, key, scale, xmax, ticks, decimals, suffix=''):
        ax.set_xlim(0, xmax)
        ax.set_xticks(ticks)
        for y, samples, color in zip([2,1,0], by_mode, COLORS):
            values = [sample[key]/scale for sample in samples]
            median = statistics.median(values)
            ax.plot([min(values),max(values)], [y,y], color='#ADB3B8', lw=.65, zorder=2)
            ax.plot([median,median], [y-.27,y+.27], color=INK, lw=.9, zorder=3)
            for j,(value,marker) in enumerate(zip(values,MARKERS)):
                ax.scatter(value,y+(-.15,0,.15)[j],s=17,marker=marker,
                           color=color,edgecolor='white',linewidth=.4,zorder=4)
            ax.text(.99,y,f'{median:.{decimals}f}{suffix}', transform=ax.get_yaxis_transform(),
                    ha='right',va='center',fontsize=6.2)
        ax.text(.99,1.04,'median',transform=ax.transAxes,ha='right',fontsize=5.5,color=MUTED)

    panel_title(fig,'a','Proving time',4,150)
    panel_title(fig,'b','Verification time',95,150)
    a,b = axes(26,112),axes(117,112)
    raw_points(a,'prove_seconds',1,40,[0,10,20,30,40],2)
    raw_points(b,'verify_ms',1,760,[0,200,400,600],1)
    a.set_xlabel('Proving time (s)',labelpad=3)
    b.set_xlabel('Verification time (ms)',labelpad=3)

    panel_title(fig,'c','Execution work',4,99)
    panel_title(fig,'d','Committed witness cells',95,99)
    c,d = axes(26,64, height=27),axes(117,64,height=27)
    c.set_xlim(0,10.7);c.set_xticks([0,2,4,6,8,10])
    d.set_xlim(0,237);d.set_xticks([0,50,100,150,200])
    for y,samples,color in zip([2,1,0],by_mode,COLORS):
        row=samples[0]
        xor,mul,other=(row[key]/1e6 for key in ('xor_instructions','mul_instructions','other_instructions'))
        c.barh(y,xor,height=.48,color=color,zorder=2)
        c.barh(y,mul,left=xor,height=.48,facecolor='white',edgecolor=color,
               hatch='////',linewidth=.5,zorder=2)
        c.barh(y,other,left=xor+mul,height=.48,color=INK,zorder=2)
        c.text(.99,y,f"{row['vm_cycles']/1e6:.3f}",transform=c.get_yaxis_transform(),ha='right',va='center',fontsize=6.2)
        d.barh(y,row['committed_witness_cells']/1e6,height=.48,color=color,zorder=2)
        d.text(.99,y,f"{row['committed_witness_cells']/1e6:.3f}",transform=d.get_yaxis_transform(),ha='right',va='center',fontsize=6.2)
    c.set_xlabel('Executed VM instructions (million)',labelpad=3)
    d.set_xlabel('Committed witness cells (million)',labelpad=3)
    c.legend(handles=[Patch(facecolor='#7C8389',label='XOR'),
              Patch(facecolor='white',edgecolor='#7C8389',hatch='////',label='MUL')],
             loc='lower left',bbox_to_anchor=(0,1.015),frameon=False,ncol=2,
             borderaxespad=0,handlelength=1.2,handleheight=.7,columnspacing=1.2,fontsize=5.5)
    d.text(0,1.04,'Identical padded commitment',transform=d.transAxes,fontsize=5.5,color=MUTED)

    panel_title(fig,'e','Serialized proof size',4,52)
    panel_title(fig,'f','Peak memory footprint',95,52)
    e,f = axes(26,17,height=27),axes(117,17,height=27)
    e.set_xlim(0,1.09);e.set_xticks([0,.25,.5,.75,1], ['0','0.25','0.50','0.75','1.00'])
    for y,samples,color in zip([2,1,0],by_mode,COLORS):
        value=samples[0]['proof_bytes']/1e6
        e.barh(y,value,height=.48,color=color,zorder=2)
        e.text(.99,y,f'{value:.4f}',transform=e.get_yaxis_transform(),ha='right',va='center',fontsize=6.2)
    e.set_xlabel('Serialized proof size (MB)',labelpad=3)
    raw_points(f,'peak_footprint_bytes',2**30,50,[0,10,20,30,40],2)
    f.set_xlabel('macOS peak memory footprint (GiB)',labelpad=3)
    handles=[Line2D([],[],color=INK,marker=m,linestyle='none',markersize=3.5,label=f'Repetition {i}')
             for i,m in enumerate(MARKERS,1)]
    handles.extend([Line2D([],[],color=INK,marker='|',linestyle='none',markersize=6,label='Median'),
                    Line2D([],[],color='#ADB3B8',lw=.65,label='Observed range')])
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.035),
               ncol=5,frameon=False,fontsize=5.5,handlelength=1.4,columnspacing=1.5)
    fig.text(.03,.01,'n = 3 fresh processes per anchor; battery power. *Hypothetical SSZ summary with a real mainnet state root.',fontsize=5.3)
    export(fig,destination/STEMS[1],'Real-proof measurements: all nine runs, instruction work, commitments, proof sizes and memory')


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    rows=load_data()
    data=io.StringIO(newline='')
    writer=csv.DictWriter(data,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    (destination/'source-data.csv').write_text(data.getvalue())
    schematic(destination)
    measured(destination,rows)


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
        print('PASS: all nine raw samples, deterministic metrics, source CSV and both SVG figures agree')
    else:
        build(args.output)
        print(f'Wrote two figures as editable SVG, vector PDF and 600 dpi PNG, plus source data: {args.output}')


if __name__=='__main__':
    main()
