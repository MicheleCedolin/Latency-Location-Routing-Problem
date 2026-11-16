"""Machine-readable description of a solution: which depots are open and which routes are driven.

All indices are 0-based and follow the order of the .dat file (customers 0..n-1, depots 0..m-1).
"""
from .core import route_distance


def _routes(sol):
    rs = [r for r in sol if r.seq]
    rs.sort(key=lambda r: (r.depot, r.seq[0]))
    return rs


def route_cost(inst, route):
    """LLRP route cost: the route latency (sum of customer arrival times, no return leg) plus the vehicle fixed cost (0 in LLRP)."""
    return route_distance(inst, route) + inst.vehicle_cost


def solution_record(inst, sol):
    """open_depots (sorted), routes (depot, customers in visiting order, load, cost) and per-depot totals."""
    routes, depots = [], {}
    for r in _routes(sol):
        cost = route_cost(inst, r)
        routes.append(dict(depot=r.depot, customers=list(r.seq), load=r.load, cost=cost))
        d = depots.setdefault(r.depot, dict(depot=r.depot, routes=0, customers=0, load=0.0, cost=0.0, opening_cost=inst.open_cost[r.depot], capacity=inst.depot_cap[r.depot]))
        d['routes'] += 1
        d['customers'] += len(r.seq)
        d['load'] += r.load
        d['cost'] += cost
    return dict(open_depots=sorted(depots), routes=routes, depots=[depots[k] for k in sorted(depots)])


def routes_compact(sol):
    """One text cell per solution: 'd1:3-0-11-19|d1:17-1-16-8|d3:...' (depot index, customers in visiting order)."""
    return '|'.join(f'd{r.depot}:' + '-'.join(map(str, r.seq)) for r in _routes(sol))
