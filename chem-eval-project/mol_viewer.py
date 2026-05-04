import re
import math
from io import BytesIO

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D
from PIL import Image, ImageDraw
import streamlit as st
import streamlit.components.v1 as components


MOL_TAG_PATTERN = r'\[MOL:\s*(.+?)\s*,\s*ANGLE:\s*(.+?)\s*,\s*SHAPE:\s*(.+?)\s*\]'
LEWIS_TAG_PATTERN = r'\[LEWIS:\s*(.+?)\s*\]'


def parse_mol_tags(text: str) -> list:
    matches = re.findall(MOL_TAG_PATTERN, text)
    results = []
    for smiles, angle, shape in matches:
        results.append({
            'smiles': smiles.strip(),
            'angle': angle.strip(),
            'shape': shape.strip(),
        })
    return results


def parse_lewis_tags(text: str) -> list:
    matches = re.findall(LEWIS_TAG_PATTERN, text)
    return [s.strip() for s in matches]


def remove_mol_tags(text: str) -> str:
    return re.sub(MOL_TAG_PATTERN, '', text).strip()


def remove_lewis_tags(text: str) -> str:
    return re.sub(LEWIS_TAG_PATTERN, '', text).strip()


def remove_all_vis_tags(text: str) -> str:
    text = remove_mol_tags(text)
    text = remove_lewis_tags(text)
    return text


def generate_3d_molblock(smiles: str) -> str:
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mol = Chem.AddHs(mol)
        result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if result == -1:
            AllChem.EmbedMolecule(mol, AllChem.ETKDG())
        AllChem.MMFFOptimizeMolecule(mol)
        return Chem.MolToMolBlock(mol)
    except Exception:
        return None


_mol_counter = 0

def generate_3dmol_html(smiles: str, angle: str = "", shape: str = "", width: int = 400, height: int = 350) -> str:
    global _mol_counter
    _mol_counter += 1
    container_id = f"mol3d-{_mol_counter}"

    molblock = generate_3d_molblock(smiles)
    if molblock is None:
        return None

    molblock_escaped = molblock.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')

    info_html = ""
    if angle or shape:
        info_html = f'<div style="text-align:center;padding:8px 0 4px 0;font-size:14px;color:#444;">결합각: <b>{angle}</b> · 분자 구조: <b>{shape}</b></div>'

    html = f"""
    <div style="border:1px solid #ddd;border-radius:10px;overflow:hidden;background:#fff;margin:8px 0;">
        {info_html}
        <div id="{container_id}" style="width:100%;height:{height}px;position:relative;"></div>
        <div style="text-align:center;padding:6px;font-size:12px;color:#888;">
            🖱️ 드래그: 회전 · 스크롤: 확대/축소 · 우클릭 드래그: 이동
        </div>
    </div>
    <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
    <script>
    (function() {{
        let container = document.getElementById('{container_id}');
        let viewer = $3Dmol.createViewer(container, {{
            backgroundColor: 'white'
        }});
        let molData = `{molblock_escaped}`;
        viewer.addModel(molData, 'sdf');
        viewer.setStyle({{}}, {{
            stick: {{radius: 0.15, colorscheme: 'Jmol'}},
            sphere: {{scale: 0.3, colorscheme: 'Jmol'}}
        }});
        viewer.zoomTo();
        viewer.render();
        viewer.spin('y', 1);
        setTimeout(function() {{ viewer.spin(false); }}, 3000);
    }})();
    </script>
    """
    return html


