from pathlib import Path
import shutil
import time
from tqdm import tqdm
from copy import deepcopy

from .ir import WorkflowCase, CalculationStep, StepStatus, CalculationType, Repository
from .config import AIM_CLUSTER, AIM_REMOTE_DIR, ALIP_ELSTAT_REMOTE_DIR, REPOSITORY_DIR, RUNS_DIR, INPUT_FOLDER, SCHEDULER, LOOP_SLEEP_TIME, ALIP_ELSTAT_CLUSTER, STOP_FILE
from .utils import get_charge_and_mult_from_com
from .calculations_steps import CALCULATION_TYPE_TO_CHECK_STEP, CALCULATION_TYPE_TO_PREPARE_STEP, CALCULATION_TYPE_TO_RUN_STEP
from .scheduler import Scheduler
from .interaction import Logger, Interaction, InteractionRequired, NoInteraction

DEFAULT_WORKFLOW_STEPS: list[CalculationStep] = [
    CalculationStep(CalculationType.LANL_OPT, required_calculations=[]),
    CalculationStep(CalculationType.DZ_OPT, required_calculations=[CalculationType.LANL_OPT]),
    CalculationStep(CalculationType.AIM_ANALYSIS, required_calculations=[CalculationType.DZ_OPT]),
    CalculationStep(CalculationType.LIGAND_ENERGIES_CALCULATION, required_calculations=[CalculationType.DZ_OPT]),
    CalculationStep(CalculationType.ALIP_ELSTAT_CALCULATION, required_calculations=[CalculationType.DZ_OPT]),
]

def add_to_repository_from_input_folder(repo: Repository, input_folder: Path, logger: Logger, interaction: Interaction):
    for input_file in input_folder.glob("*.xyz"):
        if repo.get_case_by_name(input_file.stem) is not None:
            continue

        try:
            charge, mult = interaction.request_xyz_metadata(input_file)
        except InteractionRequired:
            logger.log(f"Charge and multiplicity input is required for {input_file} but no interaction method is available. Skipping for now.")
            continue
            
        directory = Path(RUNS_DIR, input_file.stem)
        directory.mkdir(parents=True, exist_ok=True)

        repo.add_case(WorkflowCase(
            name=input_file.stem,
            directory=directory,
            input_file=Path(input_file),
            charge=charge,
            multiplicity=mult,
            steps = deepcopy(DEFAULT_WORKFLOW_STEPS)
        ))

    for input_file in input_folder.glob("*.com"):
        if repo.get_case_by_name(input_file.stem) is not None:
            continue

        charge, mult = get_charge_and_mult_from_com(input_file)

        directory = Path(RUNS_DIR, input_file.stem)
        directory.mkdir(parents=True, exist_ok=True)

        repo.add_case(WorkflowCase(
            name=input_file.stem,
            directory=directory,
            input_file=Path(input_file),
            charge=charge,
            multiplicity=mult,
            steps = deepcopy(DEFAULT_WORKFLOW_STEPS)
        ))

def process_case(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):
    current_step = case.get_current_step()

    if current_step.status == StepStatus.NOT_SURE:
        if isinstance(interaction, NoInteraction):
            return
        
        logger.log(f"Current step {current_step.calculation_type.value} for case {case.name} is in not sure status. Please check the logs and fix the issue before re-running.")

        if interaction.confirm("Did the calculation finish successfully after checking the logs and fixing the issue?", False):
            current_step.status = StepStatus.COMPLETED
            process_case(case, scheduler, logger, interaction)
        else:
            current_step.status = StepStatus.FAILED
            return

    if current_step.status == StepStatus.RUNNING:
        check_step(case, scheduler, logger)

    if current_step.status == StepStatus.NOT_SUBMITTED:
        run_step(case, scheduler, logger, interaction)

    if current_step.status == StepStatus.PENDING:
        prepare_step(case, scheduler, logger, interaction)
        if current_step.status == StepStatus.NOT_SUBMITTED:
            run_step(case, scheduler, logger, interaction)

    if current_step.status == StepStatus.COMPLETED and not case.terminated:
        case.advance()
        process_case(case, scheduler, logger, interaction)

    if current_step.status == StepStatus.FAILED:
        logger.log(f"Calculation {current_step.calculation_type.value} for case {case.name} failed. Please check the logs and fix the issue before re-running.")

        if interaction.confirm("Do you want to retry the failed calculation after fixing the issue?", False):
            current_step.status = StepStatus.PENDING
            process_case(case, scheduler, logger, interaction)

