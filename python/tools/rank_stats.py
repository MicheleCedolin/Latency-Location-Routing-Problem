#!/usr/bin/env python3
"""Ranking and significance tests for a finished campaign (standard library only, no numpy/scipy).

    python3 tools/rank_stats.py --report analysis/phaseA_P50_120s_30seeds/polish_vnd_common5/polished_report.csv \
            --out analysis/phaseA_P50_120s_30seeds/polish_vnd_common5/rank
    python3 tools/rank_stats.py --report analysis/phaseA_P50_120s_30seeds/report.csv --out analysis/phaseA_P50_120s_30seeds/rank_phaseA

Input: `report.csv` (collect.py) -> stage "before" only, or `polished_report.csv` (polish_report.py) -> stages "before" and "after".
Method label = heuristic, plus "+<local_search>" when the method has a native local search. One report must hold one configuration per
(instance, method, seed); a duplicate means two campaigns were mixed and the tool stops.

What is computed, per stage (before / after the common local search)
  * per-instance mean gap (%) of every method over its seeds; mean rank over the instances (rank 1 = smallest gap, ties averaged)
  * Friedman test over the instances (tie-corrected chi-square) and the Iman-Davenport F version
  * Nemenyi critical distance (alpha 0.05): methods whose mean rank is within CD of the best are marked in `best_group`
  * for every instance and pair of methods, a two-sided Mann-Whitney U test over the seeds (normal approximation with tie and continuity
    correction), Holm-corrected within the instance; `pairwise_wins_<stage>.csv` counts, for every ordered pair, the instances where the row
    method is significantly better; `rank_summary_<stage>.csv` totals significant wins / losses per method (sig_wins, sig_losses, net)
  * Kendall tau-b between the "before" and "after" rankings
Why two kinds of tests: with only a handful of instances the Friedman/Nemenyi test over instance means has little power for 100+ pairs,
whereas the per-instance Mann-Whitney test uses all seeds of one instance. Report both and say which one a statement rests on.
Distribution functions are implemented here (incomplete gamma / beta); the Nemenyi q values are tabulated (studentized range / sqrt 2).
"""
from __future__ import annotations
import argparse, csv, itertools, math, pathlib, sys
from collections import defaultdict

# q_alpha = studentized-range critical value / sqrt(2), infinite df, k = 2..30 (alpha 0.05)
Q05 = {2: 1.9600, 3: 2.3437, 4: 2.5690, 5: 2.7278, 6: 2.8497, 7: 2.9483, 8: 3.0309, 9: 3.1017, 10: 3.1637, 11: 3.2187,
       12: 3.2680, 13: 3.3127, 14: 3.3536, 15: 3.3912, 16: 3.4260, 17: 3.4584, 18: 3.4887, 19: 3.5171, 20: 3.5438,
       21: 3.5690, 22: 3.5929, 23: 3.6156, 24: 3.6373, 25: 3.6579, 26: 3.6776, 27: 3.6964, 28: 3.7145, 29: 3.7319,
       30: 3.7486}


# ---------------------------------------------------------------- distributions
def _gammaincc(a, x):
    """Regularised upper incomplete gamma Q(a, x)."""
    if x <= 0: return 1.0
    if x < a + 1:  # series for P
        term = s = 1.0 / a; ap = a
        for _ in range(10000):
            ap += 1; term *= x / ap; s += term
            if abs(term) < abs(s) * 1e-16: break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    b = x + 1 - a; c = 1e300; d = 1 / b; h = d  # continued fraction for Q
    for i in range(1, 10000):
        an = -i * (i - a); b += 2
        d = an * d + b; d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c; c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d; delta = d * c; h *= delta
        if abs(delta - 1) < 1e-16: break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_sf(x, df): return _gammaincc(df / 2.0, x / 2.0)


def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0; d = 1 - qab * x / qap; d = 1e-300 if abs(d) < 1e-300 else d; d = 1 / d; h = d
    for m in range(1, 10000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1e-300 if abs(d) < 1e-300 else d
        c = 1 + aa / c; c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1e-300 if abs(d) < 1e-300 else d
        c = 1 + aa / c; c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d; delta = d * c; h *= delta
        if abs(delta - 1) < 1e-16: break
    return h


def betai(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2): return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def f_sf(F, d1, d2): return betai(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * F)) if F > 0 else 1.0


def norm_sf(z): return 0.5 * math.erfc(z / math.sqrt(2))


# ---------------------------------------------------------------- statistics
def avg_ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i]); ranks = [0.0] * len(vals); i = 0; ties = []
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]: j += 1
        r = (i + j) / 2.0 + 1
        for t in range(i, j + 1): ranks[order[t]] = r
        if j > i: ties.append(j - i + 1)
        i = j + 1
    return ranks, ties


