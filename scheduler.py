from enum import Enum
from pathlib import Path
import subprocess
from bash_scripts import spust_g16_script
from config import SCHEDULER, PARTITION, NUMBER_OF_CORES, MEMORY

class SchedulerType(Enum):
    SLURM = "slurm"
    PBS = "pbs"
    LOCAL = "local"

class Scheduler:
    def __init__(self, scheduler_type: str):

        if scheduler_type not in [s.value for s in SchedulerType]:
            raise ValueError(f"Unsupported scheduler type: {scheduler_type}. Supported types are: {[s.value for s in SchedulerType]}")
        
        for s in SchedulerType:
            if s.value == scheduler_type:
                self.scheduler_type = s
                break

        if self.scheduler_type == SchedulerType.SLURM:
            self.submit_command = "sbatch"
            self.status_command = "squeue"
            self.cancel_command = "scancel"
        else:
            raise NotImplementedError(f"Scheduler type {scheduler_type} is not implemented yet.")

    def submit_job(self, cwd: Path, output_file: Path) -> str:

        job_script = spust_g16_script.substitute(
            num_cpus=NUMBER_OF_CORES,
            job_name=output_file.stem,
            memory=MEMORY,
            partition=PARTITION
        )
        job_script_path = Path(cwd, "job_script.sh")

        with open(job_script_path, "w") as f:
            f.write(job_script)
        subprocess.run(["chmod", "+x", job_script_path], check=True)
        result = subprocess.run([self.submit_command, job_script_path.name, output_file.name], capture_output=True, text=True, cwd=cwd)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to submit job: {result.stderr}")
        job_id = result.stdout.strip().split()[-1]
        #job_script_path.unlink()
        return job_id

