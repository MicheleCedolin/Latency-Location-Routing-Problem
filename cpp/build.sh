#!/bin/bash
# Builds the solver (bin/llrp_fast) and the analysis/orchestration tools (bin/llrp_tools).
# Requires g++ >= 4.8 (C++11).  Deliberately NO -ffp-contract and NO -march=native:
# floating-point results must stay identical across machines.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HERE/bin"
CXX=${CXX:-g++}
"$CXX" -O3 -std=c++11 -ffp-contract=off -o "$HERE/bin/llrp_fast" "$HERE/src/llrp_fast.cpp"
"$CXX" -O2 -std=c++11 -o "$HERE/bin/llrp_tools" "$HERE/src/llrp_tools.cpp"
echo "built: $HERE/bin/llrp_fast  $HERE/bin/llrp_tools   ($("$CXX" --version | head -1))"
[ -s "$HERE/manifest.tsv" ] || "$HERE/bin/llrp_tools" manifest "$HERE/inst" --out "$HERE/manifest.tsv" > /dev/null