def friedman(M):
    """M: N rows (instances) x k columns (methods). Returns mean ranks, chi2 (tie corrected), p, Iman-Davenport F, p_F."""
    N, k = len(M), len(M[0]); R = [0.0] * k; tie_sum = 0
    for row in M:
        r, ties = avg_ranks(row)
        for j in range(k): R[j] += r[j]
        tie_sum += sum(t ** 3 - t for t in ties)
    mean_r = [x / N for x in R]
    chi = 12.0 * N / (k * (k + 1)) * (sum(m * m for m in mean_r) - k * (k + 1) ** 2 / 4.0)
    corr = 1 - tie_sum / (N * k * (k * k - 1.0))
    chi = chi / corr if corr > 0 else float('nan')
    p = chi2_sf(chi, k - 1)
    den = N * (k - 1) - chi
    F = (N - 1) * chi / den if den > 0 else float('inf')
    pF = f_sf(F, k - 1, (k - 1) * (N - 1)) if math.isfinite(F) else 0.0
    return mean_r, chi, p, F, pF


def mannwhitney_p(x, y):
    """Two-sided Mann-Whitney U, normal approximation with tie and continuity correction (scipy's method='asymptotic')."""
    n1, n2 = len(x), len(y); n = n1 + n2
    r, ties = avg_ranks(list(x) + list(y))
    u1 = sum(r[:n1]) - n1 * (n1 + 1) / 2.0; u2 = n1 * n2 - u1
    mu = n1 * n2 / 2.0
    s2 = n1 * n2 / 12.0 * ((n + 1) - sum(t ** 3 - t for t in ties) / (n * (n - 1.0)))
    if s2 <= 0: return 1.0
    z = (max(u1, u2) - mu - 0.5) / math.sqrt(s2)
    return min(1.0, 2 * norm_sf(z))


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0.0] * len(ps); run = 0.0; m = len(ps)
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * ps[i]); adj[i] = min(1.0, run)
    return adj


def kendall_tau_b(a, b):
    n = len(a); c = d = ta = tb = 0
    for i in range(n):
        for j in range(i + 1, n):
            da, db = a[i] - a[j], b[i] - b[j]
            if da == 0 and db == 0: continue
            if da == 0: ta += 1
            elif db == 0: tb += 1
            elif (da > 0) == (db > 0): c += 1
            else: d += 1
    den = math.sqrt((c + d + ta) * (c + d + tb))
    return (c - d) / den if den else float('nan')


# ---------------------------------------------------------------- data
def label(r): return r['heuristic'] + ('+' + r['local_search'] if r.get('local_search', 'none') not in ('', 'none') else '')


def load(path, stage_cols):
    with open(path, newline='') as f: rows = list(csv.DictReader(f))
    data = {s: defaultdict(list) for s in stage_cols}; seen = set(); dup = 0
    for r in rows:
        if r.get('status') != 'ok': continue
        key = (r['instance'], label(r), r['seed'])
        if key in seen: dup += 1
        seen.add(key)
        for s, (col, need_ok) in stage_cols.items():
            if need_ok and r.get('polish_status') != 'ok': continue
            v = r.get(col)
            if v in (None, ''): continue
            data[s][(r['instance'], label(r))].append(float(v))
    if dup: sys.exit(f'ERROR: {dup} duplicate (instance, method, seed) rows: the report mixes configurations; filter it first')
    return data


