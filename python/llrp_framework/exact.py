"""Exact reference solvers for TINY instances: ground truth to validate evaluators, operators and heuristics (not a benchmark method).

dp_optimum   : Held-Karp style dynamic program over customer subsets plus a partition dynamic program. Exact, n <= ~11,
               standard LLRP objective only (no opening or vehicle cost) and uncapacitated depots (a finite depot capacity couples
               the routes of a depot; use brute_force for that).
brute_force  : enumerates every permutation, every cut into routes and every depot assignment. Exact for every instance of this
               kit (depot capacities, opening / vehicle cost in the objective, K and p bounds); n <= 6. Used to validate dp_optimum.

K is the fleet bound (at most K non-empty routes) and p the depot bound (at most p open depots). Both are arguments because the
`Instance` of this kit does not carry them (see params.reference_kp). With free depots an "at most p" optimum equals the optimum
with exactly min(p, m) open depots, which is what the dynamic program enumerates.

Minimum-latency recursion. hp[v][T] = least latency of the part of a route that starts at v (already served at time 0) and visits
the set T afterwards:
        hp[v][0] = 0,     hp[v][T] = min over u in T of  |T| * d(v,u) + hp[u][T minus u]
(the arc v -> u delays all |T| customers that are still to be served). A route from depot d serving T costs
        h[d][T] = min over v in T of  |T| * d(d,v) + hp[v][T minus v].
The partition step then chooses at most K disjoint subsets, each served from one of the open depots.
"""
from __future__ import annotations
import itertools
from typing import List, Optional, Tuple
from .core import Instance, Route, objective

INF = float('inf')


def has_depot_cap(inst: Instance) -> bool:
    """True when a depot capacity can bind (the default 'ignore' convention sets every capacity to the total demand)."""
    tot = sum(inst.demand)
    return any(c + 1e-9 < tot for c in inst.depot_cap)


def standard_objective(inst: Instance) -> bool:
    """True for the benchmark objective: the sum of arrival times only."""
    return inst.vehicle_cost == 0 and not any(inst.open_cost)


def dp_optimum(inst: Instance, K: int, p: int, max_n: int = 11) -> Tuple[float, Optional[List[Route]]]:
    """(optimal objective, optimal solution), or (INF, None) when no feasible solution exists."""
    n, m = inst.n, inst.m
    if has_depot_cap(inst) or not standard_objective(inst):
        raise NotImplementedError('dp_optimum needs uncapacitated depots and the standard objective; use brute_force')
    if n > max_n:
        raise ValueError(f'dp_optimum is for tiny instances (n <= {max_n})')
    if n == 0:
        return 0.0, []
    p = min(p, m)
    full = (1 << n) - 1
    dcc, ddc = inst.dcc, inst.ddc
    size = [bin(x).count('1') for x in range(full + 1)]
    load = [0.0] * (full + 1)
    for mask in range(1, full + 1):
        low = (mask & -mask).bit_length() - 1
        load[mask] = load[mask & (mask - 1)] + inst.demand[low]

    # hp[v][T] and its argmin (v not in T)
    hp = [[INF] * (full + 1) for _ in range(n)]
    ha = [[-1] * (full + 1) for _ in range(n)]
    for v in range(n):
        hp[v][0] = 0.0
    for T in range(1, full + 1):
        k = size[T]
        for v in range(n):
            if T >> v & 1:
                continue
            best, arg, rem = INF, -1, T
            while rem:
                lb = rem & -rem
                u = lb.bit_length() - 1
                rem ^= lb
                val = k * dcc[v][u] + hp[u][T ^ lb]
                if val < best:
                    best, arg = val, u
            hp[v][T], ha[v][T] = best, arg

    # h[d][T] and its first customer, for sets that fit one vehicle
    h = [[INF] * (full + 1) for _ in range(m)]
    first = [[-1] * (full + 1) for _ in range(m)]
    for d in range(m):
        h[d][0] = 0.0
        for T in range(1, full + 1):
            if load[T] > inst.Q + 1e-9:
                continue
            k = size[T]
            best, arg, rem = INF, -1, T
            while rem:
                lb = rem & -rem
                v = lb.bit_length() - 1
                rem ^= lb
                val = k * ddc[d][v] + hp[v][T ^ lb]
                if val < best:
                    best, arg = val, v
            h[d][T], first[d][T] = best, arg

    def route_seq(d: int, T: int) -> List[int]:
        v = first[d][T]
        seq, rest = [v], T ^ (1 << v)
        while rest:
            u = ha[v][rest]
            seq.append(u)
            rest ^= 1 << u
            v = u
        return seq

    best_val, best_sol = INF, None
    for S in itertools.combinations(range(m), p):
        B = [INF] * (full + 1)          # cheapest depot of S for every subset
        Bd = [-1] * (full + 1)
        for T in range(1, full + 1):
            for d in S:
                if h[d][T] < B[T]:
                    B[T], Bd[T] = h[d][T], d
        # F[r][mask] = least latency of covering `mask` with exactly r routes of the sets B
        F = [[INF] * (full + 1) for _ in range(K + 1)]
        choice = [[0] * (full + 1) for _ in range(K + 1)]
        F[0][0] = 0.0
        for r in range(1, K + 1):
            Fr, Fp, Cr = F[r], F[r - 1], choice[r]
            Fr[0] = 0.0
            for mask in range(1, full + 1):
                low = mask & -mask
                rest = mask ^ low
                sub, best, arg = rest, INF, 0
                while True:
                    T = sub | low               # the set containing the lowest customer of `mask`
                    b = B[T]
                    if b < INF:
                        val = b + Fp[mask ^ T]
                        if val < best:
                            best, arg = val, T
                    if sub == 0:
                        break
                    sub = (sub - 1) & rest
                Fr[mask], Cr[mask] = best, arg
        rbest = min(range(1, K + 1), key=lambda r: F[r][full]) if K >= 1 else 0
        val = F[rbest][full] if K >= 1 else INF
        if val < best_val - 1e-12:
            routes: List[Route] = []
            mask, r = full, rbest
            while mask:
                T = choice[r][mask]
                d = Bd[T]
                routes.append(Route(d, route_seq(d, T), load[T]))
                mask ^= T
                r -= 1
            best_val, best_sol = val, routes
    return best_val, best_sol


