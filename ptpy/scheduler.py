from enum import Enum
from pathlib import Path
import subprocess

from .scripts import spust_g16_script
from .config import SCHEDULER, PARTITION, NUMBER_OF_CORES_GAUSSAIN, MEMORY, USER

class UnsificientResourcesException(Exception):
    def __init__(self, message="No available resources to submit the job."):
        self.message = message
        super().__init__(self.message)

class RemoteExecutionException(Exception):
    def __init__(self, message="Failed to execute command on remote host."):
        self.message = message
        super().__init__(self.message)

class SubmissionFailedException(Exception):
    def __init__(self, message="Failed to submit the job."):
        self.message = message
        super().__init__(self.message)

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
            self.info_command = "sinfo"
            self.cancel_command = "scancel"
        else:
            raise NotImplementedError(f"Scheduler type {scheduler_type} is not implemented yet.")
        
    def get_nodes(self, status = "idle", node_type = "ne") -> list[str] | None:

        if self.scheduler_type == SchedulerType.SLURM:
            cmd = [self.info_command, "-N", "-h", "-t", status, "-o", "%N"]
            cmd.extend(["-p", PARTITION])

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            lines = result.stdout.splitlines()
            if not lines:
                return None
            return [line.strip() for line in lines if line.strip() and line.startswith(node_type)]
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")

    def get_running_jobs(self, running = True, pending = True, partition = None) -> list[tuple[str, str]]:

        if((not running) and (not pending)):
            raise RuntimeError("Specify atleast one of running or pending arguments")

        type = ""

        if running:
            type += "R"
        if pending:
            type = ",".join([type, "PD"])

        cmd = ["squeue", "-h", "-u", USER, "-t", type, "-o", "%i|%j"]
        if partition:
            cmd.extend(["-p", partition])

        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            jobid, name = line.split("|", 1)
            out.append((jobid, name))
        return out
    
    def is_job_running(self, job_id: str) -> bool:

        jobs = self.get_running_jobs()

        for jid, _ in jobs:
            if jid == job_id:
                return True
        return False

    def submit_job(self, cwd: Path, com_file: Path, chk_file: Path) -> str:

        nodes = self.get_nodes(status="idle")
        if not nodes:
            nodes = self.get_nodes(status="mixed")
        if not nodes:
            nodes = self.get_nodes(status="alloc")
        if not nodes:
            raise UnsificientResourcesException()

        job_script = spust_g16_script.substitute(
            num_cpus=NUMBER_OF_CORES_GAUSSAIN,
            job_name=com_file.stem,
            memory=MEMORY,
            chk_file=chk_file.name,
            partition=PARTITION,
            node=nodes[0]
        )
        job_script_path = Path(cwd, "job_script.sh")

        with open(job_script_path, "w") as f:
            f.write(job_script)
        subprocess.run(["chmod", "a+x", job_script_path], check=True)
        result = subprocess.run([self.submit_command, job_script_path.name, com_file.name], capture_output=True, text=True, cwd=cwd)

        if result.returncode != 0:
            raise SubmissionFailedException(f"Failed to submit job: {result.stderr}")
        job_id = result.stdout.strip().split()[-1]
        job_script_path.unlink()
        return job_id

    def cancel_job(self, job_id: str) -> None:
        if self.scheduler_type == SchedulerType.SLURM:
            subprocess.run([self.cancel_command, job_id], check=True)
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
        
    def remote_connect(self, target: str) -> None:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                subprocess.run(["ssh", target], check=True)
            except subprocess.CalledProcessError:
                raise RuntimeError(f"Failed to connect to {target}")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
        
    def remote_disconnect(self) -> None:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                subprocess.run(["exit"], check=True)
            except subprocess.CalledProcessError:
                raise RuntimeError(f"Failed to disconnect")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
        
    def run_remote_command(self, target: str, command: str) -> None:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                subprocess.run(["ssh", target, command], check=True)
            except subprocess.CalledProcessError:
                raise RemoteExecutionException(f"Failed to run command on {target}: {command}.")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
    
    def transfer_file_to_remote(self, file: Path, remote_host: str, remote_path: str) -> None:
        print(f"Transferring file {file} to {remote_host}:{remote_path}...")
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                subprocess.run(["rsync", "-avz", file, f"{remote_host}:{remote_path}"], check=True)
            except subprocess.CalledProcessError:
                raise RemoteExecutionException(f"Failed to transfer file {file} to {remote_path}.")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")