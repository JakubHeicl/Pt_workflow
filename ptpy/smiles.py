from pathlib import Path
import csv
import math
import subprocess
import itertools

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

def set_dative_bonds(mol, donor_atomic_nums=(7, 8, 15, 16, 17)):
    """
    Volitelně převede některé donor->metal vazby na dative.
    """
    pt = Chem.GetPeriodicTable()
    rwmol = Chem.RWMol(mol)
    rwmol.UpdatePropertyCache(strict=False)

    def is_transition_metal(at):
        n = at.GetAtomicNum()
        return (22 <= n <= 29) or (40 <= n <= 47) or (72 <= n <= 79)

    for metal in [a for a in rwmol.GetAtoms() if is_transition_metal(a)]:
        metal_idx = metal.GetIdx()
        for nbr in list(metal.GetNeighbors()):
            if nbr.GetAtomicNum() not in donor_atomic_nums:
                continue

            bond = rwmol.GetBondBetweenAtoms(nbr.GetIdx(), metal_idx)
            if bond is None or bond.GetBondType() != Chem.BondType.SINGLE:
                continue

            try:
                default_valence = pt.GetDefaultValence(nbr.GetAtomicNum())
            except Exception:
                default_valence = -1

            try:
                explicit_valence = nbr.GetExplicitValence()
            except Exception:
                explicit_valence = 0

            if default_valence > 0 and explicit_valence > default_valence:
                rwmol.RemoveBond(nbr.GetIdx(), metal_idx)
                rwmol.AddBond(nbr.GetIdx(), metal_idx, Chem.BondType.DATIVE)

    out = rwmol.GetMol()
    Chem.SanitizeMol(out, catchErrors=True)
    return out

def find_pt_atom(mol):
    pts = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 78]
    return pts[0] if pts else None

def guess_pt_bond_length(atom):
    z = atom.GetAtomicNum()
    if z == 7:   # N
        return 2.05
    if z == 8:   # O
        return 2.00
    if z == 15:  # P
        return 2.25
    if z == 16:  # S
        return 2.30
    if z == 17:  # Cl
        return 2.30
    return 2.10

def get_positions_array(mol, conf_id=0):
    conf = mol.GetConformer(conf_id)
    arr = np.zeros((mol.GetNumAtoms(), 3), dtype=float)
    for i in range(mol.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        arr[i] = [p.x, p.y, p.z]
    return arr

def set_positions_array(mol, arr, conf_id=0):
    conf = mol.GetConformer(conf_id)
    for i in range(mol.GetNumAtoms()):
        conf.SetAtomPosition(i, Chem.rdGeometry.Point3D(*arr[i]))

def normalize(v, eps=1e-12):
    n = np.linalg.norm(v)
    if n < eps:
        return v.copy()
    return v / n


def rigid_transform(P, Q):
    """
    Najde rigidní transformaci P -> Q (Kabsch).
    P, Q: (N, 3)
    """
    Pc = P - P.mean(axis=0)
    Qc = Q - Q.mean(axis=0)

    H = Pc.T @ Qc
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T

    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T

    t = Q.mean(axis=0) - R @ P.mean(axis=0)
    return R, t

def apply_rigid_transform(coords, R, t):
    return (R @ coords.T).T + t

def rotation_matrix_about_axis(axis, angle):
    axis = normalize(axis)
    x, y, z = axis
    c = np.cos(angle)
    s = np.sin(angle)
    C = 1.0 - c

    return np.array([
        [c + x*x*C,     x*y*C - z*s, x*z*C + y*s],
        [y*x*C + z*s,   c + y*y*C,   y*z*C - x*s],
        [z*x*C - y*s,   z*y*C + x*s, c + z*z*C]
    ], dtype=float)

def rotate_points_about_axis(points, origin, axis, angle):
    R = rotation_matrix_about_axis(axis, angle)
    shifted = points - origin
    rotated = (R @ shifted.T).T
    return rotated + origin

def orthonormalize(v1, v2=None):
    e1 = normalize(v1)
    if np.linalg.norm(e1) < 1e-8:
        e1 = np.array([1.0, 0.0, 0.0])

    if v2 is None:
        tmp = np.array([0.0, 1.0, 0.0])
        if abs(np.dot(tmp, e1)) > 0.9:
            tmp = np.array([0.0, 0.0, 1.0])
    else:
        tmp = v2 - np.dot(v2, e1) * e1

    e2 = normalize(tmp)
    if np.linalg.norm(e2) < 1e-8:
        tmp = np.array([0.0, 1.0, 0.0])
        if abs(np.dot(tmp, e1)) > 0.9:
            tmp = np.array([0.0, 0.0, 1.0])
        tmp = tmp - np.dot(tmp, e1) * e1
        e2 = normalize(tmp)

    e3 = normalize(np.cross(e1, e2))
    if np.linalg.norm(e3) < 1e-8:
        e3 = np.array([0.0, 0.0, 1.0])

    e2 = normalize(np.cross(e3, e1))
    return e1, e2, e3

def best_fit_plane_basis(vectors):
    """
    Udělá lokální bázi roviny donorů kolem Pt pro square-planar případ.
    """
    X = np.array(vectors, dtype=float)
    Xc = X - X.mean(axis=0)

    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)

    if Vt.shape[0] >= 2:
        e1 = Vt[0]
        e2 = Vt[1]
    else:
        e1 = np.array([1.0, 0.0, 0.0])
        e2 = np.array([0.0, 1.0, 0.0])

    e1, e2, _ = orthonormalize(e1, e2)
    return e1, e2

