// poolsp.hpp -- in-run route pool, exact route-order polish (Held-Karp DP) and set-partitioning (SP) recombination for llrp_fast_v7.
//
// Pool:   every route of the solutions it is shown is stored once per (depot, customer set).  Its order is replaced by the EXACT minimum-latency
//         order (open route, arrival times counted from the depot) when the route has <= DP_KMAX customers; longer routes keep the best order seen.
// SP:     for one depot set S (|S| = Ng): min sum_j c_j x_j  s.t. every customer covered exactly once, at most Nv routes, only routes with depot in S,
//         exactly Ng (or <= Ng with atmost) distinct depots in the final selection.  Only solutions with cost < UB are searched for.
//         Method: Lagrangian relaxation of the covering rows (+ the route-count row), subgradient ascent, reduced-cost fixing against UB, then a
//         depth-first exact-cover search over the surviving routes with the Lagrangian bound at every node.  The result is exact when the search
//         finishes ("complete"), otherwise the best selection found within the node / CPU limit (still a valid solution).
//         Route latencies are independent of each other, so SP over a pool is exact within the pool.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <numeric>
#include <unordered_map>
#include <vector>
#include <time.h>

namespace psp {
static int g_sg_iters = 4000, g_sg_patience = 25;   // subgradient schedule (tunable in tests)

static const int DP_KMAX = 16;
static inline double cpu_now() { timespec t; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }

struct Params {
    int n = 0, m = 0, Nv = 0, Ng = 0;
    bool atmost = false;
    const double *D = nullptr;      // (m+n)^2 distance matrix; customer c has global index m + c
    int NN = 0;
    inline double d(int i, int j) const { return D[(size_t)i * NN + j]; }
};

struct PRoute { int depot; std::vector<int> path; double lat; std::vector<uint64_t> mask; };

struct SPResult {
    bool improved = false;      // a selection with cost < UB was found
    double cost = INFINITY;     // its cost
    std::vector<int> sel;       // pool indices of the selected routes
    bool complete = false;      // search finished (proof: nothing better than the returned cost / UB exists in this sub-pool)
    bool nocover = false;       // some customer has no route with a depot in S
    double lb = -INFINITY;      // Lagrangian lower bound at the root
    long nodes = 0; int routes_in = 0, routes_kept = 0;
};

class Pool {
  public:
    Params P; int W = 0;
    std::vector<PRoute> R;
    long n_new = 0, n_hit = 0, dp_calls = 0, dp_gain = 0, dp_skipped = 0;
    long new_since_call = 0;

    explicit Pool(const Params &p) : P(p) { W = (P.n + 63) / 64; }

