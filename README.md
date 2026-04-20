# PtPy

PtPy is a workflow helper for preparing, submitting, and checking quantum-chemistry calculations for platinum complexes. It reads local `.xyz` or Gaussian `.com` inputs, creates run folders, stores workflow state as JSON, and coordinates calculation steps through SLURM, SSH, and `rsync`.

The default workflow is:

1. `lanl_opt` - Gaussian LANL1MB optimization.
2. `dz_opt` - Gaussian B3LYP/gen optimization, frequencies, and density/potential cube generation.
3. `aim_analysis` - remote AIMAll analysis from the `.fchk` file.
4. `ligand_energies_calculation` - ligand energy calculations using detected or manually reviewed ligands.
5. `alip_elstat_calculation` - remote ALIP/ELSTAT calculation from `.den`, `.pot`, and `.fchk` files.

## Installation

PtPy is installable from this repository through `pyproject.toml`.

For a normal local install:

```powershell
python -m pip install .
```

For development, use an editable install:

```powershell
python -m pip install -e .
```

After installation, the command-line entry point is available as:

```powershell
ptpy --help
```

You can also run the package directly from the repository:

```powershell
python -m ptpy --help
```

The package configuration includes the bundled basis files in `ptpy/bases/` and helper executables/scripts in `ptpy/scripts/`.

## Requirements

Python dependencies are declared in `pyproject.toml`:

- Python 3.10 or newer.
- `numpy`
- `rdkit`

If you prefer managing scientific packages with conda, create an environment first:

```powershell
conda install -c conda-forge numpy tqdm rdkit
python -m pip install -e .
```

System/runtime tools:

- SLURM commands available in `PATH`: `sbatch`, `squeue`, `sinfo`, `scancel`.
- `ssh` and `rsync` for remote steps.
- Gaussian 16 and `formchk` on the calculation cluster.
- AIMAll on the remote host used for `aim_analysis`.
- Open Babel (`obabel`) as an optional fallback for generating structures from SMILES.

## Project Layout

```text
PtPy/
|-- input_files/          # input .xyz and .com files for the workflow
|-- input_suggestions/    # generated .com suggestions from SMILES
|-- ptpy/                 # Python package
|   |-- bases/            # basis sets and pseudopotentials
|   `-- scripts/          # ALIP/ELSTAT helper scripts and executables
|-- repository/           # JSON workflow state, created at runtime
`-- runs/                 # calculation working directories
```

The `repository/`, `runs/`, and `input_suggestions/` folders are created by `ptpy --init` or automatically during workflow execution. These paths are relative to the current working directory, so run `ptpy` from the directory where you want the workflow state and run folders to live.

## Quick Start

Initialize the working folders:

```powershell
ptpy --init
```

Place input files into `input_files/`:

- `.com` files: charge and multiplicity are read from the Gaussian input.
- `.xyz` files: PtPy asks interactively for charge and multiplicity.

Run one workflow pass:

```powershell
ptpy
```

Check workflow status:

```powershell
ptpy --status
```

Run continuously in a loop:

```powershell
ptpy --loop
```

Stop the loop from another terminal:

```powershell
ptpy --stop
```

Write logs to a file:

```powershell
ptpy --log-file ptpy.log
```

Run without confirmation prompts:

```powershell
ptpy --auto
```

`--auto` answers confirmation prompts with their default values. It cannot provide missing interactive data such as charge/multiplicity for `.xyz` inputs or manual ligand review. For fully unattended runs, prefer prepared `.com` inputs.

## Input Files

PtPy scans `input_files/` on every run and creates a workflow case for each new input file.

Supported formats:

- `.xyz` - molecular geometry; charge and multiplicity are requested interactively.
- `.com` - Gaussian input; geometry, charge, and multiplicity are parsed from the file.

The input filename without extension becomes the case name. If a case with the same name already exists in `repository/`, it is not added again.

## Generating Gaussian Inputs From SMILES

PtPy can generate Gaussian `.com` suggestions from a `.smi` file into `input_suggestions/`.

Input format:

```text
SMILES id
```

Example:

```text
[Cl][Pt]([Cl])([NH3])[NH3] mol4
```

Run:

```powershell
ptpy --suggest_from_smiles input_files/input.smi
```

Outputs:

- `input_suggestions/<id>.com`
- `input_suggestions/summary.csv`

The generator uses RDKit ETKDG/MMFF/UFF. For Pt complexes, it attempts to enforce square-planar or octahedral coordination geometry based on the number of donor atoms. If RDKit generation fails, PtPy tries `obabel --gen3d --fastest`.

## Configuration

Main configuration is currently stored in `ptpy/config.py`.

Important settings:

- `INPUT_DIR`, `REPOSITORY_DIR`, `RUNS_DIR`, `SUG_DIR` - local workflow folders.
- `SCHEDULER` - currently only SLURM is implemented.
- `PARTITION`, `GAUSSIAN_NUM_CORES`, `MEMORY`, `USER` - Gaussian job settings.
- `AIM_CLUSTER`, `AIM_REMOTE_DIR` - remote AIMAll environment.
- `ALIP_ELSTAT_CLUSTER`, `ALIP_ELSTAT_REMOTE_DIR` - remote ALIP/ELSTAT environment.
- `MAX_RUNNING_AIM`, `MAX_AIM_TIME`, `MAX_ALIP_TIME` - concurrency and timeout limits.

When developing or changing cluster settings often, use an editable install (`python -m pip install -e .`) so edits to `ptpy/config.py` are used immediately.

## Workflow State

Each case is stored as a JSON file in `repository/`. The JSON state contains the current step, status, job ID, local and remote file paths, and the last known geometry.

Step statuses:

- `pending` - the step is waiting to be prepared.
- `not_submitted` - input files are ready, but the job has not been submitted yet.
- `running` - the job is running or PtPy is waiting for remote output.
- `completed` - the step finished successfully.
- `failed` - the step failed and needs manual inspection.
- `not_sure` - PtPy cannot safely determine whether a remote step completed successfully.

## Restore And Cleanup

Use `--restore` to reset workflow state:

```powershell
ptpy --restore
```

In interactive mode, PtPy asks whether it should:

- cancel running jobs,
- remove `repository/`,
- remove `runs/`,
- clear the remote AIM folder,
- clear the remote ALIP/ELSTAT folder.

Use this command carefully. With `--auto`, confirmations use the defaults defined in code.

## Development Notes

- CLI entry point: `ptpy/__main__.py`
- Workflow orchestration: `ptpy/engine.py`
- Calculation steps: `ptpy/calculations_steps.py`
- Workflow data model: `ptpy/ir.py`
- SLURM/SSH/rsync wrapper: `ptpy/scheduler.py`
- SMILES-to-structure generation: `ptpy/smiles.py`
- Packaging metadata: `pyproject.toml`

Quick CLI check:

```powershell
ptpy --help
```