def best_fit_3d_basis(vectors):
    """
    Lokální 3D báze pro oktaedrický případ.
    """
    X = np.array(vectors, dtype=float)
    Xc = X - X.mean(axis=0)

    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)

    if Vt.shape[0] >= 2:
        e1 = Vt[0]
        e2 = Vt[1]
    else:
        e1 = np.array([1.0, 0.0, 0.0])
        e2 = np.array([0.0, 1.0, 0.0])

    e1, e2, e3 = orthonormalize(e1, e2)
    return e1, e2, e3

def local_steric_score(mol, positions, pt_idx, frag_atoms, donor_idxs):
    """
    Menší score = lepší orientace.
    Tvrdě trestá H blízko Pt a obecně příliš těsné kontakty.
    """
    score = 0.0
    pt_pos = positions[pt_idx]
    frag_set = set(frag_atoms)
    donor_set = set(donor_idxs)

    n_atoms = mol.GetNumAtoms()

    for i in frag_atoms:
        if i in donor_set:
            continue

        zi = mol.GetAtomWithIdx(i).GetAtomicNum()
        pi = positions[i]

        # 1) Trest za blízkost k Pt
        dpt = np.linalg.norm(pi - pt_pos)

        if zi == 1:
            cutoff = 2.30
            weight = 1000.0
        else:
            cutoff = 2.35
            weight = 150.0

        if dpt < cutoff:
            score += weight * (cutoff - dpt) ** 2

        # 2) Trest za kolize s ostatními fragmenty
        for j in range(n_atoms):
            if j == pt_idx or j in frag_set:
                continue

            zj = mol.GetAtomWithIdx(j).GetAtomicNum()
            pj = positions[j]
            dij = np.linalg.norm(pi - pj)

            if zi == 1 or zj == 1:
                cutoff_ij = 1.45
                weight_ij = 40.0
            else:
                cutoff_ij = 1.85
                weight_ij = 20.0

            if dij < cutoff_ij:
                score += weight_ij * (cutoff_ij - dij) ** 2

    return score