def render_molecule_png(smiles: str, width: int = 350, height: int = 250) -> bytes:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    mol = Chem.AddHs(mol)
    AllChem.Compute2DCoords(mol)

    drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
    opts = drawer.drawOptions()
    opts.addAtomIndices = False
    opts.bondLineWidth = 2.0
    opts.padding = 0.15
    opts.additionalAtomLabelPadding = 0.1

    try:
        opts.explicitMethyl = True
    except AttributeError:
        pass

    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def _calc_lone_pairs(atom):
    if atom.GetAtomicNum() == 1:
        return 0
    pt = Chem.GetPeriodicTable()
    valence_e = pt.GetNOuterElecs(atom.GetAtomicNum())
    fc = atom.GetFormalCharge()
    bond_order_sum = sum(b.GetBondTypeAsDouble() for b in atom.GetBonds())
    lp_electrons = valence_e - fc - bond_order_sum
    return max(0, int(lp_electrons) // 2)


def _find_lp_angles(neighbor_angles, lp_count):
    if len(neighbor_angles) == 0:
        return [i * 2 * math.pi / max(lp_count, 1) for i in range(lp_count)]

    sorted_angles = sorted(neighbor_angles)
    gaps = []
    n = len(sorted_angles)
    for i in range(n):
        a1 = sorted_angles[i]
        a2 = sorted_angles[(i + 1) % n]
        gap = a2 - a1
        if gap <= 0:
            gap += 2 * math.pi
        mid = a1 + gap / 2
        gaps.append((gap, mid))

    gaps.sort(key=lambda g: -g[0])

    if lp_count <= len(gaps):
        return [g[1] for g in gaps[:lp_count]]

    candidate = []
    for gap_size, gap_mid in gaps:
        if len(candidate) >= lp_count:
            break
        remaining = lp_count - len(candidate)
        slots = min(remaining, max(1, int(gap_size / (math.pi / 2))))
        for j in range(slots):
            offset = (j - (slots - 1) / 2) * (gap_size / (slots + 1))
            candidate.append(gap_mid + offset)
            if len(candidate) >= lp_count:
                break
    return candidate


def render_lewis_png(smiles: str, width: int = 400, height: int = 300) -> bytes:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    mol = Chem.AddHs(mol)
    AllChem.Compute2DCoords(mol)

    drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
    opts = drawer.drawOptions()
    opts.addAtomIndices = False
    opts.bondLineWidth = 2.5
    opts.padding = 0.25
    opts.additionalAtomLabelPadding = 0.15
    try:
        opts.explicitMethyl = True
    except AttributeError:
        pass

    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    atom_coords = {}
    for atom in mol.GetAtoms():
        idx = atom.GetIdx()
        pt = drawer.GetDrawCoords(idx)
        atom_coords[idx] = (pt.x, pt.y)

    lp_info = {}
    for atom in mol.GetAtoms():
        idx = atom.GetIdx()
        lp = _calc_lone_pairs(atom)
        if lp > 0:
            lp_info[idx] = lp

    png_data = drawer.GetDrawingText()
    img = Image.open(BytesIO(png_data)).convert('RGBA')
    draw = ImageDraw.Draw(img)

    dot_radius = 3
    dot_distance = 28
    pair_spacing = 7

    for idx, lp_count in lp_info.items():
        x, y = atom_coords[idx]
        atom = mol.GetAtomWithIdx(idx)

        neighbor_angles = []
        for neighbor in atom.GetNeighbors():
            nidx = neighbor.GetIdx()
            nx, ny = atom_coords[nidx]
            angle = math.atan2(ny - y, nx - x)
            neighbor_angles.append(angle)

        candidate_angles = _find_lp_angles(neighbor_angles, lp_count)

        for angle in candidate_angles:
            dx_dir = math.cos(angle)
            dy_dir = math.sin(angle)
            cx = x + dx_dir * dot_distance
            cy = y + dy_dir * dot_distance

            perp_dx, perp_dy = -dy_dir, dx_dir
            d1x = cx + perp_dx * pair_spacing / 2
            d1y = cy + perp_dy * pair_spacing / 2
            d2x = cx - perp_dx * pair_spacing / 2
            d2y = cy - perp_dy * pair_spacing / 2

            draw.ellipse([d1x - dot_radius, d1y - dot_radius,
                          d1x + dot_radius, d1y + dot_radius], fill='black')
            draw.ellipse([d2x - dot_radius, d2y - dot_radius,
                          d2x + dot_radius, d2y + dot_radius], fill='black')

    output = BytesIO()
    img.save(output, format='PNG')
    return output.getvalue()


def display_assistant_message(text: str):
    """
    Parses the text for MOL tags, displays the cleaned text, 
    and renders 3D visualization in Streamlit.
    """
    mol_tags = parse_mol_tags(text)
    clean_text = remove_all_vis_tags(text)
    
    st.markdown(clean_text)
    
    for tag in mol_tags:
        smiles = tag.get('smiles', '')
        angle = tag.get('angle', '')
        shape = tag.get('shape', '')
        
        if smiles:
            html = generate_3dmol_html(smiles=smiles, angle=angle, shape=shape, height=350)
            if html:
                components.html(html, height=380, scrolling=False)
