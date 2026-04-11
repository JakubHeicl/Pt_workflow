from pathlib import Path

from .ir import StepStatus, WorkflowCase, CalculationType
from .parser import TerminationStatus, get_last_geometry, get_log_termination_status
from .scheduler import Scheduler
from .utils import xyz_to_lanl, com_to_lanl, make_dz_file
from .config import LANL_EXTENSION, DZ_EXTENSION

def run_lanl_optimization(case: WorkflowCase, scheduler: Scheduler):
    current_step = case.get_current_step()
    folder = current_step.folder
    input_file = case.input_file

    if current_step.calculation_type != CalculationType.LANL_OPT:
        raise ValueError(f"Expected LANL OPTIMIZATION step, got {current_step.calculation_type}.")
    
    name = f"{case.name}_{LANL_EXTENSION}"

    folder.mkdir(parents=True, exist_ok=True)
    lanl_input_file = Path(folder, name).with_suffix(".com")
    lanl_output_file = Path(folder, name).with_suffix(".log")

    if input_file.suffix == ".xyz":
        xyz_to_lanl(input_file, lanl_input_file, case.charge, case.multiplicity)
    elif input_file.suffix == ".com":
        com_to_lanl(input_file, lanl_input_file)
    else:
        raise ValueError(f"Unsupported input file format: {input_file.suffix}")
    
    job_id = scheduler.submit_job(folder, lanl_input_file)

    current_step.job_id = job_id
    current_step.input_file = lanl_input_file
    current_step.log_file = lanl_output_file
    current_step.status = StepStatus.RUNNING
    print(f"Submitted LANL optimization for case {case.name} with job ID {job_id}.")

def run_dz_optimization(case: WorkflowCase, scheduler: Scheduler):

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

    job_id = scheduler.submit_job(folder, dz_input_file)

    current_step.job_id = job_id
    current_step.input_file = dz_input_file
    current_step.chk_file = dz_chk_file
    current_step.log_file = dz_output_file
    current_step.status = StepStatus.RUNNING
    print(f"Submitted DZ optimization for case {case.name} with job ID {job_id}.")
    
def check_optimization(case: WorkflowCase, scheduler: Scheduler):
    
    current_step = case.get_current_step()
    job_id = current_step.job_id

    if not job_id:
        print(f"No job ID found for {current_step.calculation_type.value} of case {case.name}. Marking as failed.")
        current_step.status = StepStatus.FAILED
        return

    if scheduler.is_job_running(job_id):
        return
    
    try:
        termination_status = get_log_termination_status(case)
        if termination_status == TerminationStatus.SUCCESS:
            current_step.status = StepStatus.COMPLETED
            case.last_geometry = get_last_geometry(current_step.log_file)
            slurm_output = Path(current_step.folder, f"slurm-{job_id}.out")
            slurm_output.unlink(missing_ok=True)
            fort_file = Path(current_step.folder, "fort.7")
            fort_file.unlink(missing_ok=True)
            print(f"{current_step.calculation_type.value} for case {case.name} completed successfully.")
        else:
            current_step.status = StepStatus.FAILED
            print(f"{current_step.calculation_type.value} for case {case.name} failed. Please check the logs for details.")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        print(f"Error while checking termination status for {current_step.calculation_type.value} of case {case.name}: {e}")

CALCULATION_TYPE_TO_RUN_STEP = {
    CalculationType.LANL_OPT: run_lanl_optimization,
    CalculationType.DZ_OPT: run_dz_optimization,
}  

CALCULATION_TYPE_TO_CHECK_STEP = {
    CalculationType.LANL_OPT: check_optimization,
    CalculationType.DZ_OPT: check_optimization,
}
    

    

    