def optimize_monodentate_torsions(mol, positions, pt_idx, frags, atom_to_frag, angle_step_deg=15):
    """
    Pro každý monodentátní ligand:
    - osa = Pt--donor
    - rotuje celý fragment kolem této osy
    - vybere orientaci s nejmenším sterickým score
    """
    pt_atom = mol.GetAtomWithIdx(pt_idx)
    donor_neighbors = [a.GetIdx() for a in pt_atom.GetNeighbors()]

    frag_to_donors = {}
    for d in donor_neighbors:
        frag_id = atom_to_frag.get(d, None)
        if frag_id is not None:
            frag_to_donors.setdefault(frag_id, []).append(d)

    new_positions = positions.copy()

    for frag_id, donor_idxs in frag_to_donors.items():
        if len(donor_idxs) != 1:
            continue

        donor = donor_idxs[0]
        frag_atoms = list(frags[frag_id])

        if len(frag_atoms) <= 2:
            continue

        donor_pos = new_positions[donor]
        pt_pos = new_positions[pt_idx]

        axis = donor_pos - pt_pos
        if np.linalg.norm(axis) < 1e-8:
            continue

        base_positions = new_positions.copy()
        base_frag_coords = base_positions[frag_atoms].copy()

        best_score = local_steric_score(
            mol, base_positions, pt_idx, frag_atoms, donor_idxs
        )
        best_frag_coords = base_frag_coords.copy()

        for angle_deg in range(0, 360, angle_step_deg):
            angle = np.deg2rad(angle_deg)

            rotated = rotate_points_about_axis(
                base_frag_coords,
                origin=donor_pos,
                axis=axis,
                angle=angle
            )

            trial_positions = base_positions.copy()
            for local_i, global_i in enumerate(frag_atoms):
                trial_positions[global_i] = rotated[local_i]

            score = local_steric_score(
                mol, trial_positions, pt_idx, frag_atoms, donor_idxs
            )

            if score < best_score:
                best_score = score
                best_frag_coords = rotated.copy()

        for local_i, global_i in enumerate(frag_atoms):
            new_positions[global_i] = best_frag_coords[local_i]

    return new_positions

def cut_pt_bonds_and_get_fragments(mol, pt_idx):
    """
    Logicky odřízne vazby Pt-L a vrátí fragmenty jako tuple indexů.
    """
    rwmol = Chem.RWMol(mol)
    pt_atom = mol.GetAtomWithIdx(pt_idx)
    donor_neighbors = [a.GetIdx() for a in pt_atom.GetNeighbors()]

    for nbr in donor_neighbors:
        if rwmol.GetBondBetweenAtoms(pt_idx, nbr) is not None:
            rwmol.RemoveBond(pt_idx, nbr)

    cut_mol = rwmol.GetMol()
    frags = Chem.GetMolFrags(cut_mol, asMols=False, sanitizeFrags=False)
    return donor_neighbors, frags


def build_fragment_map(frags):
    atom_to_frag = {}
    for frag_id, frag in enumerate(frags):
        for idx in frag:
            atom_to_frag[idx] = frag_id
    return atom_to_frag


def fragment_centroid(positions, atom_indices, exclude=None, heavy_only=True, mol=None):
    exclude = set() if exclude is None else set(exclude)
    use = []
    for idx in atom_indices:
        if idx in exclude:
            continue
        if heavy_only and mol is not None and mol.GetAtomWithIdx(idx).GetAtomicNum() == 1:
            continue
        use.append(idx)

    if not use:
        for idx in atom_indices:
            if idx not in exclude:
                use.append(idx)

    if not use:
        return None

    return positions[use].mean(axis=0)


def fragment_anchor_source_point(mol, positions, frag_atom_indices, donor_indices):
    """
    Pomocný třetí bod pro fixaci 'twistu' fragmentu.
    """
    dcent = positions[donor_indices].mean(axis=0)
    c = fragment_centroid(
        positions,
        frag_atom_indices,
        exclude=set(donor_indices),
        heavy_only=True,
        mol=mol
    )

    if c is None:
        return None

    v = c - dcent
    if np.linalg.norm(v) < 1e-8:
        return None

    return dcent + normalize(v)

