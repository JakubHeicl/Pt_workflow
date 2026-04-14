from pathlib import Path
import time
import shutil
import numpy as np

from .ir import StepStatus, WorkflowCase, CalculationType
from .parser import FileStatus, get_aim_status, get_last_geometry, get_log_termination_status
from .scheduler import Scheduler, UnsificientResourcesException, RemoteExecutionException, SubmissionFailedException
from .utils import xyz_to_lanl, com_to_lanl, make_dz_file, make_ligand_file
from .config import AIM_CLUSTER, AIM_FOLDER, LANL_EXTENSION, DZ_EXTENSION, LIGAND_EXTENSION, NUMBER_OF_CORES_AIM, MAX_RUNNING_AIM     
from .scripts import aim_analysis_script
from .logger import Logger

def prepare_lanl_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    folder = current_step.folder
    input_file = case.input_file

    if current_step.calculation_type != CalculationType.LANL_OPT:
        raise ValueError(f"Expected LANL OPTIMIZATION step, got {current_step.calculation_type}.")
    
    name = f"{case.name}_{LANL_EXTENSION}"

    folder.mkdir(parents=True, exist_ok=True)
    lanl_com_file = Path(folder, name).with_suffix(".com")
    lanl_chk_file = Path(folder, name).with_suffix(".chk")
    lanl_log_file = Path(folder, name).with_suffix(".log")

    if input_file.suffix == ".xyz":
        xyz_to_lanl(input_file, lanl_com_file, lanl_chk_file, case.charge, case.multiplicity)
    elif input_file.suffix == ".com":
        com_to_lanl(input_file, lanl_com_file, lanl_chk_file)
    else:
        raise ValueError(f"Unsupported input file format: {input_file.suffix}")
    
    current_step.local_files["com"] = lanl_com_file
    current_step.local_files["chk"] = lanl_chk_file
    current_step.local_files["log"] = lanl_log_file

    current_step.status = StepStatus.NOT_SUBMITED

def prepare_dz_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    folder = current_step.folder

    if current_step.calculation_type != CalculationType.DZ_OPT:
        raise ValueError(f"Expected DZ OPTIMIZATION step, got {current_step.calculation_type}.")
    
    last_geometry = case.last_geometry
    if last_geometry is None:
        raise ValueError(f"No geometry found for case {case.name}. Cannot run DZ optimization.")
    
    name = f"{case.name}_{DZ_EXTENSION}"
    
    folder.mkdir(parents=True, exist_ok=True)
    dz_com_file = Path(folder, name).with_suffix(".com")
    dz_chk_file = Path(folder, name).with_suffix(".chk")
    dz_log_file = Path(folder, name).with_suffix(".log")

    make_dz_file(dz_com_file, dz_chk_file, last_geometry.geometry_lines, last_geometry.atoms_symbols, case.charge, case.multiplicity)

    current_step.local_files["com"] = dz_com_file
    current_step.local_files["chk"] = dz_chk_file
    current_step.local_files["log"] = dz_log_file

    current_step.status = StepStatus.NOT_SUBMITED
    
