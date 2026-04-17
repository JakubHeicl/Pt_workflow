from pathlib import Path, PurePosixPath
import time
import shutil
import numpy as np

from .ir import LigandError, StepStatus, WorkflowCase, CalculationType
from .parser import FileStatus, get_aim_status, get_last_geometry, get_log_termination_status
from .scheduler import Scheduler, InsufficientResourcesError, RemoteExecutionException, SubmissionFailedException
from .utils import xyz_to_lanl, com_to_lanl, make_dz_file, make_ligand_file
from .config import AIM_CLUSTER, AIM_REMOTE_DIR, ALIP_SCRIPT, CONFIG_ALIP, LANL_EXTENSION, DZ_EXTENSION, LIGAND_EXTENSION, MAX_AIM_TIME, MAX_ALIP_TIME, NUMBER_OF_CORES_AIM, MAX_RUNNING_AIM, ALIP_ELSTAT_CLUSTER, ALIP_ELSTAT_REMOTE_DIR, POTMIT_EXE, ALIP_EXE ,ELSTAT_SCRIPT, ALIP_SCRIPT  
from .scripts import aim_analysis_script
from .interaction import Logger, Interaction, LigandReviewRequest, InteractionRequired

def init_step(case: WorkflowCase, expected_type: CalculationType, logger: Logger) -> bool:

    current_step = case.get_current_step()

    if current_step.calculation_type != expected_type:
        logger.log(f"Current step for case {case.name} is {current_step.calculation_type.value}, expected {expected_type.value}. Cannot initialize step.")
        current_step.status = StepStatus.FAILED
        return False

    for calc in current_step.required_calculations:

        step = case.get_step(calc)
        if step is None or step.status != StepStatus.COMPLETED:
            logger.log(f"Required calculation {calc.value} for step {current_step.calculation_type.value} of case {case.name} is not completed yet. Cannot initialize step.")
            current_step.status = StepStatus.FAILED
            return False
    
    current_step.folder = Path(case.directory, current_step.calculation_type.value)
    return True

def prepare_lanl_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):

    if not init_step(case, CalculationType.LANL_OPT, logger):
        return

    current_step = case.get_current_step()
    folder = current_step.folder
    input_file = case.input_file
    
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
    
    #Local files that will be used for LANL optimization
    current_step.local_files["com"] = lanl_com_file

    #Local files that are expected to be generated
    current_step.local_files["chk"] = lanl_chk_file
    current_step.local_files["log"] = lanl_log_file

    current_step.status = StepStatus.NOT_SUBMITTED

def prepare_dz_optimization(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):

    if not init_step(case, CalculationType.DZ_OPT, logger):
        return

    current_step = case.get_current_step()
    folder = current_step.folder
    
    last_geometry = case.last_geometry
    
    name = f"{case.name}_{DZ_EXTENSION}"
    
    folder.mkdir(parents=True, exist_ok=True)
    com_file = Path(folder, name).with_suffix(".com")
    chk_file = Path(folder, name).with_suffix(".chk")
    log_file = Path(folder, name).with_suffix(".log")

    den_file = Path(folder, name).with_suffix(".den")
    pot_file = Path(folder, name).with_suffix(".pot")


    make_dz_file(com_file, chk_file, last_geometry.geometry_lines, last_geometry.atoms_symbols, case.charge, case.multiplicity)

    #Local files that will be used for DZ optimization
    current_step.local_files["com"] = com_file

    #Local files that are expected to be generated
    current_step.local_files["chk"] = chk_file
    current_step.local_files["log"] = log_file
    current_step.local_files["den"] = den_file
    current_step.local_files["pot"] = pot_file

    current_step.status = StepStatus.NOT_SUBMITTED
    