def square_planar_targets_from_current_geometry(mol, positions, pt_idx, donor_indices):
    """
    Vezme aktuální donorové pozice a 'snapne' je do square-planar roviny,
    ale zachová jejich cyklické pořadí.
    """
    pt = positions[pt_idx]
    donor_vecs = [positions[i] - pt for i in donor_indices]
    e1, e2 = best_fit_plane_basis(donor_vecs)

    angles = []
    for idx in donor_indices:
        r = positions[idx] - pt
        x = np.dot(r, e1)
        y = np.dot(r, e2)
        theta = math.atan2(y, x)
        angles.append((theta, idx))

    angles.sort()
    ordered = [idx for theta, idx in angles]
    start = angles[0][0]

    targets = {}
    for j, idx in enumerate(ordered):
        theta_t = start + j * (math.pi / 2.0)
        atom = mol.GetAtomWithIdx(idx)
        r = guess_pt_bond_length(atom)
        direction = math.cos(theta_t) * e1 + math.sin(theta_t) * e2
        direction = normalize(direction)
        targets[idx] = pt + r * direction

    return ordered, targets

def octahedral_targets_from_current_geometry(mol, positions, pt_idx, donor_indices):
    """
    Pro 6 donorů udělá oktaedrické cílové body:
    +e1, -e1, +e2, -e2, +e3, -e3

    Donory přiřadí k těmto směrům tak, aby to co nejlépe odpovídalo
    aktuálnímu embeddingu.
    """
    pt = positions[pt_idx]
    donor_vecs = {}
    donor_unit = {}

    for idx in donor_indices:
        v = positions[idx] - pt
        donor_vecs[idx] = v
        donor_unit[idx] = normalize(v)

    e1, e2, e3 = best_fit_3d_basis(list(donor_vecs.values()))

    directions = [
        ("+e1",  e1),
        ("-e1", -e1),
        ("+e2",  e2),
        ("-e2", -e2),
        ("+e3",  e3),
        ("-e3", -e3),
    ]

    donor_list = list(donor_indices)

    # brute force nad 6! = 720 permutacemi, což je v pohodě
    best_perm = None
    best_score = -1e99

    for perm in itertools.permutations(range(6)):
        score = 0.0
        for donor_i, dir_i in zip(donor_list, perm):
            dvec = directions[dir_i][1]
            score += float(np.dot(donor_unit[donor_i], dvec))
        if score > best_score:
            best_score = score
            best_perm = perm

    ordered = []
    targets = {}

    for donor_i, dir_i in zip(donor_list, best_perm):
        label, dvec = directions[dir_i]
        atom = mol.GetAtomWithIdx(donor_i)
        r = guess_pt_bond_length(atom)
        targets[donor_i] = pt + r * normalize(dvec)
        ordered.append(donor_i)

    return ordered, targets

def coordination_targets_from_current_geometry(mol, positions, pt_idx, donor_indices):
    n = len(donor_indices)
    if n == 4:
        ordered, targets = square_planar_targets_from_current_geometry(
            mol, positions, pt_idx, donor_indices
        )
        return "square_planar", ordered, targets

    if n == 6:
        ordered, targets = octahedral_targets_from_current_geometry(
            mol, positions, pt_idx, donor_indices
        )
        return "octahedral", ordered, targets

    return None, None, None

