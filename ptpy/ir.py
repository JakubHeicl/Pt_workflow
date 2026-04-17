from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from enum import Enum
import json
import numpy as np

_SYMBOLS: list[str] = [
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
]

class Atom:

    def __init__(self, atomic_number: int, x: float, y: float, z: float):
        self.atomic_number = atomic_number
        self.x = x
        self.y = y
        self.z = z

    @property
    def symbol(self) -> str:
        return _SYMBOLS[self.atomic_number]
    
    def to_json(self) -> dict:
        return {
            "atomic_number": self.atomic_number,
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }
    
    @classmethod
    def from_json(cls, data: dict) -> "Atom":
        return cls(
            atomic_number=data["atomic_number"],
            x=data["x"],
            y=data["y"],
            z=data["z"]
        )
    
    def coordinates(self):
        return np.array([self.x, self.y, self.z])

    def distance_to(self, atom2: Atom) -> float:
        return np.linalg.norm(self.coordinates() - atom2.coordinates())

class LigandError(Exception):
    def __init__(self, message):
        super().__init__(message)

@dataclass
class Geometry:
    atoms: list[Atom]
    pt_neighbors: list[Atom] | None = None
    ligands: list[list[Atom]] | None = None
    ligand_charges: list[int] | None = None 

    def detect_and_store_ligands(self) -> None:
        try:
            if self.pt_neighbors is None:
                self.pt_neighbors = self.find_nearest_neighbors(self.get_pt_atom(), num_neighbors=6, for_Pt=True)
            ligands = self._find_ligands()
            self.ligands = ligands
        except Exception as e:
            self.ligands = None
            raise LigandError(f"Failed to automatically find ligands: {e}.")

    def to_json(self) -> dict:
        return {
            "atoms": [atom.to_json() for atom in self.atoms],
            "pt_neighbors": [self.get_atom_index(atom) for atom in self.pt_neighbors] if self.pt_neighbors is not None else None,
            "ligands": [[self.get_atom_index(atom) for atom in ligand] for ligand in self.ligands] if self.ligands is not None else None,
            "ligand_charges": self.ligand_charges if self.ligand_charges is not None else None,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Geometry":
        atoms=[Atom.from_json(atom_data) for atom_data in data.get("atoms", [])]
        return cls(
            atoms=atoms,
            pt_neighbors=[atoms[atom_index] for atom_index in data.get("pt_neighbors", [])] if data.get("pt_neighbors") is not None else None,
            ligands=[[atoms[atom_index] for atom_index in ligand_data] for ligand_data in data.get("ligands", [])] if data.get("ligands") is not None else None,
            ligand_charges=data.get("ligand_charges") if data.get("ligand_charges") is not None else None,
        )
    
    @property
    def geometry_lines(self) -> list[str]:
        return [f"{atom.symbol}     {atom.x:12.7f}  {atom.y:12.7f}  {atom.z:12.7f}" for atom in self.atoms]
    
    @property
    def atoms_symbols(self) -> set[str]:
        return set(atom.symbol for atom in self.atoms)
    
    @property
    def number_of_atoms(self) -> int:
        return len(self.atoms)
    
    def get_atom_index(self, target_atom) -> int:
        for i, atom in enumerate(self.atoms):
            if atom == target_atom:
                return i
        raise Exception("Atom not found in geometry.")
    
    def get_atom_number(self, target_atom: Atom) -> int:
        return self.get_atom_index(target_atom) + 1

    def get_pt_atom(self) -> Atom | None:
        for atom in self.atoms:
            if atom.symbol == "Pt":
                return atom
        return None
    
    def get_atom_by_index(self, index: int) -> Atom:
        if index < 0 or index >= len(self.atoms):
            raise IndexError("Atom index out of range.")
        return self.atoms[index]
    
    def get_atom_by_number(self, number: int) -> Atom:
        return self.get_atom_by_index(number - 1)

    def find_nearest_neighbors(self, target_atom: Atom, num_neighbors: int, for_Pt: bool = False) -> list[Atom]:
        distances = []
        for atom in self.atoms:
            if atom != target_atom and ((not for_Pt) or (atom.symbol != "H")):
                dist = target_atom.distance_to(atom)
                distances.append((atom, dist))
        
        distances.sort(key=lambda x: x[1])
        
        return list(map(list, zip(*distances[:num_neighbors])))[0]
    
    def _find_ligands(self) -> list[list[Atom]] | None:
        
        ligands: list[list[Atom]] = []
        pt_neighbors = self.pt_neighbors
        assigned_atoms = set(pt_neighbors) #Set for tracking which atoms have already been assigned to a ligand, starting with Pt neighbors
        assigned_atoms.add(self.get_pt_atom())

        #Every neighbor of Pt is a starting point for a ligand, we will expand from there and then merge ligands if they are linked together
        for pt_neighbor in pt_neighbors:
            ligand = [pt_neighbor]
            queue = [pt_neighbor]  # We will use a queue to perform a breadth-first search for neighboring atoms to add to the ligand
        
            while queue:
                current_atom = queue.pop(0)
                
                if current_atom.symbol == "H":
                    num_neighbors = 1
                    max_dist = 1.7
                elif current_atom.symbol == "O":
                    num_neighbors = 3
                    max_dist = 1.7
                else:
                    num_neighbors = 4
                    max_dist= 2
                
                new_atoms = self.find_nearest_neighbors(current_atom, num_neighbors)  # Find neighbors of the current atom to potentially add to the ligand
            
                for new_atom in new_atoms:
                    if new_atom not in assigned_atoms:
                        too_close = any(
                            new_atom.distance_to(other_ligand_atom) < 1.75
                            for other_ligand in ligands
                            for other_ligand_atom in other_ligand
                            )
                        too_far = current_atom.distance_to(new_atom) > max_dist
                        if not too_close and not too_far:
                            ligand.append(new_atom)
                            queue.append(new_atom)  # Add the new atom to the queue to find its neighbors in the next iterations
                            assigned_atoms.add(new_atom)

            ligands.append(ligand)
            
        linked_ligands = any(
            ligand_atom.distance_to(other_ligand_atom) < 1.75
            for ligand in ligands
            for ligand_atom in ligand
            for other_ligand in ligands if not other_ligand == ligand
            for other_ligand_atom in other_ligand)
        
        while linked_ligands:
            merged = False
            for ligand in ligands:
                for ligand_atom in ligand:
                    for other_ligand in ligands:
                        if other_ligand == ligand:
                            continue
                        for other_ligand_atom in other_ligand:
                            if ligand_atom.distance_to(other_ligand_atom) < 1.75:
                                
                                ligand.extend(other_ligand)
                                ligands.remove(other_ligand)
                                merged = True
                                break
                        if merged:
                            break
                    if merged:
                        break
                if merged:
                    break
            linked_ligands = any(
                ligand_atom.distance_to(other_ligand_atom) < 1.75
                for ligand in ligands
                for ligand_atom in ligand
                for other_ligand in ligands if not other_ligand == ligand
                for other_ligand_atom in other_ligand)
        
        sum_of_atoms = 1
        for ligand in ligands:
            sum_of_atoms += len(ligand)
            
        if sum_of_atoms != self.number_of_atoms:
            raise LigandError("Some atoms were not assigned to any ligand.")
        
        final_ligands = []
        
        for atom in pt_neighbors:
            for ligand in ligands:
                if atom in ligand:
                    final_ligands.append(ligand)

        #sort the ligands by the pt neighbor they are linked to, so the order of ligands is always the same and corresponds to the order of pt neighbors
        sorted_final_ligands = []
        for pt_neighbor in pt_neighbors:
            for ligand in final_ligands:
                if pt_neighbor in ligand:
                    sorted_final_ligands.append(ligand)
                    break

        return sorted_final_ligands

    def ligand_to_str(self, ligand_index):
        ligand: list[Atom] = self.ligands[ligand_index]
        final_string = ""
        
        for atom in ligand:
            final_string = f"{final_string}{atom.symbol}{self.get_atom_number(atom)} "
            
        return final_string.strip()

class CalculationType(Enum):
    LANL_OPT = "lanl_opt"
    DZ_OPT = "dz_opt"
    AIM_ANALYSIS = "aim_analysis"
    LIGAND_ENERGIES_CALCULATION = "ligand_energies_calculation"
    ALIP_ELSTAT_CALCULATION = "alip_elstat_calculation"

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    NOT_SURE = "not_sure"
    FAILED = "failed"
    NOT_SUBMITTED = "not_submitted"

@dataclass
class CalculationStep:
    calculation_type: CalculationType
    required_calculations: list[CalculationType]

    status: StepStatus = StepStatus.PENDING
    folder: Path | None = None
    remote_folder: PurePosixPath | None = None

    local_files: dict[str, Path] = field(default_factory=dict)
    remote_files: dict[str, PurePosixPath] = field(default_factory=dict)

    job_id: str | None = None
    start_time: int = 0

    def to_json(self) -> dict:
        return {
            "calculation_type": self.calculation_type.value,
            "required_calculations": [calc.value for calc in self.required_calculations],
            "status": self.status.value,
            "job_id": self.job_id,
            "start_time": self.start_time,
            "folder": str(self.folder) if self.folder is not None else None,
            "remote_folder": str(self.remote_folder) if self.remote_folder is not None else None,
            "local_files": {key: str(path) for key, path in self.local_files.items()},
            "remote_files": {key: str(path) for key, path in self.remote_files.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> "CalculationStep":
        folder = data.get("folder")
        return cls(
            calculation_type=CalculationType(data["calculation_type"]),
            required_calculations=[CalculationType(calc) for calc in data.get("required_calculations", [])],
            status=StepStatus(data["status"]),
            job_id=data.get("job_id"),
            start_time=data.get("start_time", 0),
            folder=Path(folder) if folder is not None else None,
            remote_folder=PurePosixPath(data["remote_folder"]) if data.get("remote_folder") is not None else None,
            local_files={key: Path(path) for key, path in data.get("local_files", {}).items()},
            remote_files={key: PurePosixPath(path) for key, path in data.get("remote_files", {}).items()},
        )
    
@dataclass
class WorkflowCase:
    name: str
    directory: Path
    input_file: Path
    charge: int
    multiplicity: int

    last_geometry: Geometry | None = None
    repository: Repository | None = None
    steps: list[CalculationStep] = field(default_factory=list)
    current_step_index: int = 0
    terminated: bool = False

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "directory": str(self.directory),
            "input_file": str(self.input_file),
            "charge": self.charge,
            "multiplicity": self.multiplicity,
            "last_geometry": self.last_geometry.to_json() if self.last_geometry is not None else None,
            "steps": [step.to_json() for step in self.steps],
            "current_step_index": self.current_step_index,
            "terminated": self.terminated,
        }

    @classmethod
    def from_json(cls, data: dict) -> "WorkflowCase":
        return cls(
            name=data["name"],
            directory=Path(data["directory"]),
            input_file=Path(data["input_file"]),
            charge=int(data["charge"]),
            multiplicity=int(data["multiplicity"]),
            steps=[CalculationStep.from_json(step_data) for step_data in data.get("steps", [])],
            current_step_index=data.get("current_step_index", 0),
            terminated=data.get("terminated", False),
            last_geometry = Geometry.from_json(data.get("last_geometry")) if data.get("last_geometry") is not None else None,
        )
    
    def get_current_step(self) -> CalculationStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        raise IndexError("Current step index is out of range.")
    
    """def get_previous_step(self) -> CalculationStep | None:
        if self.current_step_index > 0:
            return self.steps[self.current_step_index - 1]
        return None"""
    
    def get_next_step(self) -> CalculationStep | None:
        if self.current_step_index < len(self.steps) - 1:
            return self.steps[self.current_step_index + 1]
        return None
    
    """def get_dz_opt_step(self) -> CalculationStep | None:
        for step in self.steps:
            if step.calculation_type == CalculationType.DZ_OPT:
                return step
        return None"""
    
    def get_step(self, calculation_type: CalculationType) -> CalculationStep | None:
        for step in self.steps:
            if step.calculation_type == calculation_type:
                return step
        return None
    
    def advance(self):
        if self.terminated:
            return
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
        else:
            self.terminated = True

    def get_repository(self) -> Repository | None:
        return self.repository

@dataclass
class Repository:
    cases: list[WorkflowCase] = field(default_factory=list)

    def add_case(self, case: WorkflowCase):
        if self.get_case_by_name(case.name) is not None:
            return
        self.cases.append(case)
        case.repository = self

    def get_case_by_name(self, name: str) -> WorkflowCase | None:
        for case in self.cases:
            if case.name == name:
                return case
        return None

    def add_from_json(self, data: dict):
        self.add_case(WorkflowCase.from_json(data))

    def save_to_folder(self, folder_path: Path):

        if not folder_path.exists():
            raise RuntimeError(f"Folder {folder_path} does not exist. Cannot save repository.")

        for case in self.cases:
            case_file_tmp = Path(folder_path, case.name).with_suffix(".json.tmp")
            case_file = Path(folder_path, case.name).with_suffix(".json")
            with open(case_file_tmp, "w", encoding="utf-8") as f:
                json.dump(case.to_json(), f, indent=4)
            case_file_tmp.replace(case_file)

    def load_from_folder(self, folder_path: Path):
        if not folder_path.exists():
            raise RuntimeError(f"Folder {folder_path} does not exist. Cannot load repository.")
        for case_file in folder_path.glob("*.json"):
            with open(case_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.add_from_json(data)

    def get_number_of_cases_by_step_status(self, calculation_type: CalculationType, status: StepStatus) -> int:
        count = 0
        for case in self.cases:
            step = case.get_step(calculation_type)
            if step is not None and step.status == status:
                count += 1
        return count

