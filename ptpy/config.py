from pathlib import Path, PurePosixPath

PACKAGE_ROOT            = Path(__file__).resolve().parent

INPUT_FOLDER: Path      = Path("input_files")
REPOSITORY_DIR: Path    = Path("repository")
RUNS_DIR: Path          = Path("runs")
BASES_FOLDER: Path      = Path(PACKAGE_ROOT, "bases")
STOP_FILE: Path         = Path(REPOSITORY_DIR, "STOP_FILE")

LOOP_SLEEP_TIME         = 120 # in seconds

LANL_EXTENSION          = "lanl"
DZ_EXTENSION            = "dz" 
LIGAND_EXTENSION        = "ligands"

AIM_CLUSTER             = "heiclj@jupiter.karlov.mff.cuni.cz"
ALIP_ELSTAT_CLUSTER     = "heiclj@jupiter.karlov.mff.cuni.cz"

AIM_REMOTE_DIR          = PurePosixPath("/Volumes/Home_2/Users_Ju/heiclj/ptpy_calculations/aim")
ALIP_ELSTAT_REMOTE_DIR  = PurePosixPath("/Volumes/Home_2/Users_Ju/heiclj/ptpy_calculations/alip_elstat")

POTMIT_EXE              = Path(PACKAGE_ROOT, "scripts", "potmin.exe")
ALIP_EXE                = Path(PACKAGE_ROOT, "scripts", "alip.exe")

ELSTAT_SCRIPT           = Path(PACKAGE_ROOT, "scripts", "elstat.sh")
ALIP_SCRIPT             = Path(PACKAGE_ROOT, "scripts", "alip.sh")
CONFIG_ALIP             = Path(PACKAGE_ROOT, "scripts", "config")
MAX_ALIP_TIME           = 3600

MAX_RUNNING_AIM         = 4
MAX_AIM_TIME            = 3600 * 4 # in seconds

SCHEDULER               = "slurm" # Options: "slurm", "local", "pbs"
PARTITION               = "q_kchfo"
GAUSSIAN_NUM_CORES   = 4
MEMORY                  = 2000 # in MB   

NUMBER_OF_CORES_AIM     = 4

USER                    = "heiclj"