def analyse(cells, stage, out, alpha=0.05):
    inst = sorted({i for i, _ in cells}); meths = sorted({m for _, m in cells})
    meths = [m for m in meths if all((i, m) in cells for i in inst)]
    dropped = sorted({m for _, m in cells} - set(meths))
    if dropped: print(f'  [{stage}] methods missing in some instance, left out: {dropped}')
    N, k = len(inst), len(meths)
    mean_gap = {(i, m): sum(cells[(i, m)]) / len(cells[(i, m)]) for i in inst for m in meths}
    M = [[mean_gap[(i, m)] for m in meths] for i in inst]
    mean_r, chi, p, F, pF = friedman(M)
    cd = Q05[k] * math.sqrt(k * (k + 1) / (6.0 * N)) if k in Q05 else float('nan')
    best_r = min(mean_r)
    order = sorted(range(k), key=lambda j: (mean_r[j], meths[j]))
    pos = {meths[j]: 1 + sum(1 for x in mean_r if x < mean_r[j] - 1e-12) for j in range(k)}   # equal mean ranks share a position
    # pairwise per instance
    wins = {(a, b): 0 for a in meths for b in meths if a != b}
    for i in inst:
        pairs = list(itertools.combinations(meths, 2)); ps = [mannwhitney_p(cells[(i, a)], cells[(i, b)]) for a, b in pairs]
        adj = holm(ps)
        for (a, b), q in zip(pairs, adj):
            if q < alpha:
                ma, mb = sum(cells[(i, a)]) / len(cells[(i, a)]), sum(cells[(i, b)]) / len(cells[(i, b)])
                ra, ties = avg_ranks(list(cells[(i, a)]) + list(cells[(i, b)]))
                better = a if sum(ra[:len(cells[(i, a)])]) / len(cells[(i, a)]) < sum(ra[len(cells[(i, a)]):]) / len(cells[(i, b)]) else b
                wins[(better, b if better == a else a)] += 1
    out.mkdir(parents=True, exist_ok=True)
    with (out / f'rank_summary_{stage}.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['position', 'method', 'mean_gap_pct', 'mean_rank', 'best_group_nemenyi', 'sig_wins', 'sig_losses', 'net'])
        for j in order:
            m = meths[j]; sw = sum(wins[(m, o)] for o in meths if o != m); sl = sum(wins[(o, m)] for o in meths if o != m)
            w.writerow([pos[m], m, round(sum(mean_gap[(i, m)] for i in inst) / N, 4), round(mean_r[j], 3),
                        'yes' if mean_r[j] - best_r < cd else 'no', sw, sl, sw - sl])
    with (out / f'pairwise_wins_{stage}.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['row_better_than_col_in_n_instances'] + [meths[j] for j in order])
        for j in order:
            a = meths[j]; w.writerow([a] + ['' if a == meths[t] else wins[(a, meths[t])] for t in order])
    (out / f'friedman_{stage}.txt').write_text(
        f'stage={stage}\ninstances N={N}\nmethods k={k}\nchi2_F (tie corrected)={chi:.3f}  df={k - 1}  p={p:.3e}\n'
        f'Iman-Davenport F={F:.3f}  df=({k - 1},{(k - 1) * (N - 1)})  p={pF:.3e}\nNemenyi CD (alpha 0.05)={cd:.3f}\n'
        f'per-instance Mann-Whitney: two-sided, Holm within instance, alpha={alpha}; seeds per cell={min(len(v) for v in cells.values())}-{max(len(v) for v in cells.values())}\n')
    return dict(meths=meths, pos=pos, mean_r=dict(zip(meths, mean_r)), gap={m: sum(mean_gap[(i, m)] for i in inst) / N for m in meths},
                chi=chi, p=p, F=F, pF=pF, cd=cd, N=N, k=k, wins=wins, order=[meths[j] for j in order])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--report', required=True, type=pathlib.Path)
    ap.add_argument('--out', required=True, type=pathlib.Path)
    ap.add_argument('--alpha', type=float, default=0.05)
    ap.add_argument('--exclude', default='', help='comma separated method labels to leave out, e.g. rkrs,de')
    a = ap.parse_args()
    header = next(csv.reader(open(a.report, newline='')))
    # in a polished report both stages use exactly the runs that were polished (matters when --seeds polished only a subset)
    polished = 'gap_polished_pct' in header
    stages = {'before': ('gap_pct', polished)}
    if polished: stages['after'] = ('gap_polished_pct', True)
    data = load(a.report, stages)
    ex = {x.strip() for x in a.exclude.split(',') if x.strip()}
    res = {}
    for s in stages:
        cells = {k: v for k, v in data[s].items() if k[1] not in ex}
        if not cells: sys.exit(f'ERROR: no data for stage {s}')
        print(f'stage {s}: {len(cells)} instance x method cells')
        res[s] = analyse(cells, s, a.out, a.alpha)
    md = [f'# Ranking report\n\nsource: `{a.report}`\n']
    for s, r in res.items():
        md.append(f'\n## Stage: {s}\n\nFriedman chi2 = {r["chi"]:.1f} (df {r["k"] - 1}, p = {r["p"]:.1e}); Iman-Davenport F = {r["F"]:.1f} (p = {r["pF"]:.1e}); '
                  f'N = {r["N"]} instances, k = {r["k"]} methods; Nemenyi CD = {r["cd"]:.2f}.\n\n| pos | method | mean gap % | mean rank | in best group |\n|---|---|---|---|---|')
        best = min(r['mean_r'].values())
        for m in r['order']:
            md.append(f'| {r["pos"][m]} | {m} | {r["gap"][m]:.2f} | {r["mean_r"][m]:.2f} | {"yes" if r["mean_r"][m] - best < r["cd"] else "no"} |')
    if len(res) == 2:
        common = [m for m in res['before']['order'] if m in res['after']['pos']]
        tau = kendall_tau_b([res['before']['mean_r'][m] for m in common], [res['after']['mean_r'][m] for m in common])
        md.append(f'\nKendall tau-b between the before and after rankings: {tau:.3f} ({len(common)} methods).\n')
        with (a.out / 'rank_before_after.csv').open('w', newline='') as f:
            w = csv.writer(f); w.writerow(['method', 'gap_before_pct', 'gap_after_pct', 'rank_before', 'rank_after', 'position_before', 'position_after'])
            for m in res['after']['order']:
                if m in res['before']['pos']:
                    w.writerow([m, round(res['before']['gap'][m], 4), round(res['after']['gap'][m], 4), round(res['before']['mean_r'][m], 3),
                                round(res['after']['mean_r'][m], 3), res['before']['pos'][m], res['after']['pos'][m]])
    (a.out / 'rank_report.md').write_text('\n'.join(md) + '\n')
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
