from pathlib import Path
import shutil
import time
from tqdm import tqdm

from .ir import WorkflowCase, CalculationStep, StepStatus, CalculationType, Repository
from .config import AIM_CLUSTER, AIM_FOLDER, ALIP_ELSTAT_FOLDER, REPOSITORY_FOLDER, RUN_FOLDER, INPUT_FOLDER, SCHEDULER, LOOP_SLEEP_TIME, ALIP_ELSTAT_CLUSTER
from .utils import get_charge_and_mult_from_com
from .calculations_steps import CALCULATION_TYPE_TO_CHECK_STEP, CALCULATION_TYPE_TO_PREPARE_STEP, CALCULATION_TYPE_TO_RUN_STEP
from .scheduler import Scheduler
from .logger import Logger


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
                                   status = StepStatus.PENDING) for calc_type in CalculationType]
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
                                   status = StepStatus.PENDING) for calc_type in CalculationType]
        ))

def proccess_case(case: WorkflowCase, scheduler: Scheduler, logger: Logger):
    current_step = case.get_current_step()

    if current_step.status == StepStatus.NOT_SURE:
        logger.log(f"Current step {current_step.calculation_type.value} for case {case.name} is in not sure status. Please check the logs and fix the issue before re-running.")

        if not logger.verbose:
            logger.log("Verbose mode is off, try toggle it on to be able to retry the calculation after fixing the issue.")
            return

        if logger.reassure("Did the calculation finish successfully after checking the logs and fixing the issue?"):
            current_step.status = StepStatus.COMPLETED
            proccess_case(case, scheduler, logger)
        else:
            current_step.status = StepStatus.FAILED
            return

    if current_step.status == StepStatus.RUNNING:
        check_step(case, scheduler, logger)

    if current_step.status == StepStatus.NOT_SUBMITED:
        run_step(case, scheduler, logger)

    if current_step.status == StepStatus.PENDING:
        prepare_step(case, scheduler, logger)
        run_step(case, scheduler, logger)

    if current_step.status == StepStatus.COMPLETED and not case.terminated:
        case.advance()
        proccess_case(case, scheduler, logger)

    if current_step.status == StepStatus.FAILED:
        logger.log(f"Calculation {current_step.calculation_type.value} for case {case.name} failed. Please check the logs and fix the issue before re-running.")

        if not logger.verbose:
            logger.log("Verbose mode is off, try toggle it on to be able to retry the calculation after fixing the issue.")
            return

        if logger.reassure("Do you want to retry the failed calculation after fixing the issue?"):
            current_step.status = StepStatus.PENDING
            proccess_case(case, scheduler, logger)

def prepare_step(case: WorkflowCase, scheduler: Scheduler, logger: Logger):
    
    current_step = case.get_current_step()
    
    prepare_function = CALCULATION_TYPE_TO_PREPARE_STEP.get(current_step.calculation_type)
    if prepare_function is None:
        raise NotImplementedError(f"Unknown prepare step type: {current_step.calculation_type}")
    
    prepare_function(case, scheduler, logger)

def run_step(case: WorkflowCase, scheduler: Scheduler, logger: Logger):
    
    current_step = case.get_current_step()
    
    if not logger.reassure(f"Do you want to run {current_step.calculation_type.value} for case {case.name}?"):
        return
    
    run_function = CALCULATION_TYPE_TO_RUN_STEP.get(current_step.calculation_type)
    if run_function is None:
        raise NotImplementedError(f"Unknown run step type: {current_step.calculation_type}")
    
    run_function(case, scheduler, logger)
        
def check_step(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    
    check_function = CALCULATION_TYPE_TO_CHECK_STEP.get(current_step.calculation_type)
    if check_function is None:
        raise NotImplementedError(f"Unknown check step type: {current_step.calculation_type}")
    
    check_function(case, scheduler, logger)

def run(verbose: bool = True, log_file: Path | None = None, loop: bool = False, loop_delay: int = LOOP_SLEEP_TIME):
    logger = Logger(verbose=verbose, log_file=log_file)
    continue_loop = True

    while continue_loop:
        INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        REPOSITORY_FOLDER.mkdir(parents=True, exist_ok=True)
        RUN_FOLDER.mkdir(parents=True, exist_ok=True)

        repo = Repository()
        scheduler = Scheduler(SCHEDULER)

        repo.load_from_folder(REPOSITORY_FOLDER)
        add_to_repository_from_input_folder(repo, INPUT_FOLDER)

        for case in repo.cases:
            proccess_case(case, scheduler, logger)

        repo.save_to_folder(REPOSITORY_FOLDER)

        if not loop:
            continue_loop = False
            logger.log("All cases processed for now, run the workflow later to check for running jobs and to process next steps.")
        else:
            logger.log(f"All cases processed, waiting for {loop_delay} seconds before checking again for new cases and running jobs...")
            for _ in tqdm(range(loop_delay), desc="Waiting", unit="s"):
                time.sleep(1)

def show_status(verbose: bool = True, log_file: Path | None = None):
    logger = Logger(verbose=verbose, log_file=log_file)

    if not REPOSITORY_FOLDER.exists():
        logger.log("No repository found. Please run the workflow first to create the repository.")
        return

    repo = Repository()
    repo.load_from_folder(REPOSITORY_FOLDER)

    for case in repo.cases:
        message = f"Case: {case.name:20s} is finished: {case.terminated}"
        if not case.terminated:
            current_step = case.get_current_step()
            message += f" | Current step: {current_step.calculation_type.value:20s} - {current_step.status.value:10s}"
        logger.log(message)

def restore(verbose: bool = True, log_file: Path | None = None):
    logger = Logger(verbose=verbose, log_file=log_file)
    logger.log("Running restore...")

    scheduler = Scheduler(SCHEDULER)

    if REPOSITORY_FOLDER.exists():
        repo = Repository()
        repo.load_from_folder(REPOSITORY_FOLDER)

        for case in repo.cases:
            if case.get_current_step().job_id:
                logger.log(f"Cancelling job {case.get_current_step().job_id} for case {case.name}...")
                scheduler.cancel_job(case.get_current_step().job_id)

        logger.log(f"Removing repository folder '{REPOSITORY_FOLDER}'...")
        shutil.rmtree(REPOSITORY_FOLDER, ignore_errors=True)
    
    if RUN_FOLDER.exists():
        logger.log(f"Removing run folder '{RUN_FOLDER}'...")
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)

    if logger.reassure(f"The following script will be used 'rm -rf {AIM_FOLDER}/*'. Do you want to clear the AIM cluster folder as well?"):
        logger.log(f"Clearing AIM cluster folder '{AIM_FOLDER}'...")
        scheduler.run_remote_command(AIM_CLUSTER, f"rm -rf {AIM_FOLDER}/*"  )

    if logger.reassure(f"The following script will be used 'rm -rf {ALIP_ELSTAT_FOLDER}/*'. Do you want to clear the ALIP ELSTAT cluster folder as well?"):
        logger.log(f"Clearing ALIP ELSTAT cluster folder '{ALIP_ELSTAT_FOLDER}'...")
        scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"rm -rf {ALIP_ELSTAT_FOLDER}/*"  )
        
