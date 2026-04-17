from pathlib import Path

from .scripts import lanl_header, dz_header, cube_header, ligand_header
from .config import MEMORY, GAUSSIAN_NUM_CORES, BASES_FOLDER
from .ir import _SYMBOLS, Geometry

def getbasis(name, atom, bases_folder: Path):
    
    if atom == "H" or atom == "C" or atom == "O" or atom == "N" or atom == "F":
        return ""
    
    basis_file = Path(bases_folder, f"{atom}_opt_plus_bas")

    try:
        with open(basis_file, "r") as file:
            data = file.read()
            return data
    except:
        print(f"I dont have basis for {name} for the atom {atom}")
        return f"({atom})"
        
def getpot(name, atom, bases_folder: Path):
    
    if atom == "H" or atom == "C" or atom == "O" or atom == "N" or atom == "F":
        return ""
    
    basis_file = Path(bases_folder, f"{atom}_pot")

    try:
        with open(basis_file) as file:
            data = file.read()
            return data
    except:
        print(f"I dont have potential for {name} for the atom {atom}")
        return f"({atom})"

def xyz_to_lanl(input_file, output_file, chk_file, charge, mult):
    input_path = Path(input_file)
    output_path = Path(output_file)
    lines = input_path.read_text(encoding="utf-8").splitlines()
    geometry_lines = [f"{line}\n" for line in lines[2:]]
    _write_lanl_input(output_path, chk_file, int(charge), int(mult), geometry_lines)

def com_to_lanl(input_file, output_file, chk_file):
    input_path = Path(input_file)
    output_path = Path(output_file)
    charge, mult, geometry_lines = _extract_com_data(input_path)
    _write_lanl_input(output_path, chk_file, charge, mult, geometry_lines)
    return charge, mult

def get_charge_and_mult_from_com(input_file):
    charge, mult, _ = _extract_com_data(Path(input_file))
    return charge, mult

def _extract_com_data(input_file: Path) -> tuple[int, int, list[str]]:
    lines = input_file.read_text(encoding="utf-8").splitlines()
    geometry_start = _find_geometry_start(lines)

    charge_line_parts = lines[geometry_start - 1].strip().split()
    if len(charge_line_parts) < 2:
        raise ValueError(f"Missing charge/multiplicity line in {input_file}.")

    charge = int(charge_line_parts[0])
    mult = int(charge_line_parts[1])

    geometry_lines: list[str] = []
    for line in lines[geometry_start:]:
        if _is_geometry_line(line):
            geometry_lines.append(f"{line}\n")
            continue
        break

    return charge, mult, geometry_lines