def prepare_aim_analysis(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):

    if not init_step(case, CalculationType.AIM_ANALYSIS, logger):
        return

    current_step = case.get_current_step()

    dz_fchk_file = case.get_step(CalculationType.DZ_OPT).local_files.get("fchk")

    if dz_fchk_file is None or not dz_fchk_file.exists():
        logger.log(f"Formchk file from previous DZ optimization step is not available for case {case.name}. Cannot prepare AIM analysis.")
        current_step.status = StepStatus.FAILED
        return

    folder = current_step.folder
    folder.mkdir(parents=True, exist_ok=True)
    current_step.remote_folder = PurePosixPath(AIM_REMOTE_DIR, case.name)

    shutil.copy(dz_fchk_file, folder)

    #Local file that will be transferred to be used for AIM analysis
    current_step.local_files["fchk"] = Path(folder, dz_fchk_file.name)

    #Local files that are expected to be generated and then transferred
    current_step.local_files["sum"] = current_step.local_files["fchk"].with_suffix(".sum")
    current_step.local_files["wfx"] = current_step.local_files["fchk"].with_suffix(".wfx")
    current_step.local_files["out"] = Path(folder, "output.log")

    #Remote files that will be transferred to be used for AIM analysis
    current_step.remote_files["fchk"] = PurePosixPath(current_step.remote_folder, dz_fchk_file.name)

    #Remote files, that are expected to be generated
    current_step.remote_files["sum"] = current_step.remote_files.get("fchk").with_suffix(".sum")
    current_step.remote_files["wfx"] = current_step.remote_files.get("fchk").with_suffix(".wfx")
    current_step.remote_files["out"] = PurePosixPath(current_step.remote_folder, "output.log")

    current_step.status = StepStatus.NOT_SUBMITTED

