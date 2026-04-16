from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

class Logger:
    def __init__(self, log_file: Path | None = None):
        self.log_file = log_file

    def log(self, message: str, print_to_console: bool = True):
        if print_to_console:
            print(message)

        if self.log_file is not None:
            with open(self.log_file, "a") as f:
                f.write(message + "\n")

@dataclass
class LigandReviewRequest:
    case_name: str                      # Case name
    atom_labels: list[str]              # All atoms
    pt_neighbors_labels: list[str]      # Atoms around Pt
    total_charge: int                   # Total charge of the system
    suggested_ligands: list[list[int]] = field(default_factory=list)  # Indexes of atoms

@dataclass
class LigandReviewResponse:
    ligands: list[list[int]]
    ligand_charges: list[int]

class InteractionRequired(RuntimeError):
    pass

class Interaction(Protocol):
    interactive: bool
    logger: Logger

    def confirm(self, prompt: str, default: bool = True) -> bool: ...
    def request_xyz_metadata(self, input_file: Path) -> tuple[int, int]: ...
    def review_ligands(self, request: LigandReviewRequest) -> LigandReviewResponse: ...
    def request_manual_ligands(self, request: LigandReviewRequest) -> LigandReviewResponse: ...

def atoms_labels_for_indices(indexes: list[int], all_atoms: list[str]) -> list[str]:  
        atoms = []

        for index in indexes:
            atoms.append(all_atoms[index])

        return atoms

class ConsoleInteraction:

    interactive = True

    def __init__(self, logger: Logger):
        self.logger = logger

    def _ask_int(self, prompt: str) -> int:
        while True:
            response = input(prompt).strip()
            self.logger.log(f"Prompt: {prompt}", print_to_console=False)
            self.logger.log(f"User input: {response}", print_to_console=False)

            try:
                return int(response)
            except ValueError:
                self.logger.log("Invalid input. Please enter an integer.")

    def _ask_ligand(self, pt_neighbor: str, max_atoms: int, case_name: str) -> list[int]:

        continue_loop = True
        while continue_loop:
            ligand = []
            message = f"Write the indices of atoms to the ligand {pt_neighbor} of case {case_name}:\n"
            self.logger.log(message, print_to_console=False)
            response = input(message)
            self.logger.log(f"User input: {response}", print_to_console=False)
            try:
                for index in response.strip().split():
                    ligand.append(int(index))
                continue_loop = False
            except ValueError:
                self.logger.log("Invalid input. Please enter integers only.")
                continue
            if any(index < 0 or index >= max_atoms for index in ligand):
                self.logger.log(f"Invalid input. Indices must be between 0 and {max_atoms - 1}.")
                continue
        return ligand

    def confirm(self, prompt: str, default: bool = True) -> bool:
        while True:
            message = f"{prompt} (y/n) [default: {'y' if default else 'n'}]: "
            self.logger.log(message, print_to_console=False)
            response = input(message).strip().lower()
            self.logger.log(f"User input: {response}", print_to_console=False)
            if not response:
                return default
            if response in ['y', 'yes']:
                return True
            if response in ['n', 'no']:
                return False
            
            self.logger.log("Invalid answer. Please enter y or n.")
            
    def request_xyz_metadata(self, input_file: Path) -> tuple[int, int]:
        charge = self._ask_int(f"Enter charge for {input_file.name}: ")
        multiplicity = self._ask_int(f"Enter multiplicity for {input_file.name}: ")
        return charge, multiplicity
    
    def _ask_ligand_indices(self, request: LigandReviewRequest) -> list[list[int]]:
        not_correct = True
        while not_correct:

            new_ligands = []

            for pt_neighbor in request.pt_neighbors_labels:
                
                ligand = self._ask_ligand(pt_neighbor, len(request.atom_labels), request.case_name)
                
                new_ligands.append(ligand)

            if sum([len(ligand) for ligand in new_ligands]) != len(request.atom_labels) - 1:
                self.logger.log("Ligands must include all atoms except the Pt center. Please review your ligands.")
                continue

            for i, _ in enumerate(new_ligands): self.logger.log(f"Ligand for {request.pt_neighbors_labels[i]}:\n{atoms_labels_for_indices(new_ligands[i], request.atom_labels)}\n")
            not_correct = not self.confirm("Do you want to keep these ligands?", default=True)
        return new_ligands

    def _ask_ligand_charges(self, request: LigandReviewRequest) -> list[int]:
        not_correct = True
        while not_correct:

            ligand_charges = []

            message = f"Write formal charges to each ligand (space-separated). The total charge is {request.total_charge}\n"
            self.logger.log(message, print_to_console = False)
            response = input(message)
            self.logger.log(f"User input: {response}", print_to_console=False)
            try:
                ligand_charges = [int(x) for x in response.strip().split()]
            except ValueError:
                self.logger.log("Invalid input. Please enter integer values separated by spaces.")
                continue
            if len(ligand_charges) != len(request.pt_neighbors_labels):
                self.logger.log(f"You must enter exactly {len(request.pt_neighbors_labels)} charges, one for each ligand. Please try again.")
                continue
            if (sum(ligand_charges)+4) != request.total_charge:
                self.logger.log(f"Warning: The total charge of the ligands ({sum(ligand_charges)}) does not match the expected total charge ({request.total_charge}). Please double-check the charges you entered.")
            else:
                not_correct = False
        return ligand_charges

    def request_manual_ligands(self, request: LigandReviewRequest) -> LigandReviewResponse:

        self.logger.log(f"Manually submitting ligands for case {request.case_name}.")
        
        ligands = self._ask_ligand_indices(request)
        ligand_charges = self._ask_ligand_charges(request)

        return LigandReviewResponse(ligands=ligands, ligand_charges=ligand_charges)

    def review_ligands(self, request: LigandReviewRequest) -> LigandReviewResponse:

        for i, _ in enumerate(request.suggested_ligands): self.logger.log(f"Ligand for {request.pt_neighbors_labels[i]}:\n{atoms_labels_for_indices(request.suggested_ligands[i], request.atom_labels)}\n")

        if not self.confirm(f"Review the suggested ligands for case {request.case_name}. Do you want to keep the suggested ligands?", default=True):
            new_ligands = self._ask_ligand_indices(request)
        else:
            new_ligands = request.suggested_ligands

        ligand_charges = self._ask_ligand_charges(request)

        return LigandReviewResponse(ligands=new_ligands, ligand_charges=ligand_charges)

class NoInteraction:
    interactive = False

    def __init__(self, logger: Logger):
        self.logger = logger

    def confirm(self, prompt: str, default: bool = True) -> bool:
        self.logger.log(f"Confirmation requested: {prompt} [default: {'y' if default else 'n'}]. No interaction mode is enabled, so returning default value: {default}.")
        return default

    def request_xyz_metadata(self, input_file: Path) -> tuple[int, int]:
        raise InteractionRequired
    
    def review_ligands(self, request: LigandReviewRequest) -> LigandReviewResponse:
        raise InteractionRequired
    
    def request_manual_ligands(self, request: LigandReviewRequest) -> LigandReviewResponse:
        raise InteractionRequired
