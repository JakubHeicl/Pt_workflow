from pathlib import Path
import time
import shutil

from .ir import StepStatus, WorkflowCase, CalculationType
from .parser import TerminationStatus, get_last_geometry, get_log_termination_status
from .scheduler import Scheduler, UnsificientResourcesException, RemoteExecutionException, SubmissionFailedException
from .utils import xyz_to_lanl, com_to_lanl, make_dz_file
from .config import AIM_CLUSTER, AIM_FOLDER, LANL_EXTENSION, DZ_EXTENSION, NUMBER_OF_CORES_AIM, MAX_RUNNING_AIM     
from .scripts import aim_analysis_script
from .logger import Logger

def prepare_lanl_optimization(case: WorkflowCase, scheduler: Scheduler):

    current_step = case.get_current_step()
    folder = current_step.folder
    input_file = case.input_file

    if current_step.calculation_type != CalculationType.LANL_OPT:
        raise ValueError(f"Expected LANL OPTIMIZATION step, got {current_step.calculation_type}.")
    
    name = f"{case.name}_{LANL_EXTENSION}"

    folder.mkdir(parents=True, exist_ok=True)
    lanl_input_file = Path(folder, name).with_suffix(".com")
    lanl_chk_file = Path(folder, name).with_suffix(".chk")
    lanl_output_file = Path(folder, name).with_suffix(".log")

    if input_file.suffix == ".xyz":
        xyz_to_lanl(input_file, lanl_input_file, lanl_chk_file, case.charge, case.multiplicity)
    elif input_file.suffix == ".com":
        com_to_lanl(input_file, lanl_input_file, lanl_chk_file)
    else:
        raise ValueError(f"Unsupported input file format: {input_file.suffix}")
    
    current_step.input_file = lanl_input_file
    current_step.chk_file = lanl_chk_file
    current_step.log_file = lanl_output_file

    current_step.status = StepStatus.NOT_SUBMITED