def run_aim_analysis(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()

    if case.get_repository().get_number_of_cases_by_step_status(CalculationType.AIM_ANALYSIS, StepStatus.RUNNING) >= MAX_RUNNING_AIM:
        logger.log(f"Maximum number of running AIM analyses ({MAX_RUNNING_AIM}) reached. Waiting for a slot to be free...")
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
        current_step.status = StepStatus.NOT_SUBMITTED
        return
    
    current_step.start_time = int(time.time())
    current_step.status = StepStatus.RUNNING
    logger.log(f"Submitted AIM analysis for case {case.name} on cluster {AIM_CLUSTER}.")

def prepare_ligand_energies(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):

    if not init_step(case, CalculationType.LIGAND_ENERGIES_CALCULATION, logger):
        return

    geometry = case.last_geometry

    try:
        if geometry.ligands is None:
            ligand_review_response = interaction.request_manual_ligands(LigandReviewRequest(
                case_name=case.name,
                pt_neighbors_labels=[f"{atom.symbol}{geometry.get_atom_number(atom)}" for atom in geometry.pt_neighbors],
                atom_labels=[f"{atom.symbol}{geometry.get_atom_number(atom)}" for atom in geometry.atoms],
                total_charge=case.charge,
                pt_number=geometry.get_atom_number(geometry.get_pt_atom())
            ))
        else:
            ligand_review_response = interaction.review_ligands(LigandReviewRequest(
                case_name=case.name,
                pt_neighbors_labels=[f"{atom.symbol}{geometry.get_atom_number(atom)}" for atom in geometry.pt_neighbors],
                suggested_ligands=[[geometry.get_atom_number(atom) for atom in ligand] for ligand in geometry.ligands],
                atom_labels=[f"{atom.symbol}{geometry.get_atom_number(atom)}" for atom in geometry.atoms],
                total_charge=case.charge,
                pt_number=geometry.get_atom_number(geometry.get_pt_atom())
            ))
    except InteractionRequired:
        logger.log(f"Ligand review is required for case {case.name} but no interaction method is available. Skipping for now.")
        return
    
    geometry.ligand_charges = ligand_review_response.ligand_charges
    geometry.ligands = [[geometry.get_atom_by_number(number) for number in ligand] for ligand in ligand_review_response.ligands]

    current_step = case.get_current_step()
    folder = current_step.folder
    
    name = f"{case.name}_{LIGAND_EXTENSION}"

    folder.mkdir(parents=True, exist_ok=True)
    com_file = Path(folder, name).with_suffix(".com")
    chk_file = Path(folder, name).with_suffix(".chk")
    log_file = Path(folder, name).with_suffix(".log")

    make_ligand_file(com_file, chk_file, geometry, case.charge, case.multiplicity)

    #Local files that will be used for ligand energies calculation
    current_step.local_files["com"] = com_file

    #Local files that are expected to be generated
    current_step.local_files["chk"] = chk_file
    current_step.local_files["log"] = log_file

    current_step.status = StepStatus.NOT_SUBMITTED

def run_gaussian_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()

    folder = current_step.folder
    com_file = current_step.local_files.get("com")
    chk_file = current_step.local_files.get("chk")

    try:
        job_id = scheduler.submit_job(folder, com_file, chk_file)
    except InsufficientResourcesError:
        logger.log(f"Insufficient resources to run {current_step.calculation_type.value} for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITTED
        return
    except SubmissionFailedException:
        logger.log(f"Failed to submit {current_step.calculation_type.value} job for case {case.name}. Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITTED
        return
    
    current_step.job_id = job_id
    
    current_step.status = StepStatus.RUNNING
    logger.log(f"Submitted {current_step.calculation_type.value} for case {case.name} with job ID {job_id}.")

def prepare_alip_elstat_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger, interaction: Interaction):

    if not init_step(case, CalculationType.ALIP_ELSTAT_CALCULATION, logger):
        return

    current_step = case.get_current_step()
    dz_step = case.get_step(CalculationType.DZ_OPT)

    folder = current_step.folder
    folder.mkdir(parents=True, exist_ok=True)
    current_step.remote_folder = PurePosixPath(ALIP_ELSTAT_REMOTE_DIR, case.name)

    den_file = dz_step.local_files.get("den")
    pot_file = dz_step.local_files.get("pot")
    fchk_file = dz_step.local_files.get("fchk")

    shutil.copy(den_file, folder)
    shutil.copy(pot_file, folder)
    shutil.copy(fchk_file, folder)

    #Local files that will be transferred to be used for ALIP ELSTAT calculation
    current_step.local_files["den"] = Path(folder, den_file.name)
    current_step.local_files["pot"] = Path(folder, pot_file.name)
    current_step.local_files["fchk"] = Path(folder, fchk_file.name)

    #Local files that will be transferred to be used for ALIP ELSTAT calculation
    current_step.remote_files["den"] = PurePosixPath(current_step.remote_folder, den_file.name)
    current_step.remote_files["pot"] = PurePosixPath(current_step.remote_folder, pot_file.name)
    current_step.remote_files["fchk"] = PurePosixPath(current_step.remote_folder, fchk_file.name)

    #Remote files, that are expected to be generated
    current_step.remote_files["exa"] = PurePosixPath(current_step.remote_folder, den_file.with_suffix(".exa-s").name)
    current_step.remote_files["exp"] = PurePosixPath(current_step.remote_folder, den_file.with_suffix(".exp-s").name)

    #Local files that are expected to be generated and then transferred
    current_step.local_files["exa"] = Path(folder, den_file.with_suffix(".exa-s").name)
    current_step.local_files["exp"] = Path(folder, den_file.with_suffix(".exp-s").name)

    current_step.status = StepStatus.NOT_SUBMITTED

def run_alip_elstat_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()

    remote_folder = current_step.remote_folder
    den_file = current_step.local_files.get("den")
    pot_file = current_step.local_files.get("pot")
    fchk_file = current_step.local_files.get("fchk")

    try:
        logger.log(f"Running command on {ALIP_ELSTAT_CLUSTER}: mkdir -p {remote_folder}")
        scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"mkdir -p {remote_folder}")
        logger.log(f"Transferring file {fchk_file}, {den_file}, {pot_file} to {ALIP_ELSTAT_CLUSTER}:{remote_folder}")
        scheduler.transfer_file_to_remote(den_file, ALIP_ELSTAT_CLUSTER, str(remote_folder))
        scheduler.transfer_file_to_remote(pot_file, ALIP_ELSTAT_CLUSTER, str(remote_folder))
        scheduler.transfer_file_to_remote(fchk_file, ALIP_ELSTAT_CLUSTER, str(remote_folder))

        logger.log(f"Transferring file alip.exe, potmit.exe to {ALIP_ELSTAT_CLUSTER}:{remote_folder}")
        scheduler.transfer_file_to_remote(ALIP_EXE, ALIP_ELSTAT_CLUSTER, str(remote_folder))
        scheduler.transfer_file_to_remote(POTMIT_EXE, ALIP_ELSTAT_CLUSTER, str(remote_folder))  

        logger.log(f"Transferring file alip.sh, elstat.sh and config to {ALIP_ELSTAT_CLUSTER}:{remote_folder}")
        scheduler.transfer_file_to_remote(ALIP_SCRIPT, ALIP_ELSTAT_CLUSTER, str(remote_folder))
        scheduler.transfer_file_to_remote(ELSTAT_SCRIPT, ALIP_ELSTAT_CLUSTER, str(remote_folder))
        scheduler.transfer_file_to_remote(CONFIG_ALIP, ALIP_ELSTAT_CLUSTER, str(remote_folder))

        logger.log(f"Running ALIP ELSTAT script on {ALIP_ELSTAT_CLUSTER} for case {case.name}")
        scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"cd {remote_folder} && chmod a+x alip.sh elstat.sh")
        scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"cd {remote_folder} && chmod a+x potmin.exe alip.exe")

        scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"cd {remote_folder} && ./elstat.sh")
        scheduler.run_remote_background_command(ALIP_ELSTAT_CLUSTER, f"/bin/bash -lc 'cd {remote_folder} && nohup ./alip.sh > output.log 2>&1 </dev/null &'")

    except RemoteExecutionException as e:
        logger.log(f"Failed to run ALIP ELSTAT calculations for case {case.name} on cluster {ALIP_ELSTAT_CLUSTER}: {e} Trying again later...")
        current_step.status = StepStatus.NOT_SUBMITTED
        return
    
    current_step.start_time = int(time.time())
    current_step.status = StepStatus.RUNNING
    logger.log(f"Submitted ALIP ELSTAT calculations for case {case.name} on cluster {ALIP_ELSTAT_CLUSTER}.")

