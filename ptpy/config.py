from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent

INPUT_FOLDER: Path = Path("input_files")
REPOSITORY_FOLDER: Path = Path("repository")
RUN_FOLDER: Path = Path("runs")
BASES_FOLDER: Path = Path(PACKAGE_ROOT, "bases")

LANL_EXTENSION = "lanl"
DZ_EXTENSION = "dz" 

SCHEDULER = "slurm" # Options: "slurm", "local", "pbs"
PARTITION = "q_kchfo"
NUMBER_OF_CORES = 8
MEMORY = 2000 # in MB   

USER = "heiclj"
