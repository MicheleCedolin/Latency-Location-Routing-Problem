#!/bin/bash
# Submits stages to the queue (qsub).  Usage:   bash hpc/start.sh P20      |    bash hpc/start.sh P20 P50 P100 P200   (chain)
# Every stage: 6 jobs x 15 cores. Python/conda are found automatically (hpc/pyenv.sh); conda does not have to be active in your shell.
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
export SUBMIT=1 STAGES="${*:-P20}"
exec bash hpc/submit_llrp_campaign.sh