def force_coordination_geometry_by_rigid_fragments(mol, conf_id=0):
    """
    Klíčová funkce:
    - najde Pt
    - zjistí koordinační číslo
    - pro 4 sousedy dělá square-planar
    - pro 6 sousedů dělá octahedral
    - rozdělí ligandy na fragmenty
    - každý fragment rigidně přenese do cílového uspořádání
    """
    pt_idx = find_pt_atom(mol)
    if pt_idx is None:
        return False, "no_pt"

    pt_atom = mol.GetAtomWithIdx(pt_idx)
    donor_neighbors = [a.GetIdx() for a in pt_atom.GetNeighbors()]

    if len(donor_neighbors) not in (4, 6):
        return False, f"pt_coord_{len(donor_neighbors)}"

    positions = get_positions_array(mol, conf_id=conf_id)
    pt_pos = positions[pt_idx].copy()

    geom_tag, ordered_donors, donor_targets = coordination_targets_from_current_geometry(
        mol, positions, pt_idx, donor_neighbors
    )

    if geom_tag is None:
        return False, f"unsupported_coord_{len(donor_neighbors)}"

    donor_neighbors_cut, frags = cut_pt_bonds_and_get_fragments(mol, pt_idx)
    atom_to_frag = build_fragment_map(frags)

    new_positions = positions.copy()
    new_positions[pt_idx] = pt_pos

    frag_to_donors = {}
    for d in donor_neighbors:
        frag_id = atom_to_frag.get(d, None)
        if frag_id is None:
            continue
        frag_to_donors.setdefault(frag_id, []).append(d)

    for frag_id, donor_idxs in frag_to_donors.items():
        frag_atoms = list(frags[frag_id])

        P = [positions[d] for d in donor_idxs]
        Q = [donor_targets[d] for d in donor_idxs]

        src_anchor = fragment_anchor_source_point(mol, positions, frag_atoms, donor_idxs)
        if src_anchor is not None:
            donor_target_centroid = np.mean(np.array(Q), axis=0)
            outward = donor_target_centroid - pt_pos

            if np.linalg.norm(outward) < 1e-8:
                if geom_tag == "square_planar":
                    outward = np.array([0.0, 0.0, 1.0])
                else:
                    outward = np.array([1.0, 0.0, 0.0])

            tgt_anchor = donor_target_centroid + normalize(outward)

            P.append(src_anchor)
            Q.append(tgt_anchor)

        P = np.array(P, dtype=float)
        Q = np.array(Q, dtype=float)
        frag_coords = positions[frag_atoms]

        if len(frag_atoms) == 1:
            shift = donor_targets[donor_idxs[0]] - positions[donor_idxs[0]]
            new_positions[frag_atoms[0]] = positions[frag_atoms[0]] + shift
            continue

        if len(P) >= 2:
            try:
                R, t = rigid_transform(P, Q)
                transformed = apply_rigid_transform(frag_coords, R, t)
                for local_i, global_i in enumerate(frag_atoms):
                    new_positions[global_i] = transformed[local_i]
            except Exception:
                src_cent = positions[donor_idxs].mean(axis=0)
                tgt_cent = np.array([donor_targets[d] for d in donor_idxs]).mean(axis=0)
                shift = tgt_cent - src_cent
                for idx in frag_atoms:
                    new_positions[idx] = positions[idx] + shift
        else:
            src_cent = positions[donor_idxs].mean(axis=0)
            tgt_cent = np.array([donor_targets[d] for d in donor_idxs]).mean(axis=0)
            shift = tgt_cent - src_cent
            for idx in frag_atoms:
                new_positions[idx] = positions[idx] + shift

    new_positions = optimize_monodentate_torsions(
        mol, new_positions, pt_idx, frags, atom_to_frag, angle_step_deg=15
    )

    set_positions_array(mol, new_positions, conf_id=conf_id)
    return True, f"{geom_tag}+rigid_fragments+torsi_opt"


def relax_surroundings_keep_coordination(mol, conf_id=0, max_iters=1000):
    """
    Lehká FF relaxace:
    - Pt a donorové atomy fixne
    - zbytek může mírně povolit
    """
    pt_idx = find_pt_atom(mol)
    if pt_idx is None:
        return "no_pt"

    pt_atom = mol.GetAtomWithIdx(pt_idx)
    donor_idxs = [a.GetIdx() for a in pt_atom.GetNeighbors()]

    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            props = AllChem.MMFFGetMoleculeProperties(mol)
            ff = AllChem.MMFFGetMoleculeForceField(mol, props, confId=conf_id)
            ff.AddFixedPoint(pt_idx)
            for d in donor_idxs:
                ff.AddFixedPoint(d)
            ff.Initialize()
            ff.Minimize(maxIts=max_iters)
            return "mmff_relaxed"
    except Exception:
        pass

    try:
        if AllChem.UFFHasAllMoleculeParams(mol):
            ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
            ff.AddFixedPoint(pt_idx)
            for d in donor_idxs:
                ff.AddFixedPoint(d)
            ff.Initialize()
            ff.Minimize(maxIts=max_iters)
            return "uff_relaxed"
    except Exception:
        pass

    return "no_ff"

