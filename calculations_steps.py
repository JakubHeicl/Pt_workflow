from ir import Status, WorkflowCase, CalculationType
from scheduler import Scheduler
from utils import xyz_to_lanl, com_to_lanl
from pathlib import Path
from config import LANL_EXTENSION

def run_lanl_optimization(case: WorkflowCase, scheduler: Scheduler):
    current_step = case.get_current_step()
    folder = current_step.folder
    input_file = case.input_file

    if current_step.calculation_type != CalculationType.LANL_OPT:
        raise ValueError(f"Expected OPTIMIZATION step, got {current_step.calculation_type}.")
    
    name = f"{case.name}_{LANL_EXTENSION}"

    folder.mkdir(parents=True, exist_ok=True)
    output_file = Path(folder, name).with_suffix(".com")

    if input_file.suffix == ".xyz":
        xyz_to_lanl(input_file, output_file, case.charge, case.multiplicity)

    elif input_file.suffix == ".com":
        com_to_lanl(input_file, output_file)
    else:
        raise ValueError(f"Unsupported input file format: {input_file.suffix}")
    
    job_id = scheduler.submit_job(folder, name)

    current_step.job_id = job_id
    current_step.status = Status.RUNNING
    print(f"Submitted LANL optimization for case {case.name} with job ID {job_id}.")
    

    

    