def brute_force(inst: Instance, K: int, p: int, max_n: int = 6) -> Tuple[float, Optional[List[Route]]]:
    """Complete enumeration; handles every constraint of this kit (depot capacity, opening / vehicle cost, K, p)."""
    n, m = inst.n, inst.m
    if n > max_n:
        raise ValueError(f'brute_force is for n <= {max_n}')
    if n == 0:
        return objective(inst, []), []
    best_val, best_sol = INF, None
    q_max = inst.Q + 1e-9
    capped = has_depot_cap(inst)
    for perm in itertools.permutations(range(n)):
        for cut in range(1 << (n - 1)):
            routes, cur = [], [perm[0]]
            for pos in range(1, n):
                if cut >> (pos - 1) & 1:
                    routes.append(cur)
                    cur = [perm[pos]]
                else:
                    cur.append(perm[pos])
            routes.append(cur)
            if len(routes) > K:
                continue
            lds = [sum(inst.demand[c] for c in r) for r in routes]
            if any(l > q_max for l in lds):
                continue
            for deps in itertools.product(range(m), repeat=len(routes)):
                if len(set(deps)) > p:
                    continue
                if capped:
                    dl = [0.0] * m
                    for dd, l in zip(deps, lds):
                        dl[dd] += l
                    if any(dl[d] > inst.depot_cap[d] + 1e-9 for d in range(m)):
                        continue
                sol = [Route(dd, list(r), l) for dd, r, l in zip(deps, routes, lds)]
                val = objective(inst, sol)
                if val < best_val - 1e-12:
                    best_val, best_sol = val, sol
    return best_val, best_sol


def random_instance(seed: int, n: int = 6, m: int = 3, q_tightness: float = 0.5, depot_cap: bool = False,
                    open_cost: bool = False, vehicle_cost: float = 0.0) -> Instance:
    """Small random Euclidean instance in the kit's Instance format (for tests and validation runs).

    Integer demands 1..9; the vehicle capacity is `q_tightness` times the total demand but at least the largest demand, so a feasible
    solution needs about 1/q_tightness routes. depot_cap=True gives every depot about 60 % of the total demand (binding);
    open_cost / vehicle_cost put those costs into the objective (only brute_force supports them).
    """
    import math
    import random
    rng = random.Random(seed)
    cust = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]
    dep = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(m)]
    demand = [float(rng.randint(1, 9)) for _ in range(n)]
    tot = sum(demand)
    Q = float(max(max(demand), math.ceil(q_tightness * tot)))
    dcc = [[math.hypot(a[0] - b[0], a[1] - b[1]) for b in cust] for a in cust]
    ddc = [[math.hypot(a[0] - b[0], a[1] - b[1]) for b in cust] for a in dep]
    cap = [float(math.ceil(0.6 * tot))] * m if depot_cap else [float(tot)] * m
    oc = [float(rng.randint(5, 30)) for _ in range(m)] if open_cost else [0.0] * m
    return Instance(n, m, cust, dep, demand, Q, dcc, ddc, cap, oc, float(vehicle_cost), 'random',
                    'real_euclidean', 'llrp', list(oc), list(cap), 'enforce' if depot_cap else 'ignore')
