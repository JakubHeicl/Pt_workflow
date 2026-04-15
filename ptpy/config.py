from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent

INPUT_FOLDER: Path = Path("input_files")
REPOSITORY_FOLDER: Path = Path("repository")
METADATA_FILE: Path = Path("metadata.json")
RUN_FOLDER: Path = Path("runs")
BASES_FOLDER: Path = Path(PACKAGE_ROOT, "bases")

LOOP_SLEEP_TIME = 20 # in seconds

LANL_EXTENSION = "lanl"
DZ_EXTENSION = "dz" 
LIGAND_EXTENSION = "ligands"

AIM_CLUSTER =           "heiclj@jupiter.karlov.mff.cuni.cz"
ALIP_ELSTAT_CLUSTER =   "heiclj@jupiter.karlov.mff.cuni.cz"
AIM_FOLDER =            "/Volumes/Home_2/Users_Ju/heiclj/ptpy_calculations/aim"
ALIP_ELSTAT_FOLDER =    "/Volumes/Home_2/Users_Ju/heiclj/ptpy_calculations/alip_elstat"

POTMIT_EXE = Path(PACKAGE_ROOT, "scripts", "potmin.exe")
ALIP_EXE = Path(PACKAGE_ROOT, "scripts", "alip.exe")

ELSTAT_SCRIPT = Path(PACKAGE_ROOT, "scripts", "elstat.sh")
ALIP_SCRIPT = Path(PACKAGE_ROOT, "scripts", "alip.sh")
CONFIG_ALIP = Path(PACKAGE_ROOT, "scripts", "config")
MAX_ALIP_TIME = 360

MAX_RUNNING_AIM = 4
MAX_AIM_TIME = 3600 * 4 # in seconds

SCHEDULER = "slurm" # Options: "slurm", "local", "pbs"
PARTITION = "q_kchfo"
NUMBER_OF_CORES_GAUSSAIN = 16
MEMORY = 4000 # in MB   

NUMBER_OF_CORES_AIM = 4

USER = "heiclj"