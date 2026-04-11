from enum import Enum
from pathlib import Path

from .ir import WorkflowCase, Geometry, Atom

class TerminationStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"

def get_log_termination_status(case: WorkflowCase) -> TerminationStatus:
    
    current_step = case.get_current_step()

    log_file = current_step.log_file

    if log_file is None or not log_file.exists():
        raise RuntimeError(f"Log file for case {case.name} does not exist. Cannot determine termination status.")
    
    with open(log_file, "r") as f:
        lines = f.readlines()
        if not lines:
            raise RuntimeError(f"Log file for case {case.name} is empty. Cannot determine termination status.")
        
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            if "Normal termination" in line:
                return TerminationStatus.SUCCESS
            elif "Error termination" in line:
                return TerminationStatus.FAILURE
    raise RuntimeError(f"Could not determine termination status for case {case.name}. Please check the log file for details.")

def get_last_geometry(log_file: Path) -> Geometry:
    if not log_file.exists():
        raise RuntimeError(f"Log file {log_file} does not exist. Cannot extract geometry.")
    
    with open(log_file, "r") as f:

        lines = f.readlines()

        index = None

        stationary_point_found = False

        for i, line in enumerate(lines):
            if "Stationary point found" in line:
                stationary_point_found = True
            
            if "Standard orientation:" in line and stationary_point_found:
                index = i

        if index is None:
            raise RuntimeError(f"Could not find geometry in log file {log_file}. Please check the log file for details.")
        
        inside_geometry_block = False

        atoms: list[Atom] = []

        for line in lines[index:]:
            if "------" in line and inside_geometry_block:
                break

            parts = line.strip().split() if line.strip() else ["NONE"]

            if parts[0].isdigit():
                inside_geometry_block = True
                atoms.append(Atom(
                    atomic_number = int(parts[1]),
                    x = float(parts[3]),
                    y = float(parts[4]),
                    z = float(parts[5]),
                ))

        if not atoms:
            raise RuntimeError(f"Could not extract geometry from log file {log_file}. Please check the log file for details.")
        return Geometry(atoms=atoms)


            