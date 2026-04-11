from string import Template


spust_g16_script = Template("""#!/bin/bash
#SBATCH -c ${num_cpus}
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -J ${job_name}
#SBATCH --mem=${memory}mb
#SBATCH -w ${node}
#SBATCH -p ${partition}

G16_DIR="g16"
g16root=/opt/QChem
mkdir -p /scratch/heiclj
export GAUSS_SCRDIR=/scratch/heiclj
export LD_LIBRARY_PATH="{$$g16root/g16}:$${LD_LIBRARY_PATH}"
. $$g16root/g16/bsd/g16.profile

g16 $$1
""")

lanl_header = Template("%mem=${memory}MB\n%nprocshared=${num_cpus}\n#p opt hf lanl1mb\n\n${job_description}\n\n${charge} ${mult}\n")
dz_header =   Template("""%mem=${memory}MB
                       %nproc=${num_cpus}
                       %%chk=${check_file}
                       #p B3LYP/gen Opt Freq pseudo=cards EmpiricalDispersion=GD3BJ SCRF=(COSMO)
                        
                       ${job_description}
                       
                       ${charge} ${mult}
                       """)

cube_header = Template("""--Link1--
                       %mem=${memory}MB
                       %nproc=${num_cpus}
                       %%chk=${check_file}
                       #p B3LYP/gen pseudo=cards EmpiricalDispersion=GD3BJ geom=check SCRF=(COSMO) pop=(nboread) cube=density cube=potential
                        
                       ${job_description}

                       ${charge} ${mult}
                       """)