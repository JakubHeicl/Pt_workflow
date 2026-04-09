from pathlib import Path

INPUT_FOLDER: Path = Path("input_files")
REPOSITORY_FOLDER: Path = Path("repository")
RUN_FOLDER: Path = Path("runs")

LANL_EXTENSION = "lanl"

SCHEDULER = "slurm" # Options: "slurm", "local", "pbs"
PARTITION = "q_kchfo"
NUMBER_OF_CORES = 4
MEMORY = 2000 # in MB   