def check_gaussian_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    job_id = current_step.job_id

    if not job_id:
        logger.log(f"No job ID found for {current_step.calculation_type.value} of case {case.name}. Marking as failed.")
        current_step.status = StepStatus.FAILED
        return

    if scheduler.is_job_active(job_id):
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

            if current_step.calculation_type in [CalculationType.LANL_OPT, CalculationType.DZ_OPT]:
                case.last_geometry = get_last_geometry(current_step.local_files.get("log"))
                if current_step.calculation_type == CalculationType.DZ_OPT:
                    logger.log(f"Extracted geometry from log file for case {case.name} after DZ optimization. Looking for ligands ...")
                    try:
                        case.last_geometry.detect_and_store_ligands()
                    except LigandError as e:
                        logger.log(f"Error while finding ligands for case {case.name}: {e}. Please specify them manually.")

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
    sum_file = current_step.remote_files.get("sum")
    wfx_file = current_step.remote_files.get("wfx")

    try:
        if scheduler.does_remote_file_exist(AIM_CLUSTER, output_file) and scheduler.does_remote_file_exist(AIM_CLUSTER, sum_file) and scheduler.does_remote_file_exist(AIM_CLUSTER, wfx_file):
            if scheduler.does_remote_file_contain(AIM_CLUSTER, output_file, "AIMQB Job Completed"):
                scheduler.transfer_file_from_remote(AIM_CLUSTER, str(output_file), current_step.folder)
                scheduler.transfer_file_from_remote(AIM_CLUSTER, str(sum_file), current_step.folder)
                scheduler.transfer_file_from_remote(AIM_CLUSTER, str(wfx_file), current_step.folder)
                scheduler.run_remote_command(AIM_CLUSTER, f"rm -rf {current_step.remote_folder}")
                current_step.status = StepStatus.COMPLETED
                logger.log(f"AIM analysis for case {case.name} completed successfully.")
        if current_step.start_time and time.time() - current_step.start_time > MAX_AIM_TIME:
            logger.log(f"AIM analysis for case {case.name} is running for a long time. Please check the output log for details. Marking as not sure for now.")
            current_step.status = StepStatus.NOT_SURE  

    except RemoteExecutionException as e:
        logger.log(f"Error while checking AIM analysis for case {case.name} on cluster {AIM_CLUSTER}: {e}. Trying again later...")
        return

