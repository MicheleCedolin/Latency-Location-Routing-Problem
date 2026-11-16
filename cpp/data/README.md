# `data/` — measurements and validation tables used by the tools

| File | Content |
|---|---|
| `timing_probe_20it.tsv` | CPU time of 20 GRASP iterations on every one of the 76 instances (full pool + SO, 2.1 GHz Xeon, single process, seed 0). `run_ablation.sh` and `llrp_tools irace-gen` use it for time estimates. |
| `pilot_stall_calibration/` | 10 Barreto instances x seeds 0..3 x 600 iterations, `--ops full --so` (no stall rule). Analyse with `bin/llrp_tools calibrate data/pilot_stall_calibration`. |
| `pilot_ils_probe/results.csv` | Mi134-8 and Ch75-10, seeds 0..1, equal 30 s CPU budget, `--ops full --so`, `--ils {0,10,30}`. Indicative only (2 seeds). |
| `inst_validation_published_solutions.txt` | Data validation. For each instance the cost of the published solution (Zou et al. 2024, `solutions/*.txt`) is recomputed on (i) the raw coordinates of the original instance files and (ii) the `.inst` file of this repository and compared with the published best value. |

## Data validation

* The published solution files of Zou et al. reproduce the published best values exactly on the kit data for **Prins 30/30** and **Barreto 9/9** (Or117-14 has an empty solution file) and for **33/36 Tüzün–Burke** instances.
* Three Tüzün–Burke solution files are defective and cannot validate the data (they do not depend on the coordinates): `P112222-20` (the file covers 90 of 100 customers), `P122122-20` (the file evaluates to 3705.739 while the published best is 3705.59, which looks like an older best-known solution) and `P131122-20` (the file evaluates to 38761.9 against a published 4870.82).
* The Tüzün–Burke files in `../inst/tuzun/` carry the full-precision decimal coordinates; `../check_inst_data.sh` checks this before every run.
* The consolidated best-known values with their verification status are in [`../../bks/LLRP_BKS.csv`](../../bks/LLRP_BKS.csv).
