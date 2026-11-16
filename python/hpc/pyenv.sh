# Sourced by the launcher scripts (never run by hand): makes sure a Python >= 3.10 is usable ($PYTHON, default python3).
# Does nothing when python3 is already fine. Otherwise, in this order:
#   1. looks for a ready interpreter in conda-style folders WITHOUT needing the `conda` command (a broken or incomplete conda install is common):
#      $LLRP_PYTHON, $CONDA_ENV, then ~/{miniconda3,anaconda3,miniforge3,mambaforge}/{envs/*,.}/bin/python3, ~/.conda/envs/*, ~/*/envs/*, /opt/*conda*/...
#      The first one with Python >= 3.10 is used (PYTHON is set to its full path and its folder goes to the front of PATH);
#   2. else sources conda.sh and activates llrp_env, clrp_env, base or any other environment with Python >= 3.10.
# This is why the job scripts need neither `conda activate` in your shell nor `qsub -V`.
_llrp_py_ok () {
    command -v "${PYTHON:-python3}" > /dev/null 2>&1 && \
    "${PYTHON:-python3}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' > /dev/null 2>&1
}
_llrp_try_python () {   # $1 = interpreter path
    [ -x "$1" ] || return 1
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' > /dev/null 2>&1 || return 1
    PATH="$(dirname "$1"):$PATH"; export PATH; PYTHON="$1"; export PYTHON
    echo "pyenv: using $1 ($("$1" -V 2>&1))"
}
if ! _llrp_py_ok; then
    _llrp_name="$(basename "${PYTHON:-python3}")"
    _llrp_found=0
    [ -n "${LLRP_PYTHON:-}" ] && _llrp_try_python "$LLRP_PYTHON" && _llrp_found=1
    if [ "$_llrp_found" = 0 ]; then
        for _llrp_p in \
            "$HOME/miniconda3/envs/${CONDA_ENV:-_none_}/bin/$_llrp_name" "$HOME/anaconda3/envs/${CONDA_ENV:-_none_}/bin/$_llrp_name" \
            "$HOME"/miniconda3/envs/llrp_env/bin/"$_llrp_name" "$HOME"/miniconda3/envs/clrp_env/bin/"$_llrp_name" \
            "$HOME"/miniconda3/bin/"$_llrp_name" "$HOME"/miniconda3/envs/*/bin/"$_llrp_name" \
            "$HOME"/anaconda3/bin/"$_llrp_name" "$HOME"/anaconda3/envs/*/bin/"$_llrp_name" \
            "$HOME"/miniforge3/bin/"$_llrp_name" "$HOME"/miniforge3/envs/*/bin/"$_llrp_name" \
            "$HOME"/mambaforge/bin/"$_llrp_name" "$HOME"/mambaforge/envs/*/bin/"$_llrp_name" \
            "$HOME"/.conda/envs/*/bin/"$_llrp_name" "$HOME"/*/envs/*/bin/"$_llrp_name" \
            /opt/*conda*/bin/"$_llrp_name" /opt/*conda*/envs/*/bin/"$_llrp_name"; do
            _llrp_try_python "$_llrp_p" && { _llrp_found=1; break; }
        done
    fi
    if [ "$_llrp_found" = 0 ]; then
        _llrp_u=0; case $- in *u*) _llrp_u=1; set +u ;; esac       # conda's own scripts are not `set -u` clean
        for _llrp_sh in "${CONDA_SH:-}" "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/anaconda3/etc/profile.d/conda.sh" \
                        "$HOME/miniforge3/etc/profile.d/conda.sh" /opt/*conda*/etc/profile.d/conda.sh; do
            [ -n "$_llrp_sh" ] && [ -f "$_llrp_sh" ] || continue
            . "$_llrp_sh" > /dev/null 2>&1 || continue
            _llrp_envs="${CONDA_ENV:-} llrp_env clrp_env base $(conda env list 2>/dev/null | awk '!/^#/ && NF {print $1}' | tr '\n' ' ')"
            for _llrp_e in $_llrp_envs; do
                conda activate "$_llrp_e" > /dev/null 2>&1 && _llrp_py_ok && { echo "pyenv: conda environment '$_llrp_e' ($("${PYTHON:-python3}" -V 2>&1))"; break 2; }
            done
        done
        [ "$_llrp_u" = 1 ] && set -u
    fi
    unset _llrp_name _llrp_found _llrp_p _llrp_u _llrp_sh _llrp_envs _llrp_e
fi
if ! _llrp_py_ok; then
    echo "ERROR: no Python >= 3.10 found (looked in ~/miniconda3, ~/anaconda3, ~/miniforge3, ~/.conda, /opt/*conda*). Set LLRP_PYTHON=<full path of python3> or CONDA_SH=<path>/etc/profile.d/conda.sh CONDA_ENV=<name>."
    return 2 2> /dev/null || exit 2
fi
