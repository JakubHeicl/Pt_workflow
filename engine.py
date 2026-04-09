from repository import Repository
from ir import WorkflowCase, CalculationStep, Status, CalculationType
from pathlib import Path
from config import REPOSITORY_FOLDER, RUN_FOLDER, INPUT_FOLDER, SCHEDULER
from utils import get_charge_and_mult_from_com
from calculations_steps import run_lanl_optimization
from scheduler import Scheduler 

def add_to_repository_from_input_folder(repo: Repository, input_folder: Path):
    for input_file in input_folder.glob("*.xyz"):
        if repo.get_case_by_name(input_file.stem) is not None:
            continue

        charge = int(input(f"Enter charge for {input_file.name}: "))
        mult = int(input(f"Enter multiplicity for {input_file.name}: "))

        directory = Path(RUN_FOLDER, input_file.stem)
        directory.mkdir(parents=True, exist_ok=True)

        repo.add_case(WorkflowCase(
            name=input_file.stem,
            directory=directory,
            input_file=Path(input_file),
            charge=charge,
            multiplicity=mult,
            steps=[CalculationStep(calculation_type = calc_type, 
                                   folder = Path(directory, calc_type.value), 
                                   status = Status.PENDING) for calc_type in CalculationType]
        ))

    for input_file in input_folder.glob("*.com"):
        if repo.get_case_by_name(input_file.stem) is not None:
            continue

        charge, mult = get_charge_and_mult_from_com(input_file)

        directory = Path(RUN_FOLDER, input_file.stem)
        directory.mkdir(parents=True, exist_ok=True)

        repo.add_case(WorkflowCase(
            name=input_file.stem,
            directory=directory,
            input_file=Path(input_file),
            charge=charge,
            multiplicity=mult,
            steps=[CalculationStep(calculation_type = calc_type, 
                                   folder = Path(directory, calc_type.value), 
                                   status = Status.PENDING) for calc_type in CalculationType]
        ))

def proccess_case(case: WorkflowCase, scheduler: Scheduler):
    current_step = case.get_current_step()

    if current_step.status == Status.PENDING:
        run_step(case, scheduler)

    if current_step.status == Status.RUNNING:
        check_step(case)

    if current_step.status == Status.COMPLETED:
        case.advance()
        proccess_case(case, scheduler)

    if current_step.status == Status.FAILED:
        print(f"Calculation {current_step.calculation_type.value} for case {case.name} failed. Please check the logs and fix the issue before re-running.")
        if input("Do you want to retry the failed calculation after fixing the issue? (y/n): ").lower() == "y":
            current_step.status = Status.PENDING
            proccess_case(case, scheduler)

def run_step(case: WorkflowCase, scheduler: Scheduler):
    
    current_step = case.get_current_step()
    
    if input(f"Do you want to run {current_step.calculation_type.value} for case {case.name}? (y/n): ").lower() != "y":
        return
    
    if current_step.calculation_type == CalculationType.LANL_OPT:
        run_lanl_optimization(case, scheduler)
    elif current_step.calculation_type == CalculationType.DZ_OPT:
        raise NotImplementedError("DZ optimization is not implemented yet.")
    elif current_step.calculation_type == CalculationType.AIM_ANALYSIS:
        raise NotImplementedError("AIM analysis is not implemented yet.")   
    elif current_step.calculation_type == CalculationType.LIGAND_ENERGIES_CALCULATION:
        raise NotImplementedError("Ligand energies calculation is not implemented yet.")
    elif current_step.calculation_type == CalculationType.ALIP_CALCULATION:
        raise NotImplementedError("ALIP calculation is not implemented yet.")
    elif current_step.calculation_type == CalculationType.ELSTAT_CALCULATION:
        raise NotImplementedError("Electrostatic potential calculation is not implemented yet.")
    else:
        raise ValueError(f"Unknown calculation type: {current_step.calculation_type}")
        

def check_step(case: WorkflowCase):
    pass


if __name__ == "__main__":
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    repo = Repository()
    scheduler = Scheduler(SCHEDULER)

    repo.load_from_folder(REPOSITORY_FOLDER)
    add_to_repository_from_input_folder(repo, INPUT_FOLDER)

    for case in repo.cases:
        proccess_case(case, scheduler)

    repo.save_to_folder(REPOSITORY_FOLDER)
