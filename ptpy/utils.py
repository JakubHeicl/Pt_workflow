from pathlib import Path

from .scripts import lanl_header, dz_header, cube_header
from .config import MEMORY, NUMBER_OF_CORES, BASES_FOLDER

_SYMBOLS = {
    "X",
    "H", "He",
    "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar",
    "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr",
    "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "In", "Sn", "Sb", "Te", "I", "Xe",
    "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn",
    "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr",
    "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn",
    "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}

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

def xyz_to_lanl(input_file, output_file, charge, mult):
    input_path = Path(input_file)
    output_path = Path(output_file)
    lines = input_path.read_text(encoding="utf-8").splitlines()
    geometry_lines = [f"{line}\n" for line in lines[2:]]
    _write_lanl_input(output_path, int(charge), int(mult), geometry_lines)

def com_to_lanl(input_file, output_file):
    input_path = Path(input_file)
    output_path = Path(output_file)
    charge, mult, geometry_lines = _extract_com_data(input_path)
    _write_lanl_input(output_path, charge, mult, geometry_lines)
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

def _write_lanl_input(output_file: Path, charge: int, mult: int, geometry_lines: list[str]) -> None:
    header = lanl_header.substitute(
        memory=MEMORY,
        num_cpus=NUMBER_OF_CORES,
        job_description="LANL optimization",
        charge=charge,
        mult=mult
    )
    content = header + "".join(geometry_lines) + "\n"
    output_file.write_text(content, encoding="utf-8")

def make_dz_file(output_file: Path, geometry_lines: list[str], atom_symbols: set[str], charge: int, mult: int, bases_folder: Path = BASES_FOLDER):
    
    header = dz_header.substitute(
        memory=MEMORY,
        num_cpus=NUMBER_OF_CORES,
        check_file=output_file.with_suffix(".chk").name,
        job_description="DZ optimization and frequency calculation",
        charge=charge,
        mult=mult
    )

    content = header + "".join(geometry_lines) + "\n"

    relevant_atoms = ["O", "N", "C", "H", "F"]

    for atom in atom_symbols:
        if atom in relevant_atoms:
            content += (atom + " ")

    content += "\n6-31+G(d)\n****\n"

    for atom in atom_symbols:
        content += getbasis(output_file.stem, atom, bases_folder)

    content += "\n"

    for atom in atom_symbols:
        content += getpot(output_file.stem, atom, bases_folder)

    content += "\n\n"

    header = cube_header.substitute(
        memory=MEMORY,
        num_cpus=NUMBER_OF_CORES,
        check_file=output_file.with_suffix(".chk").name,
        job_description="Cube file generation for density and potential",
        charge=charge,
        mult=mult
    )

    content += "\n"

    for atom in atom_symbols:
        if atom in relevant_atoms:
            content += f"{atom} "

    content += "\n6-31+G(d)\n****\n"

    for atom in atom_symbols:
        content += getbasis(output_file.stem, atom, bases_folder)

    content += "\n"

    for atom in atom_symbols:
        content += getpot(output_file.stem, atom, bases_folder)

    content += f"\n{output_file.with_suffix('.pot').name}\n{output_file.with_suffix('.den').name}\n\n"

    content += f"$NBO archive plot file={output_file.stem} $END\n"

    with open(output_file, "w") as file:
        file.write(content)

