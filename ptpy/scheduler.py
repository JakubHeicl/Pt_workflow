from enum import Enum
from pathlib import Path
import subprocess
import shlex

from .scripts import spust_g16_script
from .config import SCHEDULER, PARTITION, GAUSSIAN_NUM_CORES, MEMORY, USER

class InsufficientResourcesError(Exception):
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

    def get_active_jobs(self, running = True, pending = True, partition = None) -> list[tuple[str, str]]:

        if((not running) and (not pending)):
            raise RuntimeError("Specify at least one of running or pending arguments")

        states_arg = ""

        if running:
            states_arg += "R"
        if pending:
            states_arg = ",".join([states_arg, "PD"])

        cmd = ["squeue", "-h", "-u", USER, "-t", states_arg, "-o", "%i|%j"]
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
    
    def is_job_active(self, job_id: str) -> bool:

        jobs = self.get_active_jobs()

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
            raise InsufficientResourcesError()

        job_script = spust_g16_script.substitute(
            num_cpus=GAUSSIAN_NUM_CORES,
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
        
    def run_remote_command(self, target: str, command: str) -> str | None:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                result = subprocess.run(["ssh", "-T", "-n", target, command], check=True, capture_output=True, text=True)
                return result.stdout if result.stdout else None
            except subprocess.CalledProcessError:
                raise RemoteExecutionException(f"Failed to run command on {target}: {command}.")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
        
    def run_remote_background_command(self, target: str, command: str) -> None:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                subprocess.run(["ssh", "-T", "-n", "-f", target, command], check=True)
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
        

    def transfer_file_from_remote(self, remote_host: str, remote_path: str, local_path: Path) -> None:

        print(f"Transferring file {remote_host}:{remote_path} to {local_path}...")
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                subprocess.run(["rsync", "-avz", f"{remote_host}:{remote_path}", local_path], check=True)
            except subprocess.CalledProcessError:
                raise RemoteExecutionException(f"Failed to transfer file {remote_path} from {remote_host}.")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
        
    def does_remote_file_exist(self, remote_host: str, remote_path: str) -> bool:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                result = subprocess.run(["ssh", remote_host, "test", "-e", remote_path], check=True)
                return result.returncode == 0
            except subprocess.CalledProcessError:
                return False
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")
        
    def get_remote_file_size(self, remote_host: str, remote_path: str) -> int:
        if self.scheduler_type == SchedulerType.SLURM:
            try:
                result = subprocess.run(["ssh", remote_host, "stat", "-f", "%z", remote_path], check=True, capture_output=True, text=True)
                return int(result.stdout.strip())
            except subprocess.CalledProcessError:
                raise RemoteExecutionException(f"Failed to get size of file {remote_path} from {remote_host}.")
        else:
            raise NotImplementedError(f"Scheduler type {self.scheduler_type} is not implemented yet.")

    def does_remote_file_contain(self, remote_host: str, remote_path: str, text: str) -> bool:
        if self.scheduler_type == SchedulerType.SLURM:
            command = f"grep -F -q -- {shlex.quote(text)} {shlex.quote(str(remote_path))}"
            result = subprocess.run(
                ["ssh", "-T", "-n", remote_host, command],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True
            if result.returncode == 1:
                return False
            raise RemoteExecutionException(
                f"Failed to search in remote file {remote_path} on {remote_host}: {result.stderr.strip()}"
            )
        else:
            raise NotImplementedError(...)
