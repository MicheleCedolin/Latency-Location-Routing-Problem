#!/bin/bash
# Data-integrity guard: are the Tuzun-Burke coordinates in inst/tuzun/*.inst RAW (decimal, e.g. 35.700001) or truncated to integers (35.0)?
# Runs on truncated files give meaningless gaps to the BKS (negative gaps appear).
#   ./check_inst_data.sh            # exit code 1 if there is a problem;  SKIP_DATA_CHECK=1 skips the check (not recommended)
# run_irace.sh, run_config.sh and run_final.sh call it automatically.  It only looks at inst/tuzun/ (the Prins and Barreto data are sound).
HERE=$(cd "$(dirname "$0")" && pwd)
[ "${SKIP_DATA_CHECK:-0}" = 1 ] && exit 0
ROOT=${INSTROOT:-$HERE/inst}
bad=0; n=0
for f in "$ROOT"/tuzun/*.inst; do
  [ -e "$f" ] || continue
  n=$((n+1))
  # after the 'depots' line, at least one coordinate in the first two fields must have a non-zero fractional digit
  if ! awk '/^depots/{c=1;next} c && ($1 ~ /\.[0-9]*[1-9]/ || $2 ~ /\.[0-9]*[1-9]/){ok=1; exit} END{exit !ok}' "$f"; then
    echo "TRUNCATED COORDINATES (integers): $f" >&2; bad=$((bad+1))
  fi
done
if [ "$bad" -gt 0 ]; then
  echo "ERROR: $bad / $n Tuzun instances contain coordinates truncated to integers.  Restore inst/tuzun/*.inst from the repository" >&2
  echo "       (git checkout -- inst/tuzun); the full-precision coordinates are also in ../python/data/T/*.dat." >&2
  exit 1
fi
exit 0
