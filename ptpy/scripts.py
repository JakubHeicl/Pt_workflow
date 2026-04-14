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
                                                     
formchk ${chk_file}
""")

aim_analysis_script = Template("/bin/bash -lc 'cd ${folder} && nohup /Applications/QChem/AIMAll/aimqb.app/Contents/MacOS/aimqb -nogui -nproc=${num_cpus} -skipint=true ${fchk_file} > output.log 2>&1 </dev/null &'")

lanl_header = Template("""%mem=${memory}MB
%nprocshared=${num_cpus}
%chk=${check_file}
#p opt hf lanl1mb

${job_description}

${charge} ${mult}
""")

dz_header =   Template("""%mem=${memory}MB
%nprocshared=${num_cpus}
%chk=${check_file}
#p B3LYP/gen Opt Freq pseudo=cards EmpiricalDispersion=GD3BJ SCRF=(COSMO)

${job_description}

${charge} ${mult}
""")

cube_header = Template("""--Link1--
%mem=${memory}MB
%nprocshared=${num_cpus}
%chk=${check_file}
#p B3LYP/gen pseudo=cards EmpiricalDispersion=GD3BJ geom=check SCRF=(COSMO) pop=(nboread) cube=density cube=potential

${job_description}

${charge} ${mult}
""")