def prepare_step(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):
    
    current_step = case.get_current_step()
    
    prepare_function = CALCULATION_TYPE_TO_PREPARE_STEP.get(current_step.calculation_type)
    if prepare_function is None:
        raise NotImplementedError(f"Unknown prepare step type: {current_step.calculation_type}")
    
    prepare_function(case, scheduler, logger, interaction)

def run_step(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):
    
    current_step = case.get_current_step()

    if current_step.status != StepStatus.NOT_SUBMITTED:
        return
    
    if not interaction.confirm(f"Do you want to run {current_step.calculation_type.value} for case {case.name}?", True):
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

def run(logger: Logger, interaction: Interaction, loop: bool = False, loop_delay: int = LOOP_SLEEP_TIME):
    continue_loop = True

    while continue_loop:
        INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        REPOSITORY_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)

        repo = Repository()
        scheduler = Scheduler(SCHEDULER)

        repo.load_from_folder(REPOSITORY_DIR)
        add_to_repository_from_input_folder(repo, INPUT_FOLDER, logger, interaction)

        for case in repo.cases:
            process_case(case, scheduler, logger, interaction)

        repo.save_to_folder(REPOSITORY_DIR)

        if not loop:
            continue_loop = False
            logger.log("All cases processed for now, run the workflow later to check for running jobs and to process next steps.")
        else:
            logger.log(f"All cases processed, waiting for {loop_delay} seconds before checking again for new cases and running jobs...")
            for _ in range(loop_delay):
                time.sleep(1)
                if STOP_FILE.exists():
                    logger.log("Command --stop called, stopping the loop now.")
                    continue_loop = False
                    break

    if STOP_FILE.exists():
        STOP_FILE.unlink()

def show_status(logger: Logger):
    if not REPOSITORY_DIR.exists():
        logger.log("No repository found. Please run the workflow first to create the repository.")
        return

    repo = Repository()
    repo.load_from_folder(REPOSITORY_DIR)

    for case in repo.cases:
        message = f"Case: {case.name:20s} is finished: {case.terminated}"
        if not case.terminated:
            current_step = case.get_current_step()
            message += f" | Current step: {current_step.calculation_type.value:20s} - {current_step.status.value:10s}"
        logger.log(message)

def restore(logger: Logger, interaction: Interaction):
    logger.log("Running restore...")

    scheduler = Scheduler(SCHEDULER)

    if REPOSITORY_DIR.exists():
        repo = Repository()
        repo.load_from_folder(REPOSITORY_DIR)
        if interaction.confirm(f"Repository found with {len(repo.cases)} cases. Do you want to cancel all running jobs?", False):
            for case in repo.cases:
                if case.get_current_step().job_id:
                    logger.log(f"Cancelling job {case.get_current_step().job_id} for case {case.name}...")
                    scheduler.cancel_job(case.get_current_step().job_id)
                    case.get_current_step().status = StepStatus.PENDING

        if interaction.confirm(f"Do you want to reset the repository folder '{REPOSITORY_DIR}' by removing all cases and their data?", False):
            logger.log(f"Removing repository folder '{REPOSITORY_DIR}'...")
            shutil.rmtree(REPOSITORY_DIR, ignore_errors=True)
    
    if RUNS_DIR.exists():
        if interaction.confirm(f"Do you want to remove the run folder '{RUNS_DIR}' as well?", False):
            logger.log(f"Removing run folder '{RUNS_DIR}'...")
            shutil.rmtree(RUNS_DIR, ignore_errors=True)

    if interaction.confirm(f"The following script will be used 'rm -rf {AIM_REMOTE_DIR}/*'.\nDo you want to clear the AIM cluster folder as well?", False):
        logger.log(f"Clearing AIM cluster folder '{AIM_REMOTE_DIR}'...")
        scheduler.run_remote_command(AIM_CLUSTER, f"rm -rf {AIM_REMOTE_DIR}/*"  )

    if interaction.confirm(f"The following script will be used 'rm -rf {ALIP_ELSTAT_REMOTE_DIR}/*'.\nDo you want to clear the ALIP ELSTAT cluster folder as well?", False):
        logger.log(f"Clearing ALIP ELSTAT cluster folder '{ALIP_ELSTAT_REMOTE_DIR}'...")
        scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"rm -rf {ALIP_ELSTAT_REMOTE_DIR}/*"  )
        
def stop_loop():
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.touch()