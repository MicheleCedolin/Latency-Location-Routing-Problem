#!/bin/bash
# Installs R + irace without root: micromamba + conda-forge.  Independent of a broken system R.
#   ./setup_irace_env.sh                       # $HOME/micromamba_root/envs/irace  (about 1-1.5 GB, 3-10 min)
#   ROOT_PREFIX=/other/path ./setup_irace_env.sh
# Afterwards run_irace.sh finds this environment by itself (no PATH changes needed).
# Note: the conda solver respects the machine's glibc version (CentOS 7 = 2.17); it does not pick incompatible packages and fails if no solution exists.
ROOT_PREFIX=${ROOT_PREFIX:-$HOME/micromamba_root}
ENVN=${ENVN:-irace}
MM=$ROOT_PREFIX/bin/micromamba
mkdir -p "$ROOT_PREFIX" || exit 1
echo "glibc : $(ldd --version 2>&1 | head -1)"
echo "disk  : $(df -h "$ROOT_PREFIX" | tail -1)"
if [ ! -x "$MM" ]; then
  echo "downloading micromamba ..."
  curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$ROOT_PREFIX" bin/micromamba \
    || { echo "ERROR: could not download micromamba (micro.mamba.pm).  Fallback: install Miniconda (repo.anaconda.com/miniconda) and run 'conda create -n irace -c conda-forge r-base r-irace'."; exit 1; }
fi
"$MM" --version || exit 1
if [ ! -x "$ROOT_PREFIX/envs/$ENVN/bin/Rscript" ]; then
  "$MM" create -y -r "$ROOT_PREFIX" -n "$ENVN" -c conda-forge --override-channels r-base r-irace \
    || { echo "ERROR: could not create the environment (see the solver message above)."; exit 1; }
fi
export PATH="$ROOT_PREFIX/envs/$ENVN/bin:$PATH"
Rscript -e 'library(irace); cat("irace", as.character(packageVersion("irace")), "|", R.version.string, "\n")' || exit 1
echo "OK: $ROOT_PREFIX/envs/$ENVN"
