#!/bin/bash
# Starts irace (needs R + the irace package; if missing, run ./setup_irace_env.sh first).
#   ./run_irace.sh                  # uses irace/scenario.txt
#   ./run_irace.sh --parallel 15    # command-line options are passed straight to irace
#   IRACE_ENV=/path/to/env ./run_irace.sh   # another R environment that contains bin/Rscript
# Output: irace/irace_stdout.txt (full log), irace/irace.Rdata.  When it has finished, extract the best parameters with:
#   bin/llrp_tools irace-flags --from-log irace/irace_stdout.txt --out irace/best.flags
#   FLAGS_FILE=irace/best.flags FAMILY=all ./run_config.sh tuned
HERE=$(cd "$(dirname "$0")" && pwd)
# data integrity: do not start if the Tuzun coordinates are truncated to integers
[ -x "$HERE/check_inst_data.sh" ] && { "$HERE/check_inst_data.sh" || exit 1; }
# R environment: IRACE_ENV, or an 'irace' environment created by setup_irace_env.sh / conda is found automatically (put in front of the system Rscript)
for d in "${IRACE_ENV:-}" "$HOME/micromamba_root/envs/irace" "$HOME/miniconda3/envs/irace" "$HOME/anaconda3/envs/irace"; do
  if [ -n "$d" ] && [ -x "$d/bin/Rscript" ]; then export PATH="$d/bin:$PATH"; echo "R environment: $d"; break; fi
done
cd "$HERE/irace" || exit 1
if command -v Rscript >/dev/null 2>&1 && ! Rscript -e 'invisible(0)' >/dev/null 2>&1; then
  echo "Rscript does not work ($(command -v Rscript)); the system R may be broken (e.g. a missing shared library).  Fix:  ./setup_irace_env.sh" >&2; exit 1
fi
IRACE=${IRACE:-$(command -v irace)}
if [ -z "$IRACE" ] && command -v Rscript >/dev/null 2>&1; then IRACE=$(Rscript -e 'cat(system.file("bin", "irace", package = "irace"))' 2>/dev/null); fi
[ -n "$IRACE" ] && [ -x "$IRACE" ] || { echo "irace not found.  Install it with ./setup_irace_env.sh   or   IRACE=/path/to/irace ./run_irace.sh"; exit 1; }
echo "irace: $IRACE ($("$IRACE" --version 2>&1 | head -1))"
"$IRACE" --scenario scenario.txt "$@" 2>&1 | tee irace_stdout.txt
exit ${PIPESTATUS[0]}
