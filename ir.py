from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class CalculationType(Enum):
    LANL_OPT = "LANL optimization"
    DZ_OPT = "DZ optimization   "
    AIM_ANALYSIS = "AIM analysis"
    LIGAND_ENERGIES_CALCULATION = "Ligand energies calculation"
    ALIP_CALCULATION = "ALIP calculation"
    ELSTAT_CALCULATION = "Electrostatic potential calculation"

class Status(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CalculationStep:
    calculation_type: CalculationType
    status: Status
    folder: Path
    job_id: str | None = None

    def to_json(self) -> dict:
        return {
            "calculation_type": self.calculation_type.value,
            "status": self.status.value,
            "job_id": self.job_id,
            "folder": str(self.folder) if self.folder is not None else None,
        }

    @classmethod
    def from_json(cls, data: dict) -> "CalculationStep":
        folder = data.get("folder")
        return cls(
            calculation_type=CalculationType(data["calculation_type"]),
            status=Status(data["status"]),
            job_id=data.get("job_id"),
            folder=Path(folder) if folder is not None else None,
        )


@dataclass
class WorkflowCase:
    name: str
    directory: Path
    input_file: Path
    charge: int
    multiplicity: int
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
        )
    
    def get_current_step(self) -> CalculationStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        raise IndexError("Current step index is out of range.")
    
    def advance(self):
        if self.terminated:
            return
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
        else:
            self.terminated = True