def check_alip_elstat_calculation(case: WorkflowCase, scheduler: Scheduler, logger: Logger):

    current_step = case.get_current_step()
    remote_exa_file = current_step.remote_files.get("exa")
    remote_exp_file = current_step.remote_files.get("exp")

    try:
        if scheduler.does_remote_file_exist(ALIP_ELSTAT_CLUSTER, remote_exa_file) and scheduler.does_remote_file_exist(ALIP_ELSTAT_CLUSTER, remote_exp_file):
            if scheduler.get_remote_file_size(ALIP_ELSTAT_CLUSTER, remote_exa_file) > 0 and scheduler.get_remote_file_size(ALIP_ELSTAT_CLUSTER, remote_exp_file) > 0:
                scheduler.transfer_file_from_remote(ALIP_ELSTAT_CLUSTER, str(remote_exa_file), current_step.folder)
                scheduler.transfer_file_from_remote(ALIP_ELSTAT_CLUSTER, str(remote_exp_file), current_step.folder)
                scheduler.run_remote_command(ALIP_ELSTAT_CLUSTER, f"rm -rf {current_step.remote_folder}")
                current_step.status = StepStatus.COMPLETED
                logger.log(f"ALIP ELSTAT calculations for case {case.name} completed successfully.")
        if current_step.start_time and time.time() - current_step.start_time > MAX_ALIP_TIME:
            current_step.status = StepStatus.NOT_SURE
            logger.log(f"ALIP ELSTAT calculations for case {case.name} are running for a long time. Please check the output files on cluster {ALIP_ELSTAT_CLUSTER} for details. Marking as not sure for now.")

    except RemoteExecutionException as e:
        logger.log(f"Error while checking ALIP ELSTAT calculation for case {case.name} on cluster {ALIP_ELSTAT_CLUSTER}: {e}. Trying again later...")        
        return

CALCULATION_TYPE_TO_PREPARE_STEP = {
    CalculationType.LANL_OPT: prepare_lanl_optimization,
    CalculationType.DZ_OPT: prepare_dz_optimization,
    CalculationType.AIM_ANALYSIS: prepare_aim_analysis,
    CalculationType.LIGAND_ENERGIES_CALCULATION: prepare_ligand_energies,
    CalculationType.ALIP_ELSTAT_CALCULATION: prepare_alip_elstat_calculation,
}

CALCULATION_TYPE_TO_RUN_STEP = {
    CalculationType.LANL_OPT: run_gaussian_calculation,
    CalculationType.DZ_OPT: run_gaussian_calculation,
    CalculationType.AIM_ANALYSIS: run_aim_analysis,
    CalculationType.LIGAND_ENERGIES_CALCULATION: run_gaussian_calculation,
    CalculationType.ALIP_ELSTAT_CALCULATION: run_alip_elstat_calculation,
}

CALCULATION_TYPE_TO_CHECK_STEP = {
    CalculationType.LANL_OPT: check_gaussian_calculation,
    CalculationType.DZ_OPT: check_gaussian_calculation,
    CalculationType.AIM_ANALYSIS: check_aim_analysis,
    CalculationType.LIGAND_ENERGIES_CALCULATION: check_gaussian_calculation,
    CalculationType.ALIP_ELSTAT_CALCULATION: check_alip_elstat_calculation,
}
    

    

    