    double lat_of(int depot, const std::vector<int> &path) const {
        double tot = 0.0, arr = 0.0; int prev = depot;
        for (int c : path) { arr += P.d(prev, P.m + c); tot += arr; prev = P.m + c; }
        return tot;
    }
    // exact minimum-latency order (Held-Karp).  Returns the order (same customers).
    std::vector<int> dp_order(int depot, const std::vector<int> &cu) {
        const int k = (int)cu.size();
        std::vector<double> D((size_t)k * k), d0(k);
        for (int a = 0; a < k; a++) { d0[a] = P.d(depot, P.m + cu[a]); for (int b = 0; b < k; b++) D[(size_t)a * k + b] = P.d(P.m + cu[a], P.m + cu[b]); }
        const size_t S = (size_t)1 << k;
        std::vector<double> F(S * k, INFINITY); std::vector<signed char> Pp(S * k, -1);
        for (int j = 0; j < k; j++) F[((size_t)1 << j) * k + j] = d0[j] * k;
        for (size_t mask = 1; mask < S; mask++) {
            const int m1 = __builtin_popcountll((unsigned long long)mask);
            if (m1 == k) continue;
            for (int j = 0; j < k; j++) {
                if (!((mask >> j) & 1)) continue;
                const double v = F[mask * k + j]; if (v == INFINITY) continue;
                for (int t = 0; t < k; t++) {
                    if ((mask >> t) & 1) continue;
                    const double c = v + D[(size_t)j * k + t] * (k - m1);
                    const size_t nm = mask | ((size_t)1 << t);
                    if (c < F[nm * k + t]) { F[nm * k + t] = c; Pp[nm * k + t] = (signed char)j; }
                }
            }
        }
        const size_t full = S - 1; int bj = 0; double best = INFINITY;
        for (int j = 0; j < k; j++) if (F[full * k + j] < best) { best = F[full * k + j]; bj = j; }
        std::vector<int> ord(k); size_t mask = full; int j = bj;
        for (int pos = k - 1; pos >= 0; pos--) { ord[pos] = cu[j]; const int pj = Pp[mask * k + j]; mask ^= ((size_t)1 << j); j = pj; }
        return ord;
    }
    static uint64_t hkey(int depot, const std::vector<int> &sorted) {
        uint64_t h = 1469598103934665603ULL ^ (uint64_t)(depot + 1);
        h *= 1099511628211ULL;
        for (int c : sorted) { h ^= (uint64_t)(c + 1); h *= 1099511628211ULL; }
        return h;
    }
    std::unordered_map<uint64_t, std::vector<int>> idx;
    // adds a route; returns its pool index (existing or new)
    int add(int depot, const std::vector<int> &path) {
        if (path.empty()) return -1;
        std::vector<int> srt = path; std::sort(srt.begin(), srt.end());
        std::vector<uint64_t> mask(W, 0ULL); for (int c : srt) mask[c >> 6] |= 1ULL << (c & 63);
        const uint64_t h = hkey(depot, srt);
        auto &lst = idx[h];
        double lat = lat_of(depot, path);
        for (int j : lst) {
            PRoute &r = R[j];
            if (r.depot == depot && r.mask == mask) {
                n_hit++;
                if ((int)path.size() > DP_KMAX && lat < r.lat - 1e-9) { r.path = path; r.lat = lat; }
                return j;
            }
        }
        std::vector<int> pth = path;
        if ((int)path.size() <= DP_KMAX && path.size() >= 2) {
            dp_calls++;
            std::vector<int> o = dp_order(depot, path);
            const double l2 = lat_of(depot, o);
            if (l2 < lat - 1e-9) { pth = o; lat = l2; dp_gain++; }
        } else if ((int)path.size() > DP_KMAX) dp_skipped++;
        PRoute r; r.depot = depot; r.path = pth; r.lat = lat; r.mask = mask;
        R.push_back(std::move(r)); lst.push_back((int)R.size() - 1);
        n_new++; new_since_call++;
        return (int)R.size() - 1;
    }