def _find_geometry_start(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if _is_geometry_line(line):
            return index
    raise ValueError("Could not find geometry block in Gaussian input.")

def _is_geometry_line(line: str) -> bool:
    parts = line.strip().split()
    return len(parts) > 1 and parts[0].capitalize() in _SYMBOLS

def _write_lanl_input(com_file: Path, chk_file: Path, charge: int, mult: int, geometry_lines: list[str]) -> None:
    header = lanl_header.substitute(
        memory=MEMORY,
        num_cpus=GAUSSIAN_NUM_CORES,
        check_file=chk_file.name,
        job_description="LANL optimization",
        charge=charge,
        mult=mult
    )
    content = header + "".join(geometry_lines) + "\n"
    com_file.write_text(content, encoding="utf-8")

def make_dz_file(com_file: Path, chk_file: Path, geometry_lines: list[str], atom_symbols: set[str], charge: int, mult: int, bases_folder: Path = BASES_FOLDER):
    
    header = dz_header.substitute(
        memory=MEMORY,
        num_cpus=GAUSSIAN_NUM_CORES,
        check_file=chk_file.name,
        job_description="DZ optimization and frequency calculation",
        charge=charge,
        mult=mult
    )

    content = header

    for geometry_line in geometry_lines:
        content += geometry_line + "\n"

    content += "\n"

    relevant_atoms = ["O", "N", "C", "H", "F"]

    for atom in atom_symbols:
        if atom in relevant_atoms:
            content += (atom + " ")

    content += "\n6-31+G(d)\n****\n"

    for atom in atom_symbols:
        content += getbasis(com_file.stem, atom, bases_folder)

    content += "\n"

    for atom in atom_symbols:
        content += getpot(com_file.stem, atom, bases_folder)

    content += "\n\n"

    header = cube_header.substitute(
        memory=MEMORY,
        num_cpus=GAUSSIAN_NUM_CORES,
        check_file=chk_file.name,
        job_description="Cube file generation for density and potential",
        charge=charge,
        mult=mult
    )

    content += header

    content += "\n"

    for atom in atom_symbols:
        if atom in relevant_atoms:
            content += f"{atom} "

    content += "\n6-31+G(d)\n****\n"

    for atom in atom_symbols:
        content += getbasis(com_file.stem, atom, bases_folder)

    content += "\n"

    for atom in atom_symbols:
        content += getpot(com_file.stem, atom, bases_folder)

    content += f"\n{com_file.with_suffix('.pot').name}\n{com_file.with_suffix('.den').name}\n\n"

    content += f"$NBO archive plot file={com_file.stem} $END\n"

    with open(com_file, "w") as file:
        file.write(content)

def make_ligand_file(com_file: Path, chk_file: Path, geometry: Geometry, charge: int, mult: int, bases_folder: Path = BASES_FOLDER):

    with open(com_file, "w") as f:
                    
        for i, ligand in enumerate(geometry.ligands):
            
            relevant_atoms = ["O", "N", "C", "H", "F"]
            unique_atoms = []
            for atom in geometry.atoms:
                if atom not in ligand:
                    if atom.symbol not in unique_atoms:
                        unique_atoms.append(atom.symbol)
            
            ligand_charge = geometry.ligand_charges[i] 
            
            for j, ligand2 in enumerate(geometry.ligands):
                if i == j:
                    continue
                if set(ligand) == set(ligand2):
                    ligand_charge += geometry.ligand_charges[j]
        
            if i != 0:
                f.write("--Link1--\n")
                
            f.write(ligand_header.substitute(
                memory=MEMORY,
                num_cpus=GAUSSIAN_NUM_CORES,
                check_file=chk_file.name,
                job_description=f"Ligand {i+1} optimization",
                charge=charge - ligand_charge,
                mult=mult,
                cards="pseudo=cards " if any(atom not in relevant_atoms for atom in unique_atoms) else ""
            ))
            for atom in geometry.atoms:
                if atom not in ligand:
                    f.write(f" {atom.symbol:<5}    {atom.x:>10.6f}  {atom.y:>10.6f}  {atom.z:>10.6f}\n")
                else:
                    #final_file.write(f" {atom.symbol}-Bq    {atom.x:>10.6f}  {atom.y:>10.6f}  {atom.z:>10.6f}\n")
                    pass
                    
            f.write("\n")
            
            for atom in unique_atoms:
                if atom in relevant_atoms:
                    f.write(atom + " ")
            
            if any(atom in relevant_atoms for atom in unique_atoms):
                f.write("\n6-31+G(d)\n")
                f.write("****\n")
                
            for atom in unique_atoms:
                f.write(getbasis(com_file.stem, atom, bases_folder))
                
            f.write("\n")
            
            for atom in unique_atoms:
                f.write(getpot(com_file.stem, atom, bases_folder))
                
            f.write("\n")
            f.write("--Link1--\n")
            f.write(ligand_header.substitute(
                memory=MEMORY,
                num_cpus=GAUSSIAN_NUM_CORES,
                check_file=chk_file.name,
                job_description=f"Ligand {i+1} optimization",
                charge=ligand_charge,
                mult=mult,
                cards="pseudo=cards " if any(atom not in relevant_atoms for atom in unique_atoms) else ""
            ))
            
            unique_atoms = []
            for atom in geometry.atoms:
                if atom in ligand:
                    if atom.symbol not in unique_atoms:
                        unique_atoms.append(atom.symbol)
            
            for atom in geometry.atoms:
                if atom in ligand:
                    f.write(f" {atom.symbol:<5}    {atom.x:>10.6f}  {atom.y:>10.6f}  {atom.z:>10.6f}\n")
                else:
                    #final_file.write(f" {atom.symbol}-Bq    {atom.x:>10.6f}  {atom.y:>10.6f}  {atom.z:>10.6f}\n")
                    pass
                    
            f.write("\n")
            relevant_atoms = ["O", "N", "C", "H", "F"]
            
            for atom in unique_atoms:
                if atom in relevant_atoms:
                    f.write(atom + " ")
            
            if any(atom in relevant_atoms for atom in unique_atoms):
                f.write("\n6-31+G(d)\n")
                f.write("****\n")
            
            for atom in unique_atoms:
                f.write(getbasis(com_file.stem, atom, bases_folder))
                
            f.write("\n")
            
            for atom in unique_atoms:
                f.write(getpot(com_file.stem, atom, bases_folder))
                
            f.write("\n")