def prepare_aim_analysis(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    if case.get_repository().metadata.get("running_aim") is None:
        case.get_repository().metadata["running_aim"] = 0

    current_step = case.get_current_step()
    previous_step = case.get_previous_step()

    if current_step.calculation_type != CalculationType.AIM_ANALYSIS:
        raise ValueError(f"Expected AIM ANALYSIS step, got {current_step.calculation_type}.")
    
    if previous_step.calculation_type != CalculationType.DZ_OPT:
        raise ValueError(f"Expected previous step to be DZ OPTIMIZATION, got {previous_step.calculation_type}.")
    
    formchk_file = previous_step.local_files.get("fchk")

    if formchk_file is None or not formchk_file.exists():
        logger.log(f"Formchk file from previous DZ optimization step is not available for case {case.name}. Cannot prepare AIM analysis.")
        current_step.status = StepStatus.FAILED
        return

    folder = current_step.folder
    folder.mkdir(parents=True, exist_ok=True)
    current_step.remote_folder = Path(AIM_FOLDER, case.name)
    remote_folder = current_step.remote_folder
    current_step.remote_files["fchk"] = Path(remote_folder, formchk_file.name)
    current_step.remote_files["out"] = Path(remote_folder, "output.log")
    shutil.copy(formchk_file, folder)
    current_step.local_files["fchk"] = Path(folder, formchk_file.name)

    current_step.status = StepStatus.NOT_SUBMITED

def run_aim_analysis(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()

    if case.get_repository().metadata.get("running_aim", 0) >= MAX_RUNNING_AIM:
        logger.log(f"Maximum number of running AIM analyses reached. Cannot run AIM analysis for case {case.name} now. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return

    remote_folder = current_step.remote_folder
    formchk_file = current_step.local_files.get("fchk")

    try:

        aim_script = aim_analysis_script.substitute(folder=remote_folder, fchk_file=current_step.remote_files.get("fchk").name, num_cpus=NUMBER_OF_CORES_AIM)

        logger.log(f"Running command on {AIM_CLUSTER}: mkdir -p {remote_folder}")
        scheduler.run_remote_command(AIM_CLUSTER, f"mkdir -p {remote_folder}")
        logger.log(f"Transferring file {formchk_file} to {AIM_CLUSTER}:{remote_folder}")
        scheduler.transfer_file_to_remote(formchk_file, AIM_CLUSTER, str(remote_folder))
        logger.log(f"Running command on {AIM_CLUSTER}: {aim_script}")
        scheduler.run_remote_background_command(AIM_CLUSTER, aim_script)
    except RemoteExecutionException as e:
        logger.log(f"Failed to run AIM analysis for case {case.name} on cluster {AIM_CLUSTER}: {e} Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    
    current_step.status = StepStatus.RUNNING
    case.get_repository().metadata["running_aim"] = case.get_repository().metadata.get("running_aim", 0) + 1
    logger.log(f"Submitted AIM analysis for case {case.name} on cluster {AIM_CLUSTER}.")

def prepare_ligand_energies(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    geometry = case.last_geometry

    if geometry is None:
        raise ValueError(f"No geometry found for case {case.name}. Cannot run ligand energies calculation.")

    if not logger.verbose:
        logger.log("Verbose mode is off. To proceed with ligand energies calculation, please turn on verbose mode to see the ligands and confirm that they are correct.")
        return

    for i, _ in enumerate(geometry.ligands): logger.log(f"Ligand for {geometry.pt_neighbors[i].symbol}{geometry.get_atom_index(geometry.pt_neighbors[i])}:\n{geometry.ligand_to_str(i)}\n")

    if not logger.reassure("Please confirm that the ligands are correct. Do you want to proceed with ligand energies calculation?"):
        
        geometry.ligands = []
        for atom in geometry.atoms: logger.log(f"{geometry.get_atom_index(atom):<4} {atom.symbol:<3}")
        for atom in geometry.pt_neighbors:
            ligand = []
            for index in np.array(logger.get_input(f"Write index of atoms to the ligand {atom.symbol}{geometry.get_atom_index(atom)}:\n").strip().split(), dtype = int):
                ligand.append(geometry.get_atom(index))
            geometry.ligands.append(ligand)

        for i, _ in enumerate(geometry.ligands): logger.log(f"Ligand for {geometry.pt_neighbors[i].symbol}{geometry.get_atom_index(geometry.pt_neighbors[i])}:\n{geometry.ligand_to_str(i)}\n")

    not_correct = True
    while not_correct:
        geometry.ligand_charges = [int(x) for x in logger.get_input(f"Write formal charges to each ligand (space-separated). The total charge is {case.charge}\n").strip().split()]
        if (sum(geometry.ligand_charges)+4) != case.charge:
            logger.log(f"Warning: The total charge of the ligands ({sum(geometry.ligand_charges)}) does not match the expected total charge ({case.charge}). Please double-check the charges you entered.")
        else:
            not_correct = False

    current_step = case.get_current_step()
    folder = current_step.folder
    
    name = f"{case.name}_{LIGAND_EXTENSION}"

    folder.mkdir(parents=True, exist_ok=True)
    com_file = Path(folder, name).with_suffix(".com")
    chk_file = Path(folder, name).with_suffix(".chk")
    log_file = Path(folder, name).with_suffix(".log")

    make_ligand_file(com_file, chk_file, geometry, case.charge, case.multiplicity)

    current_step.local_files["com"] = com_file
    current_step.local_files["chk"] = chk_file
    current_step.local_files["log"] = log_file

    current_step.status = StepStatus.NOT_SUBMITED

def run_gaussian_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()

    if current_step.status != StepStatus.NOT_SUBMITED:
        return

    folder = current_step.folder
    com_file = current_step.local_files.get("com")
    chk_file = current_step.local_files.get("chk")

    try:
        job_id = scheduler.submit_job(folder, com_file, chk_file)
    except UnsificientResourcesException:
        logger.log(f"Insufficient resources to run {current_step.calculation_type.value} for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    except SubmissionFailedException:
        logger.log(f"Failed to submit {current_step.calculation_type.value} job for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITED
        return
    
    current_step.job_id = job_id
    
    current_step.status = StepStatus.RUNNING
    logger.log(f"Submitted {current_step.calculation_type.value} for case {case.name} with job ID {job_id}.")

def check_gaussian_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    job_id = current_step.job_id

    if not job_id:
        logger.log(f"No job ID found for {current_step.calculation_type.value} of case {case.name}. Marking as failed.")
        current_step.status = StepStatus.FAILED
        return

    if scheduler.is_job_running(job_id):
        return
    
    formchk_file = current_step.local_files.get("com").with_suffix(".fchk")

    if not formchk_file.exists():
        logger.log(f"Formchk file {formchk_file} for {current_step.calculation_type.value} of case {case.name} might still not be ready. Waiting...")
        time.sleep(10)
        if not formchk_file.exists():
            logger.log(f"Formchk file {formchk_file} for {current_step.calculation_type.value} of case {case.name} is still not available after waiting. Marking as failed.")
            current_step.status = StepStatus.FAILED
            return

    while formchk_file.stat().st_mtime + 15 > time.time():
        logger.log(f"Formchk file {formchk_file} for {current_step.calculation_type.value} of case {case.name} might still not be ready. Waiting...")
        time.sleep(10)

    current_step.local_files["fchk"] = formchk_file

    try:
        termination_status = get_log_termination_status(case)
        if termination_status == FileStatus.SUCCESS:
            current_step.status = StepStatus.COMPLETED
            case.last_geometry = get_last_geometry(current_step.local_files.get("log"))
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
    
    current_step = case.get_current_step()
    output_file = current_step.remote_files.get("out")

    folder = current_step.folder

    current_step.local_files["out"] = Path(folder, "output.log")
    try:
        scheduler.transfer_file_from_remote(AIM_CLUSTER, str(output_file), folder)
    except RemoteExecutionException as e:
        logger.log(f"Error while transferring AIM output file for case {case.name}: {e}. Trying again later...")
        return
    
    file_status = get_aim_status(current_step.local_files["out"])

    if file_status == FileStatus.SUCCESS:
        if not scheduler.does_remote_file_exist(AIM_CLUSTER, current_step.remote_files.get("fchk").with_suffix(".sum")):
            logger.log(f"AIM output file for case {case.name} indicates success, but summary file is missing. Marking as not sure for now.")
            current_step.status = StepStatus.NOT_SURE
            case.get_repository().metadata["running_aim"] = case.get_repository().metadata.get("running_aim", 0) - 1
            return
        try:
            scheduler.transfer_file_from_remote(AIM_CLUSTER, str(current_step.remote_files.get("fchk").with_suffix(".sum")), folder)
            scheduler.transfer_file_from_remote(AIM_CLUSTER, str(current_step.remote_files.get("fchk").with_suffix(".wfx")), folder)
            scheduler.run_remote_command(AIM_CLUSTER, f"rm -rf {current_step.remote_folder}")
        except RemoteExecutionException as e:
            logger.log(f"Error while transferring AIM result files for case {case.name}: {e}. Trying again later...")
            return
        current_step.local_files["sum"] = current_step.local_files["fchk"].with_suffix(".sum")
        current_step.local_files["wfx"] = current_step.local_files["fchk"].with_suffix(".wfx")
        current_step.status = StepStatus.COMPLETED
        case.get_repository().metadata["running_aim"] = case.get_repository().metadata.get("running_aim", 0) - 1
        logger.log(f"AIM analysis for case {case.name} completed successfully.")
    elif file_status == FileStatus.NOT_SURE:
        case.get_repository().metadata["running_aim"] = case.get_repository().metadata.get("running_aim", 0) - 1
        logger.log(f"AIM analysis for case {case.name} is running for a long time. Please check the output log for details. Marking as not sure for now.")
        current_step.status = StepStatus.NOT_SURE
        return
    elif file_status == FileStatus.FAILURE:
        case.get_repository().metadata["running_aim"] = case.get_repository().metadata.get("running_aim", 0) - 1
        current_step.status = StepStatus.FAILED
        logger.log(f"AIM analysis for case {case.name} failed. Please check the logs for details.")
    elif file_status == FileStatus.RUNNING:
        return


CALCULATION_TYPE_TO_PREPARE_STEP = {
    CalculationType.LANL_OPT: prepare_lanl_optimization,
    CalculationType.DZ_OPT: prepare_dz_optimization,
    CalculationType.AIM_ANALYSIS: prepare_aim_analysis,
    CalculationType.LIGAND_ENERGIES_CALCULATION: prepare_ligand_energies,
}

CALCULATION_TYPE_TO_RUN_STEP = {
    CalculationType.LANL_OPT: run_gaussian_calculation,
    CalculationType.DZ_OPT: run_gaussian_calculation,
    CalculationType.AIM_ANALYSIS: run_aim_analysis,
    CalculationType.LIGAND_ENERGIES_CALCULATION: run_gaussian_calculation,
}

CALCULATION_TYPE_TO_CHECK_STEP = {
    CalculationType.LANL_OPT: check_gaussian_calculation,
    CalculationType.DZ_OPT: check_gaussian_calculation,
    CalculationType.AIM_ANALYSIS: check_aim_analysis,
    CalculationType.LIGAND_ENERGIES_CALCULATION: check_gaussian_calculation,
}
    

    

    