    // ---------------------------------------------------------------------------------------- SP for one depot set
    SPResult solve_set(const std::vector<int> &depot_set, double UB, double deadline_cpu, long node_limit) const {
        SPResult out; const int n = P.n;
        std::vector<char> inS(P.m, 0); for (int d : depot_set) inS[d] = 1;
        std::vector<int> ids;
        for (size_t j = 0; j < R.size(); j++) if (inS[R[j].depot]) ids.push_back((int)j);
        const int Rn = (int)ids.size(); out.routes_in = Rn;
        std::vector<std::vector<int>> cov(n);
        for (int a = 0; a < Rn; a++) for (int c : R[ids[a]].path) cov[c].push_back(a);
        for (int c = 0; c < n; c++) if (cov[c].empty()) { out.nocover = true; return out; }
        std::vector<double> cst(Rn); std::vector<int> sz(Rn);
        for (int a = 0; a < Rn; a++) { cst[a] = R[ids[a]].lat; sz[a] = (int)R[ids[a]].path.size(); }
        // ---- subgradient ascent on the Lagrangian dual
        std::vector<double> u(n, INFINITY), bu, g(n), rc(Rn);
        for (int a = 0; a < Rn; a++) for (int c : R[ids[a]].path) u[c] = std::min(u[c], cst[a] / sz[a]);
        double lam = 0.0, blam = 0.0, bL = -INFINITY, f = 2.0; int noimp = 0; bu = u;
        for (int it = 0; it < g_sg_iters; it++) {
            double L = -lam * P.Nv; for (int c = 0; c < n; c++) L += u[c];
            std::fill(g.begin(), g.end(), 1.0); int xs = 0;
            for (int a = 0; a < Rn; a++) {
                double r = cst[a] + lam; for (int c : R[ids[a]].path) r -= u[c];
                rc[a] = r;
                if (r < 0) { L += r; xs++; for (int c : R[ids[a]].path) g[c] -= 1.0; }
            }
            double gl = xs - P.Nv; if (lam <= 0 && gl < 0) gl = 0;
            if (L > bL + 1e-9) { bL = L; bu = u; blam = lam; noimp = 0; } else if (++noimp >= g_sg_patience) { f *= 0.5; noimp = 0; }
            if (bL >= UB - 1e-7) break;
            double nrm = gl * gl; for (int c = 0; c < n; c++) nrm += g[c] * g[c];
            if (nrm < 1e-12 || f < 1e-5) break;
            const double t = f * (UB - L) / nrm;
            for (int c = 0; c < n; c++) u[c] += t * g[c];
            lam = std::max(0.0, lam + t * gl);
            if ((it & 31) == 31 && cpu_now() > deadline_cpu) break;
        }
        u = bu; lam = blam;
        double L = -lam * P.Nv; for (int c = 0; c < n; c++) L += u[c];
        for (int a = 0; a < Rn; a++) { double r = cst[a] + lam; for (int c : R[ids[a]].path) r -= u[c]; rc[a] = r; if (r < 0) L += r; }
        out.lb = L;
        if (L >= UB - 1e-7) { out.complete = true; return out; }       // proof: no selection cheaper than UB in this sub-pool
        // ---- reduced-cost fixing against UB
        std::vector<int> kept;
        for (int a = 0; a < Rn; a++) if (L + std::max(0.0, rc[a]) < UB - 1e-7) kept.push_back(a);
        out.routes_kept = (int)kept.size();
        const int K = (int)kept.size();
        std::vector<std::vector<int>> kcov(n);                          // kept routes (local kept index) per customer, by rc ascending
        std::vector<int> order(K); std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&](int x, int y) { return rc[kept[x]] < rc[kept[y]]; });
        std::vector<int> kpos(K);                                       // rank of kept route in rc order
        std::vector<int> kid(K);                                        // kid[rank] = local route index a
        for (int r = 0; r < K; r++) kid[r] = kept[order[r]];
        for (int r = 0; r < K; r++) for (int c : R[ids[kid[r]]].path) kcov[c].push_back(r);
        for (int c = 0; c < n; c++) if (kcov[c].empty()) { out.complete = true; return out; }   // some customer lost all routes: nothing better than UB
        std::vector<double> krc(K), kc(K); std::vector<int> kdep(K);
        for (int r = 0; r < K; r++) { krc[r] = rc[kid[r]]; kc[r] = cst[kid[r]]; kdep[r] = R[ids[kid[r]]].depot; }
        // ---- depth-first exact cover with Lagrangian bound
        std::vector<int> cur, bestsel; double ub = UB; long nodes = 0; bool stop = false, hit_limit = false;
        std::vector<int> dcnt(P.m, 0); int ndep = 0;
        std::vector<uint64_t> covered(W, 0ULL);
        std::vector<int> cnt(n);
        std::vector<int> compat; compat.reserve(K);
        // recursive lambda via std::function-free helper
        struct Rec {
            const Pool *self; const std::vector<int> &ids; const std::vector<int> &kid; int K, n, W; const std::vector<double> &krc, &kc, &u; const std::vector<std::vector<int>> &kcov;
            const std::vector<int> &kdep; double lam; double &ub; std::vector<int> &cur, &bestsel; std::vector<int> &dcnt; int &ndep; std::vector<uint64_t> &covered; std::vector<int> &cnt;
            long &nodes; bool &stop, &hit; double deadline; long node_limit;
            void go(double cost, int k, int ncov) {
                if (stop) return;
                if (++nodes > node_limit) { stop = true; hit = true; return; }
                if ((nodes & 255) == 0 && cpu_now() > deadline) { stop = true; hit = true; return; }
                if (ncov == n) {
                    const Params &P = self->P;
                    const bool okdep = P.atmost ? ndep <= P.Ng : ndep == P.Ng;
                    if (okdep && cost < ub - 1e-9) { ub = cost; bestsel = cur; }
                    return;
                }
                if (k >= self->P.Nv) return;
                // compatible routes, node bound, counts
                double lbn = cost - lam * (self->P.Nv - k);
                for (int c = 0; c < n; c++) if (!((covered[c >> 6] >> (c & 63)) & 1ULL)) lbn += u[c];
                std::vector<int> compat; compat.reserve(64);
                std::vector<double> negs;                                   // at most Nv-k further routes can be selected: only the most negative reduced costs count
                for (int r = 0; r < K; r++) {
                    const std::vector<uint64_t> &mk = self->R[ids[kid[r]]].mask; bool ok = true;
                    for (int w = 0; w < W; w++) if (mk[w] & covered[w]) { ok = false; break; }
                    if (!ok) continue;
                    compat.push_back(r); if (krc[r] < 0) negs.push_back(krc[r]);
                }
                { const size_t lim = (size_t)(self->P.Nv - k);
                  if (negs.size() > lim) std::nth_element(negs.begin(), negs.begin() + lim, negs.end());
                  for (size_t i = 0; i < negs.size() && i < lim; i++) lbn += negs[i]; }
                if (lbn >= ub - 1e-7) return;
                std::fill(cnt.begin(), cnt.end(), 0);
                for (int r : compat) for (int c : self->R[ids[kid[r]]].path) cnt[c]++;
                int cs = -1, cm = 1 << 30;
                for (int c = 0; c < n; c++) if (!((covered[c >> 6] >> (c & 63)) & 1ULL)) { if (cnt[c] < cm) { cm = cnt[c]; cs = c; if (cm == 0) break; } }
                if (cs < 0 || cm == 0) return;
                std::vector<int> cand;
                for (int r : kcov[cs]) {                                    // rc ascending
                    const std::vector<uint64_t> &mk = self->R[ids[kid[r]]].mask; bool ok = true;
                    for (int w = 0; w < W; w++) if (mk[w] & covered[w]) { ok = false; break; }
                    if (ok) cand.push_back(r);
                }
                for (int r : cand) {
                    const PRoute &pr = self->R[ids[kid[r]]];
                    for (int w = 0; w < W; w++) covered[w] |= pr.mask[w];
                    if (dcnt[pr.depot]++ == 0) ndep++;
                    cur.push_back(ids[kid[r]]);
                    go(cost + pr.lat, k + 1, ncov + (int)pr.path.size());
                    cur.pop_back();
                    if (--dcnt[pr.depot] == 0) ndep--;
                    for (int w = 0; w < W; w++) covered[w] &= ~pr.mask[w];
                    if (stop) return;
                }
            }
        };
        (void)kpos; (void)kc; (void)kdep; (void)cnt; (void)compat;
        Rec rec{this, ids, kid, K, n, W, krc, kc, u, kcov, kdep, lam, ub, cur, bestsel, dcnt, ndep, covered, cnt, nodes, stop, hit_limit, deadline_cpu, node_limit};
        rec.go(0.0, 0, 0);
        out.nodes = nodes;
        if (!bestsel.empty()) { out.improved = true; out.cost = ub; out.sel = bestsel; }
        out.complete = !hit_limit;
        return out;
    }
};

}  // namespace psp
