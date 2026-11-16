# Edge structure of the final solutions versus the published solutions of Zou et al.

Neighbour rank of an edge = min over its two ends of the position of the other end in the end's distance-ordered customer list. delta* = largest rank in a solution. Groups: `<alg>_best` = best run of each instance, `<alg>_all` = all runs. Paired with Zou on the common instances.

| group | instances | rank>10 % | rank>20 % | rank>30 % | delta* mean | delta* median | Zou rank>20 % (same instances) | Zou delta* mean |
|---|---|---|---|---|---|---|---|---|
| B1_all | 53 | 4.00 | 1.32 | 0.54 | 25.0 | 22 | 1.32 | 25.0 |
| B1_best | 53 | 3.90 | 1.30 | 0.52 | 24.3 | 22 | 1.32 | 25.0 |
| ext10_all | 54 | 4.20 | 1.38 | 0.57 | 26.0 | 25 | 1.30 | 24.7 |
| ext10_best | 54 | 4.03 | 1.33 | 0.52 | 24.9 | 24 | 1.30 | 24.7 |
| tuned_all | 72 | 3.64 | 1.13 | 0.48 | 22.9 | 20 | 0.97 | 20.7 |
| tuned_best | 72 | 3.23 | 1.04 | 0.45 | 21.0 | 17 | 0.97 | 20.7 |

## Zou edges (directed) found in our runs

| algorithm | instances | Zou edges | in the best run % | in at least one run % | in no run | of those: rank>20 % | found edges: rank>20 % |
|---|---|---|---|---|---|---|---|
| B1 | 53 | 6598 | 91.9 | 99.56 | 29 | 6.9 | 1.29 |
| ext10 | 54 | 6664 | 85.6 | 99.40 | 40 | 17.5 | 1.21 |
| tuned | 72 | 7226 | 79.2 | 98.89 | 80 | 11.2 | 1.09 |

## Candidate edge sets (out/cand_ext10): coverage of the Zou edges versus size (undirected pairs per customer)

| candidate set | coverage % | size | coverage n=200 % |
|---|---|---|---|
| knn-5 | 89.08 | 3.1 | 87.81 |
| knn-10 | 96.27 | 6.0 | 95.80 |
| knn-15 | 97.87 | 8.9 | 97.81 |
| knn-20 | 98.70 | 11.8 | 98.85 |
| knn-30 | 99.42 | 17.5 | 99.47 |
| union-1 | 80.35 | 0.9 | 68.68 |
| union-1+knn-5 | 95.25 | 3.2 | 92.87 |
| union-1+knn-10 | 98.23 | 6.1 | 97.19 |
| union-3 | 92.98 | 1.2 | 88.22 |
| union-3+knn-5 | 97.65 | 3.2 | 96.05 |
| union-3+knn-10 | 99.06 | 6.1 | 98.34 |
| union-5 | 95.80 | 1.3 | 92.98 |
| union-5+knn-5 | 98.35 | 3.3 | 97.21 |
| union-5+knn-10 | 99.35 | 6.1 | 98.81 |
| union-10 | 98.27 | 1.5 | 96.94 |
| union-10+knn-5 | 99.06 | 3.4 | 98.35 |
| union-10+knn-10 | 99.62 | 6.2 | 99.25 |
| union-30 | 99.56 | 1.9 | 99.15 |
| union-30+knn-5 | 99.67 | 3.6 | 99.36 |
| union-30+knn-10 | 99.85 | 6.3 | 99.63 |

## Candidate edge sets (out/cand_B1): coverage of the Zou edges versus size (undirected pairs per customer)

| candidate set | coverage % | size | coverage n=200 % |
|---|---|---|---|
| knn-5 | 89.05 | 3.1 | 87.81 |
| knn-10 | 96.20 | 6.0 | 95.80 |
| knn-15 | 97.83 | 8.9 | 97.81 |
| knn-20 | 98.68 | 11.8 | 98.85 |
| knn-30 | 99.41 | 17.5 | 99.47 |
| union-1 | 90.17 | 0.9 | 81.90 |
| union-1+knn-5 | 97.60 | 3.2 | 95.61 |
| union-1+knn-10 | 99.15 | 6.1 | 98.40 |
| union-3 | 96.68 | 1.0 | 93.26 |
| union-3+knn-5 | 99.02 | 3.2 | 97.80 |
| union-3+knn-10 | 99.63 | 6.1 | 99.12 |
| union-5 | 97.88 | 1.1 | 95.94 |
| union-5+knn-5 | 99.38 | 3.2 | 98.53 |
| union-5+knn-10 | 99.78 | 6.1 | 99.40 |
| union-10 | 99.16 | 1.2 | 97.96 |
| union-10+knn-5 | 99.68 | 3.3 | 99.18 |
| union-10+knn-10 | 99.88 | 6.1 | 99.65 |
| union-30 | 99.67 | 1.3 | 99.24 |
| union-30+knn-5 | 99.81 | 3.3 | 99.54 |
| union-30+knn-10 | 99.93 | 6.1 | 99.77 |
