from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from .utils import _SYMBOLS

@dataclass
class Atom:
    atomic_number: int
    x: float
    y: float
    z: float

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

@dataclass
class Geometry:
    atoms: list[Atom]

    def to_json(self) -> dict:
        return {
            "atoms": [atom.to_json() for atom in self.atoms]
        }

    @classmethod
    def from_json(cls, data: dict) -> "Geometry":
        return cls(
            atoms=[Atom.from_json(atom_data) for atom_data in data.get("atoms", [])]
        )
    
    @property
    def geometry_lines(self) -> list[str]:
        return [f"{atom.symbol}     {atom.x}  {atom.y}  {atom.z}" for atom in self.atoms]
    
    def atoms_symbols(self) -> set[str]:
        return set(atom.symbol for atom in self.atoms)

class CalculationType(Enum):
    LANL_OPT = "lanl_opt"
    DZ_OPT = "dz_opt"
    AIM_ANALYSIS = "aim_analysis"
    LIGAND_ENERGIES_CALCULATION = "ligand_energies_calculation"
    ALIP_CALCULATION = "alip_calculation"
    ELSTAT_CALCULATION = "elstat_calculation"

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class CalculationStep:
    calculation_type: CalculationType
    status: StepStatus
    folder: Path
    input_file: Path | None = None
    log_file: Path | None = None
    chk_file: Path | None = None
    job_id: str | None = None

    def to_json(self) -> dict:
        return {
            "calculation_type": self.calculation_type.value,
            "status": self.status.value,
            "job_id": self.job_id,
            "folder": str(self.folder) if self.folder is not None else None,
            "input_file": str(self.input_file) if self.input_file is not None else None,
            "log_file": str(self.log_file) if self.log_file is not None else None,
            "chk_file": str(self.chk_file) if self.chk_file is not None else None,
        }

    @classmethod
    def from_json(cls, data: dict) -> "CalculationStep":
        folder = data.get("folder")
        return cls(
            calculation_type=CalculationType(data["calculation_type"]),
            status=StepStatus(data["status"]),
            job_id=data.get("job_id"),
            folder=Path(folder) if folder is not None else None,
            input_file=Path(data["input_file"]) if data.get("input_file") is not None else None,
            log_file=Path(data["log_file"]) if data.get("log_file") is not None else None,
            chk_file=Path(data["chk_file"]) if data.get("chk_file") is not None else None,
        )


@dataclass
class WorkflowCase:
    name: str
    directory: Path
    input_file: Path
    charge: int
    multiplicity: int
    last_geometry: Geometry | None = None
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
    
    def get_previous_step(self) -> CalculationStep | None:
        if self.current_step_index > 0:
            return self.steps[self.current_step_index - 1]
        return None
    
    def get_next_step(self) -> CalculationStep | None:
        if self.current_step_index < len(self.steps) - 1:
            return self.steps[self.current_step_index + 1]
        return None
    
    def advance(self):
        if self.terminated:
            return
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
        else:
            self.terminated = True