def run_lanl_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    folder = current_step.folder
    lanl_input_file = current_step.input_file
    lanl_chk_file = current_step.chk_file

    try:
        job_id = scheduler.submit_job(folder, lanl_input_file, lanl_chk_file)
    except UnsificientResourcesException:
        logger.log(f"Insufficient resources to run LANL optimization for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    except SubmissionFailedException:
        logger.log(f"Failed to submit LANL optimization job for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return

    current_step.job_id = job_id
    
    current_step.status = StepStatus.RUNNING
    logger.log(f"Submitted LANL optimization for case {case.name} with job ID {job_id}.")

def prepare_dz_optimization(case: WorkflowCase, scheduler: Scheduler):

    current_step = case.get_current_step()
    folder = current_step.folder
    previous_step = case.get_previous_step()

    if current_step.calculation_type != CalculationType.DZ_OPT:
        raise ValueError(f"Expected DZ OPTIMIZATION step, got {current_step.calculation_type}.")
    
    if previous_step.calculation_type != CalculationType.LANL_OPT:
        raise ValueError(f"Expected previous step to be LANL OPTIMIZATION, got {previous_step.calculation_type}.")
    
    last_geometry = case.last_geometry
    if last_geometry is None:
        raise ValueError(f"No geometry found for case {case.name}. Cannot run DZ optimization.")
    
    name = f"{case.name}_{DZ_EXTENSION}"
    
    folder.mkdir(parents=True, exist_ok=True)
    dz_input_file = Path(folder, name).with_suffix(".com")
    dz_chk_file = Path(folder, name).with_suffix(".chk")
    dz_output_file = Path(folder, name).with_suffix(".log")

    make_dz_file(dz_input_file, dz_chk_file, last_geometry.geometry_lines, last_geometry.atoms_symbols, case.charge, case.multiplicity)

    current_step.input_file = dz_input_file
    current_step.chk_file = dz_chk_file
    current_step.log_file = dz_output_file

    current_step.status = StepStatus.NOT_SUBMITED

def run_dz_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    folder = current_step.folder
    dz_input_file = current_step.input_file
    dz_chk_file = current_step.chk_file

    try:
        job_id = scheduler.submit_job(folder, dz_input_file, dz_chk_file)
    except UnsificientResourcesException:
        logger.log(f"Insufficient resources to run DZ optimization for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    except SubmissionFailedException:
        logger.log(f"Failed to submit DZ optimization job for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    
    current_step.job_id = job_id
    
    current_step.status = StepStatus.RUNNING
    logger.log(f"Submitted DZ optimization for case {case.name} with job ID {job_id}.")
    
def prepare_aim_analysis(case: WorkflowCase, scheduler: Scheduler):

    if case.get_repository().metadata.get("running_aim") is None:
        case.get_repository().metadata["running_aim"] = 0

    current_step = case.get_current_step()
    previous_step = case.get_previous_step()

    if current_step.calculation_type != CalculationType.AIM_ANALYSIS:
        raise ValueError(f"Expected AIM ANALYSIS step, got {current_step.calculation_type}.")
    
    if previous_step.calculation_type != CalculationType.DZ_OPT:
        raise ValueError(f"Expected previous step to be DZ OPTIMIZATION, got {previous_step.calculation_type}.")
    
    formchk_file = previous_step.fchk_file

    folder = current_step.folder
    folder.mkdir(parents=True, exist_ok=True)
    current_step.remote_folder = Path(AIM_FOLDER, case.name)
    remote_folder = current_step.remote_folder
    current_step.remote_fchk_file = Path(remote_folder, formchk_file.name)
    shutil.copy(formchk_file, folder)
    current_step.fchk_file = Path(folder, formchk_file.name)

    current_step.status = StepStatus.NOT_SUBMITED

def run_aim_analysis(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()

    if case.get_repository().metadata.get("running_aim", 0) >= MAX_RUNNING_AIM:
        logger.log(f"Maximum number of running AIM analyses reached. Cannot run AIM analysis for case {case.name} now. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return

    remote_folder = current_step.remote_folder
    formchk_file = current_step.fchk_file
    
    try:

        aim_script = aim_analysis_script.substitute(folder=remote_folder, fchk_file=current_step.remote_fchk_file.name, num_cpus=NUMBER_OF_CORES_AIM)

        logger.log(f"Running command on {AIM_CLUSTER}: mkdir -p {remote_folder}")
        scheduler.run_remote_command(AIM_CLUSTER, f"mkdir -p {remote_folder}")
        logger.log(f"Transferring file {formchk_file} to {AIM_CLUSTER}:{remote_folder}")
        scheduler.transfer_file_to_remote(formchk_file, AIM_CLUSTER, str(remote_folder))
        logger.log(f"Running command on {AIM_CLUSTER}: {aim_script}")
        scheduler.run_remote_command(AIM_CLUSTER, aim_script)
    except RemoteExecutionException as e:
        logger.log(f"Failed to run AIM analysis for case {case.name} on cluster {AIM_CLUSTER}: {e} Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    
    current_step.status = StepStatus.RUNNING
    case.get_repository().metadata["running_aim"] = case.get_repository().metadata.get("running_aim", 0) + 1
    logger.log(f"Submitted AIM analysis for case {case.name} on cluster {AIM_CLUSTER}.")

def check_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    job_id = current_step.job_id

    if not job_id:
        logger.log(f"No job ID found for {current_step.calculation_type.value} of case {case.name}. Marking as failed.")
        current_step.status = StepStatus.FAILED
        return

    if scheduler.is_job_running(job_id):
        return
    
    formchk_file = current_step.input_file.with_suffix(".fchk")

    if not formchk_file.exists():
        logger.log(f"Formchk file {formchk_file} for {current_step.calculation_type.value} of case {case.name} might still not be ready. Waiting...")
        time.sleep(5)
        if not formchk_file.exists():
            logger.log(f"Formchk file {formchk_file} for {current_step.calculation_type.value} of case {case.name} is still not available after waiting. Marking as failed.")
            current_step.status = StepStatus.FAILED
            return

    while formchk_file.stat().st_mtime + 15 > time.time():
        logger.log(f"Formchk file {formchk_file} for {current_step.calculation_type.value} of case {case.name} might still not be ready. Waiting...")
        time.sleep(2)

    current_step.fchk_file = formchk_file

    try:
        termination_status = get_log_termination_status(case)
        if termination_status == TerminationStatus.SUCCESS:
            current_step.status = StepStatus.COMPLETED
            case.last_geometry = get_last_geometry(current_step.log_file)
            slurm_output = Path(current_step.folder, f"slurm-{job_id}.out")
            slurm_output.unlink(missing_ok=True)
            fort_file = Path(current_step.folder, "fort.7")
            fort_file.unlink(missing_ok=True)
            logger.log(f"{current_step.calculation_type.value} for case {case.name} completed successfully.")
        else:
            current_step.status = StepStatus.FAILED
            logger.log(f"{current_step.calculation_type.value} for case {case.name} failed. Please check the logs for details.")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        logger.log(f"Error while checking termination status for {current_step.calculation_type.value} of case {case.name}: {e}")

def check_aim_analysis(case: WorkflowCase, scheduler: Scheduler, logger: Logger):
    pass

CALCULATION_TYPE_TO_PREPARE_STEP = {
    CalculationType.LANL_OPT: prepare_lanl_optimization,
    CalculationType.DZ_OPT: prepare_dz_optimization,
    CalculationType.AIM_ANALYSIS: prepare_aim_analysis,
}

CALCULATION_TYPE_TO_RUN_STEP = {
    CalculationType.LANL_OPT: run_lanl_optimization,
    CalculationType.DZ_OPT: run_dz_optimization,
    CalculationType.AIM_ANALYSIS: run_aim_analysis,
}  

CALCULATION_TYPE_TO_CHECK_STEP = {
    CalculationType.LANL_OPT: check_optimization,
    CalculationType.DZ_OPT: check_optimization,
    CalculationType.AIM_ANALYSIS: check_aim_analysis,
}
    

    

    