def rdkit_generate_3d(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, "parse_failed"

    try:
        mol = set_dative_bonds(mol)
    except Exception:
        pass

    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    params.numThreads = 0
    params.randomSeed = 42

    code = AllChem.EmbedMolecule(mol, params)
    if code != 0:
        return None, "embed_failed"

    method = "rdkit_etkdg"

    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            AllChem.MMFFOptimizeMolecule(mol, maxIters=80)
            method = "rdkit_mmff"
        elif AllChem.UFFHasAllMoleculeParams(mol):
            AllChem.UFFOptimizeMolecule(mol, maxIters=80)
            method = "rdkit_uff"
    except Exception:
        pass

    ok, tag = force_coordination_geometry_by_rigid_fragments(mol)
    method += f"+{tag}"

    if ok:
        relax_tag = relax_surroundings_keep_coordination(mol, max_iters=80)
        method += f"+{relax_tag}"

    return mol, method

def obabel_fallback_to_xyz(smiles, out_xyz):
    tmp_smi = Path("tmp_input.smi")
    tmp_smi.write_text(smiles + "\n", encoding="utf-8")

    result = subprocess.run(
        ["obabel", str(tmp_smi), "-O", str(out_xyz), "--gen3d", "--fastest"],
        capture_output=True,
        text=True
    )

    tmp_smi.unlink(missing_ok=True)
    return result.returncode == 0

def xyz_to_com(xyz_path, com_path, title="generated", charge=0, mult=1, route_line="#p"):
    lines = Path(xyz_path).read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise ValueError(f"Neplatny XYZ soubor: {xyz_path}")

    natoms = int(lines[0].strip())
    coord_lines = lines[2:2 + natoms]

    with open(com_path, "w", encoding="utf-8") as f:
        f.write("%chk=" + com_path.with_suffix(".chk").name + "\n")
        f.write(route_line + "\n\n")
        f.write(title + "\n\n")
        f.write(f"{charge} {mult}\n")
        for line in coord_lines:
            f.write(line.strip() + "\n")
        f.write("\n")


def write_gaussian_com(mol, path, title="generated", charge=0, mult=1, route_line="#p"):
    conf = mol.GetConformer()
    with open(path, "w", encoding="utf-8") as f:
        f.write("%chk=" + path.with_suffix(".chk").name + "\n")
        f.write(route_line + "\n\n")
        f.write(title + "\n\n")
        f.write(f"{charge} {mult}\n")
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            f.write(f"{atom.GetSymbol():<3} {pos.x: .6f} {pos.y: .6f} {pos.z: .6f}\n")
        f.write("\n")

def process_smiles_file(input_smi, out_dir, charge=0, mult=1, route_line="#p"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    with open(input_smi, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            smiles = parts[0]
            mol_id = parts[1] if len(parts) > 1 else f"mol_{i:06d}"

            com_path = out_dir / f"{mol_id}.com"
            xyz_path = out_dir / f"{mol_id}.xyz"

            mol, method = rdkit_generate_3d(smiles)

            if mol is not None:
                write_gaussian_com(
                    mol,
                    com_path,
                    title=mol_id,
                    charge=charge,
                    mult=mult,
                    route_line=route_line,
                )
                rows.append((mol_id, smiles, method, "ok"))
            else:
                ok = obabel_fallback_to_xyz(smiles, xyz_path)
                if ok:
                    xyz_to_com(
                        xyz_path,
                        com_path,
                        title=mol_id,
                        charge=charge,
                        mult=mult,
                        route_line=route_line,
                    )
                    rows.append((mol_id, smiles, "obabel_fastest", "ok"))
                else:
                    rows.append((mol_id, smiles, method, "failed"))

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "smiles", "method", "final_status"])
        w.writerows(rows)


if __name__ == "__main__":
    process_smiles_file(
        input_smi="input.smi",
        out_dir="generated_com",
        charge=0,
        mult=1,
        route_line="#p"
    )