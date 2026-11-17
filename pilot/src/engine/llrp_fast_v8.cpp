// llrp_fast.cpp -- GRASP + RVND for the Latency Location-Routing Problem (LLRP): fast engine with O(1) move evaluation.
//
// Evaluation: Silva, Subramanian, Vidal, Ochi (2012), EJOR 221(3):513-520 (concatenation of sub-sequences, Proposition 1).
// Search:     GRASP construction (ECWA + RCL, diversification / intensification cycle of the CLRP code) followed by a descent over a
//             configurable POOL of neighbourhoods (RVND = random order, or fixed order), best (or first) improvement, optional strategic
//             oscillation (--so), optional ILS with double-bridge perturbation (--ils K).
// Termination: --max-iter N (cap), --stall K (stop after K consecutive GRASP iterations without a new best), --time S (CPU seconds).
// Output:     --out PREFIX writes PREFIX.{run,routes,iter,ops,trace}.csv (open depots, routes with arrival times, iteration log,
//             per-operator statistics, anytime trace).
//
//   llrp_fast --instance X.inst --seed S [--ops zou|legacy5|full|LIST] [--so] [--ds] [--select best|first] [--order random|fixed]
//             [--max-iter 1000] [--stall K] [--time SEC] [--ils K] [--rcl 5] [--out PREFIX] [--algo NAME] [--check] [--quiet]
//             [--dpm-rank K[,eps]] [--dpm-prune] [--dpm-memory]      (v6 depot layer, off by default; see the block before initial_allowed)
//             [--pool-sp] [--pool-tl S] [--pool-sets M] [--pool-first N] [--pool-src 1|2] [--pool-theta X] [--pool-nodes N]
//                                                                    (v7 in-run route pool + exact order DP + set-partitioning recombination, off by default; poolsp.hpp)
//
// Build:  g++ -O3 -std=c++11 -ffp-contract=off -o llrp_fast llrp_fast.cpp
#include <algorithm>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include <time.h>
#include "poolsp.hpp"

using std::string;
using std::vector;


[[noreturn]] static void die(const string &msg) {
    fprintf(stderr, "llrp_vnd: ERROR: %s\n", msg.c_str());
    exit(2);
}

struct Counters { long lat = 0, dist = 0, valid = 0, samples = 0, choices = 0; } CT;
static bool g_atmost = false;      // --atmost: at most Ng open depots (default: exactly Ng, as in the original port)

// ------------------------------------------------------------------------------------------------ instance
struct Inst {
    string name;
    int n = 0, m = 0, N = 0, Nv = 0, Ng = 0;
    double Q = 0, bks = 0;
    vector<double> D;       // (m+n)^2 distance matrix, customer c has global index m + c
    vector<double> dem;
    vector<double> dxy;     // coordinates (depots then customers) x,y
    inline double d(int i, int j) const { return D[(size_t)i * N + j]; }
};

static Inst read_instance(const string &path) {
    std::ifstream f(path);
    if (!f) die("cannot open instance " + path);
    Inst I;
    string tok;
    vector<double> hexd;
    f >> tok;
    if (tok != "LLRP_INSTANCE") die("not an instance file");
    int ver;
    f >> ver;
    while (f >> tok) {
        if (tok == "name") f >> I.name;
        else if (tok == "n") f >> I.n;
        else if (tok == "m") f >> I.m;
        else if (tok == "Q") { string s; f >> s; I.Q = strtod(s.c_str(), nullptr); }
        else if (tok == "Nv") f >> I.Nv;
        else if (tok == "Ng") f >> I.Ng;
        else if (tok == "bks") { string s; f >> s; I.bks = strtod(s.c_str(), nullptr); }
        else if (tok == "depots") {
            for (int i = 0; i < I.m; i++) { string a, b; f >> a >> b; I.dxy.push_back(strtod(a.c_str(), nullptr)); I.dxy.push_back(strtod(b.c_str(), nullptr)); }
        } else if (tok == "customers") {
            for (int i = 0; i < I.n; i++) {
                string a, b, c; f >> a >> b >> c;
                I.dxy.push_back(strtod(a.c_str(), nullptr)); I.dxy.push_back(strtod(b.c_str(), nullptr));
                I.dem.push_back(strtod(c.c_str(), nullptr));
            }
        } else if (tok == "dist_hex") {
            int N = I.m + I.n;
            hexd.resize((size_t)N * N);
            for (size_t k = 0; k < hexd.size(); k++) { string s; f >> s; hexd[k] = strtod(s.c_str(), nullptr); }
        }
    }
    I.N = I.m + I.n;
    I.D.assign((size_t)I.N * I.N, 0.0);
    // numpy: diff = c[:,None,:] - c[None,:,:]; dist = sqrt(sum(diff**2, axis=-1)) -> sqrt(dx*dx + dy*dy)
    for (int i = 0; i < I.N; i++)
        for (int j = 0; j < I.N; j++) {
            double dx = I.dxy[2 * i] - I.dxy[2 * j], dy = I.dxy[2 * i + 1] - I.dxy[2 * j + 1];
            double sx = dx * dx, sy = dy * dy;
            I.D[(size_t)i * I.N + j] = std::sqrt(sx + sy);
        }
    if (!hexd.empty()) {
        size_t bad = 0;
        for (size_t k = 0; k < hexd.size(); k++)
            if (memcmp(&hexd[k], &I.D[k], sizeof(double)) != 0) bad++;
        fprintf(stderr, "llrp_vnd: distance matrix vs numpy: %zu of %zu entries differ bitwise\n", bad, hexd.size());
        if (bad) die("distance matrix is not bit-identical to the Python one");
    }
    return I;
}

// numpy.sum for float64 (pairwise summation), used by initial_beta
static double np_pairwise_sum(const double *a, size_t n) {
    if (n < 8) {
        double res = 0.;
        for (size_t i = 0; i < n; i++) res += a[i];
        return res;
    } else if (n <= 128) {
        double r[8];
        for (int j = 0; j < 8; j++) r[j] = a[j];
        size_t i;
        for (i = 8; i < n - (n % 8); i += 8)
            for (int j = 0; j < 8; j++) r[j] += a[i + j];
        double res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++) res += a[i];
        return res;
    } else {
        size_t n2 = n / 2;
        n2 -= n2 % 8;
        return np_pairwise_sum(a, n2) + np_pairwise_sum(a + n2, n - n2);
    }
}

// ------------------------------------------------------------------------------------------------ Python-compatible randomness
// CPython's random module (Mersenne Twister MT19937, Modules/_randommodule.c + Lib/random.py), re-implemented so that
// `--pyrng --seed s` reproduces the random stream of Python's `random.seed(s)` exactly.
struct PyMT {
    enum { N = 624, M = 397 };
    uint32_t mt[N];
    int index = N;
    void init_genrand(uint32_t s) {
        mt[0] = s;
        int mti;
        for (mti = 1; mti < N; mti++) mt[mti] = (1812433253U * (mt[mti - 1] ^ (mt[mti - 1] >> 30)) + (uint32_t)mti);
        index = mti;
    }
    void init_by_array(const uint32_t *key, int klen) {
        init_genrand(19650218U);
        int i = 1, j = 0;
        for (int k = (N > klen ? N : klen); k; k--) {
            mt[i] = (mt[i] ^ ((mt[i - 1] ^ (mt[i - 1] >> 30)) * 1664525U)) + key[j] + (uint32_t)j;
            i++; j++;
            if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
            if (j >= klen) j = 0;
        }
        for (int k = N - 1; k; k--) {
            mt[i] = (mt[i] ^ ((mt[i - 1] ^ (mt[i - 1] >> 30)) * 1566083941U)) - (uint32_t)i;
            i++;
            if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
        }
        mt[0] = 0x80000000U;
    }
    // random.seed(int): the key is abs(seed) as little-endian 32-bit words (one word for seeds < 2**32, also for 0)
    void seed(unsigned long long s) {
        uint32_t key[2];
        int klen = 1;
        key[0] = (uint32_t)(s & 0xffffffffULL);
        key[1] = (uint32_t)(s >> 32);
        if (key[1]) klen = 2;
        init_by_array(key, klen);
    }
    uint32_t genrand_uint32() {
        static const uint32_t mag01[2] = {0x0U, 0x9908b0dfU};
        uint32_t y;
        if (index >= N) {
            int kk;
            for (kk = 0; kk < N - M; kk++) {
                y = (mt[kk] & 0x80000000U) | (mt[kk + 1] & 0x7fffffffU);
                mt[kk] = mt[kk + M] ^ (y >> 1) ^ mag01[y & 1U];
            }
            for (; kk < N - 1; kk++) {
                y = (mt[kk] & 0x80000000U) | (mt[kk + 1] & 0x7fffffffU);
                mt[kk] = mt[kk + (M - N)] ^ (y >> 1) ^ mag01[y & 1U];
            }
            y = (mt[N - 1] & 0x80000000U) | (mt[0] & 0x7fffffffU);
            mt[N - 1] = mt[M - 1] ^ (y >> 1) ^ mag01[y & 1U];
            index = 0;
        }
        y = mt[index++];
        y ^= (y >> 11);
        y ^= (y << 7) & 0x9d2c5680U;
        y ^= (y << 15) & 0xefc60000U;
        y ^= (y >> 18);
        return y;
    }
    uint32_t getrandbits(int k) { return k <= 0 ? 0 : (genrand_uint32() >> (32 - k)); }        // k <= 32
    // Random._randbelow_with_getrandbits(n): k = n.bit_length(); r = getrandbits(k); while r >= n: redraw
    uint32_t randbelow(uint32_t n) {
        int k = 0;
        for (uint32_t t = n; t; t >>= 1) k++;
        uint32_t r = getrandbits(k);
        while (r >= n) r = getrandbits(k);
        return r;
    }
};

// CPython's set of small non-negative ints (hash(v) == v; Objects/setobject.c of 3.7 ... 3.13: open addressing,
// LINEAR_PROBES = 9, PERTURB_SHIFT = 5, table 8 -> resize to 4*used when fill*5 >= mask*3).  Only the operations that
// the user's code performs are emulated: add(), set(other_set) (set_merge) and iteration order; nothing is ever removed.
struct PySet {
    vector<long long> tab;                 // -1 = empty slot
    size_t mask, fill, used;
    PySet() : tab(8, -1), mask(7), fill(0), used(0) {}
    static void insert_clean(vector<long long> &t, size_t mk, long long v) {
        size_t perturb = (size_t)v, i = (size_t)v & mk;
        for (;;) {
            size_t e = i;
            if (t[e] < 0) { t[e] = v; return; }
            if (i + 9 <= mk) {
                for (size_t j = 0; j < 9; j++) {
                    e++;
                    if (t[e] < 0) { t[e] = v; return; }
                }
            }
            perturb >>= 5;
            i = (i * 5 + 1 + perturb) & mk;
        }
    }
    void resize(size_t minused) {
        size_t newsize = 8;
        while (newsize <= minused) newsize <<= 1;
        vector<long long> nt(newsize, -1);
        for (size_t k = 0; k < tab.size(); k++) if (tab[k] >= 0) insert_clean(nt, newsize - 1, tab[k]);
        tab.swap(nt);
        mask = newsize - 1;
        fill = used;
    }
    void add(long long v) {
        size_t perturb = (size_t)v, i = (size_t)v & mask;
        for (;;) {
            size_t probes = (i + 9 <= mask) ? 9 : 0;
            for (size_t k = 0; k <= probes; k++) {
                size_t e = i + k;
                if (tab[e] < 0) {
                    tab[e] = v; fill++; used++;
                    if (fill * 5 >= mask * 3) resize(used > 50000 ? used * 2 : used * 4);
                    return;
                }
                if (tab[e] == v) return;                           // already present
            }
            perturb >>= 5;
            i = (i * 5 + 1 + perturb) & mask;
        }
    }
    PySet copy() const {                                           // set(other): set_merge into an empty set
        PySet s;
        if (used == 0) return s;
        if ((s.fill + used) * 5 >= s.mask * 3) s.resize((s.used + used) * 2);
        if (s.fill == 0 && s.mask == mask && fill == used) {       // same table size, no dummies: copy the table
            s.tab = tab; s.fill = fill; s.used = used;
            return s;
        }
        s.fill = s.used = used;                                    // otherwise set_insert_clean in the order of the source table
        for (size_t k = 0; k < tab.size(); k++) if (tab[k] >= 0) insert_clean(s.tab, s.mask, tab[k]);
        return s;
    }
    vector<int> items() const {                                    // list(set)
        vector<int> r;
        for (size_t k = 0; k < tab.size(); k++) if (tab[k] >= 0) r.push_back((int)tab[k]);
        return r;
    }
};

// ------------------------------------------------------------------------------------------------ randomness
struct Event { char t; vector<long long> v; };

struct Rng {
    bool replay = false;
    bool pyrng = false;                 // Python-compatible MT19937 stream (--pyrng), otherwise std::mt19937_64
    long order_mismatch = 0;            // replay only: emulated Python set order differed from the recorded one
    vector<Event> ev;
    size_t pos = 0;
    std::mt19937_64 gen;
    PyMT mt;

    void load_trace(const string &path) {
        std::ifstream f(path);
        if (!f) die("cannot open trace " + path);
        string line;
        std::getline(f, line);                           // header
        while (std::getline(f, line)) {
            if (line.empty()) continue;
            std::istringstream ss(line);
            string t; ss >> t;
            Event e; e.t = t[0];
            long long x;
            while (ss >> x) e.v.push_back(x);
            ev.push_back(e);
        }
        replay = true;
    }
    Event &next(char t, const char *where) {
        if (pos >= ev.size()) die(string("trace exhausted at ") + where);
        Event &e = ev[pos++];
        if (e.t != t) die(string("trace desync at ") + where + ": expected event '" + t + "', trace has '" + e.t + "' (event #" + std::to_string(pos) + ")");
        return e;
    }
    // random.choice(seq of length n) -> index
    int choice(int n) {
        CT.choices++;
        if (replay) {
            Event &e = next('C', "choice");
            if (e.v[0] != n) die("trace desync: choice length " + std::to_string(n) + " vs recorded " + std::to_string(e.v[0]));
            return (int)e.v[1];
        }
        if (pyrng) return (int)mt.randbelow((uint32_t)n);
        return std::uniform_int_distribution<int>(0, n - 1)(gen);
    }
    // random.sample(population, k) -> chosen VALUES in selection order
    vector<int> sample(const vector<int> &pop, int k) {
        CT.samples++;
        if (replay) {
            Event &e = next('S', "sample");
            if (e.v[0] != (long long)pop.size() || e.v[1] != k) die("trace desync: sample(" + std::to_string(pop.size()) + "," + std::to_string(k) + ")");
            vector<int> r;
            for (int i = 0; i < k; i++) {
                int val = (int)e.v[2 + i];
                if (std::find(pop.begin(), pop.end(), val) == pop.end()) die("trace desync: sampled value not in population");
                r.push_back(val);
            }
            return r;
        }
        if (pyrng) return py_sample(pop, k);
        vector<int> pool = pop, r;
        int n = (int)pool.size();
        for (int i = 0; i < k; i++) {
            int j = std::uniform_int_distribution<int>(0, n - i - 1)(gen);
            r.push_back(pool[j]);
            pool[j] = pool[n - i - 1];
        }
        return r;
    }
    // Lib/random.py Random.sample(population, k) for a sequence population
    vector<int> py_sample(const vector<int> &pop, int k) {
        int n = (int)pop.size();
        if (k < 0 || k > n) die("sample larger than population or is negative");
        vector<int> result(k);
        long long setsize = 21;                                    // size of a small set minus size of an empty list
        if (k > 5) {
            long long p4 = 1;
            while (p4 < 3LL * k) p4 *= 4;                          // 4 ** ceil(log(k*3, 4))
            setsize += p4;
        }
        if (n <= setsize) {                                        // pool algorithm
            vector<int> pool = pop;
            for (int i = 0; i < k; i++) {
                int j = (int)mt.randbelow((uint32_t)(n - i));
                result[i] = pool[j];
                pool[j] = pool[n - i - 1];
            }
        } else {                                                   // selection-set algorithm
            std::set<int> selected;
            for (int i = 0; i < k; i++) {
                int j = (int)mt.randbelow((uint32_t)n);
                while (selected.count(j)) j = (int)mt.randbelow((uint32_t)n);
                selected.insert(j);
                result[i] = pop[j];
            }
        }
        return result;
    }
    // lists whose order comes from Python set iteration.  `v` holds the order predicted by the CPython set emulation
    // (PySet).  Replay mode: the recorded order is adopted (same members required) and a prediction that differs is
    // counted in order_mismatch, so the emulation is checked against real Python runs.
    void order(char t, vector<int> &v) {
        if (!replay) return;
        Event &e = next(t, "order");
        if (e.v[0] != (long long)v.size()) die(string("trace desync: list '") + t + "' length");
        vector<int> rec;
        for (size_t i = 0; i < v.size(); i++) rec.push_back((int)e.v[1 + i]);
        vector<int> a = v, b = rec;
        std::sort(a.begin(), a.end()); std::sort(b.begin(), b.end());
        if (a != b) die(string("trace desync: list '") + t + "' has different members");
        if (v != rec) order_mismatch++;
        v = rec;
    }
};
static Rng RNG;

// ------------------------------------------------------------------------------------------------ evaluation
static const Inst *G = nullptr;

static inline double eval_lat(int depot, const int *p, size_t L) {            // evaluate_route_latency
    CT.lat++;
    if (L == 0) return 0.0;
    double tot = 0.0, arr = 0.0;
    int prev = depot;
    const int m = G->m;
    for (size_t k = 0; k < L; k++) {
        int cg = m + p[k];
        arr += G->d(prev, cg);
        tot += arr;
        prev = cg;
    }
    return tot;
}
static inline double eval_dist(int depot, const int *p, size_t L) {           // evaluate_route_distance_open
    CT.dist++;
    if (L == 0) return 0.0;
    double dd = 0.0;
    int prev = depot;
    const int m = G->m;
    for (size_t k = 0; k < L; k++) {
        int cg = m + p[k];
        dd += G->d(prev, cg);
        prev = cg;
    }
    return dd;
}
static inline double path_load(const int *p, size_t L) {
    double s = 0.0;
    for (size_t k = 0; k < L; k++) s += G->dem[p[k]];
    return s;
}

struct Route { int depot = 0; vector<int> path; double load = 0, latency = 0, dist = 0; };
struct Sol {
    vector<Route> routes;
    vector<int> open;           // open depots (ascending; in replay mode adopted from the trace where Python order matters)
    double cost = INFINITY;
};

static double calculate_cost(Sol &s) {
    std::set<int> od;
    double tl = 0.0;
    for (auto &r : s.routes) {
        if (r.path.empty()) continue;
        od.insert(r.depot);
        r.latency = eval_lat(r.depot, r.path.data(), r.path.size());
        r.dist = eval_dist(r.depot, r.path.data(), r.path.size());
        tl += r.latency;
    }
    s.open.assign(od.begin(), od.end());
    s.cost = tl;
    return s.cost;
}
// Python's Solution.open_depots after calculate_cost(): a set filled by .add() in route order (empty routes skipped);
// its iteration order is what list(sol.open_depots) returns.
static PySet py_open_set(const Sol &s) {
    PySet p;
    for (auto &r : s.routes) if (!r.path.empty()) p.add(r.depot);
    return p;
}
static int route_count(const Sol &s) { int c = 0; for (auto &r : s.routes) if (!r.path.empty()) c++; return c; }
static void drop_empty(Sol &s) {
    vector<Route> k;
    for (auto &r : s.routes) if (!r.path.empty()) k.push_back(std::move(r));
    s.routes.swap(k);
}
static bool check_validity(Sol &s) {
    CT.valid++;
    calculate_cost(s);
    int nonempty = 0;
    for (auto &r : s.routes) if (!r.path.empty()) nonempty++;
    if (nonempty > G->Nv) return false;
    if (g_atmost ? (int)s.open.size() > G->Ng : (int)s.open.size() != G->Ng) return false;
    for (auto &r : s.routes) if (!r.path.empty() && r.load > G->Q + 1e-4) return false;
    vector<char> seen(G->n, 0);
    size_t tot = 0;
    for (auto &r : s.routes) {
        if (r.path.empty()) continue;
        for (int c : r.path) { if (c < 0 || c >= G->n || seen[c]) return false; seen[c] = 1; tot++; }
    }
    return tot == (size_t)G->n;
}
// ------------------------------------------------------------------------------------------------ construction
static void repair_route_count_by_relocation(Sol &sol) {
    const Inst &I = *G;
    int target = I.Nv;
    while (route_count(sol) > target) {
        drop_empty(sol);
        calculate_cost(sol);
        vector<int> order(sol.routes.size());
        for (size_t i = 0; i < order.size(); i++) order[i] = (int)i;
        std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return sol.routes[a].load < sol.routes[b].load; });
        bool eliminated = false;
        for (int ridx : order) {
            if (sol.routes[ridx].path.empty()) continue;
            vector<int> move = sol.routes[ridx].path;
            vector<Route> temp = sol.routes;
            bool success = true;
            std::stable_sort(move.begin(), move.end(), [&](int a, int b) { return I.dem[a] > I.dem[b]; });
            for (int cust : move) {
                double cd = I.dem[cust];
                bool have = false;
                size_t b_t = 0, b_pos = 0;
                double best_delta = INFINITY, best_lat = 0;
                for (size_t tidx = 0; tidx < temp.size(); tidx++) {
                    if ((int)tidx == ridx) continue;
                    Route &tr = temp[tidx];
                    if (tr.load + cd > I.Q + 1e-4) continue;
                    double old_lat = eval_lat(tr.depot, tr.path.data(), tr.path.size());
                    vector<int> np;
                    for (size_t pos = 0; pos <= tr.path.size(); pos++) {
                        np.assign(tr.path.begin(), tr.path.begin() + pos);
                        np.push_back(cust);
                        np.insert(np.end(), tr.path.begin() + pos, tr.path.end());
                        double nl = eval_lat(tr.depot, np.data(), np.size());
                        double delta = nl - old_lat;
                        if (delta < best_delta) { best_delta = delta; have = true; b_t = tidx; b_pos = pos; best_lat = nl; }
                    }
                }
                if (!have) { success = false; break; }
                Route &tr = temp[b_t];
                vector<int> np(tr.path.begin(), tr.path.begin() + b_pos);
                np.push_back(cust);
                np.insert(np.end(), tr.path.begin() + b_pos, tr.path.end());
                tr.path = np;
                tr.load += cd;
                tr.latency = best_lat;
                tr.dist = eval_dist(tr.depot, tr.path.data(), tr.path.size());
            }
            if (success) {
                temp[ridx].path.clear();
                temp[ridx].load = 0.0;
                sol.routes.clear();
                for (auto &r : temp) if (!r.path.empty()) sol.routes.push_back(r);
                calculate_cost(sol);
                eliminated = true;
                break;
            }
        }
        if (!eliminated) break;
    }
}

struct ECand { int i, j, ord, dep; double delta, nl, nd; };

static Sol ECWA(vector<int> allowed, int rcl_size) {
    const Inst &I = *G;
    Sol sol;
    // _select_initial_allowed_depots
    {
        vector<int> u;
        for (int d : allowed) if (std::find(u.begin(), u.end(), d) == u.end()) u.push_back(d);
        allowed = u;
        int max_open = std::max(1, std::min(I.Ng, I.m));
        if ((int)allowed.size() > max_open) allowed = RNG.sample(allowed, max_open);
        if (allowed.empty()) die("empty allowed depot list (randrange branch not ported)");
    }
    // phase 1
    for (int c = 0; c < I.n; c++) {
        int cg = I.m + c, best = allowed[0];
        double bd = I.d(allowed[0], cg);
        for (size_t k = 1; k < allowed.size(); k++) {
            double dd = I.d(allowed[k], cg);
            if (dd < bd) { bd = dd; best = allowed[k]; }          // min(): first minimum wins
        }
        Route r; r.depot = best; r.path = {c}; r.load = I.dem[c]; r.dist = bd; r.latency = bd;
        sol.routes.push_back(r);
    }
    // phase 2
    int target = I.Nv;
    vector<ECand> cands;
    while (route_count(sol) > target) {
        cands.clear();
        vector<int> idx;                                          // indices of non-empty routes
        for (size_t k = 0; k < sol.routes.size(); k++) if (!sol.routes[k].path.empty()) idx.push_back((int)k);
        int R = (int)idx.size();
        for (int i = 0; i < R; i++)
            for (int j = 0; j < R; j++) {
                if (i == j) continue;
                const Route &r1 = sol.routes[idx[i]], &r2 = sol.routes[idx[j]];
                double cl = r1.load + r2.load;
                if (cl > I.Q + 1e-4) continue;
                double old_obj = eval_lat(r1.depot, r1.path.data(), r1.path.size()) + eval_lat(r2.depot, r2.path.data(), r2.path.size());
                int cdep[2], nd = 0;
                cdep[nd++] = r1.depot;
                if (r2.depot != r1.depot) cdep[nd++] = r2.depot;
                for (int di = 0; di < nd; di++)
                    for (int ord = 0; ord < 2; ord++) {
                        const vector<int> &a = ord == 0 ? r1.path : r2.path;
                        const vector<int> &b = ord == 0 ? r2.path : r1.path;
                        // latency / distance of the concatenation a+b from depot cdep[di] (same arithmetic as the numba kernels)
                        CT.lat++; CT.dist++;
                        double tot = 0.0, arr = 0.0, dd = 0.0;
                        int prev = cdep[di];
                        for (int c : a) { int cg = I.m + c; double w = I.d(prev, cg); arr += w; tot += arr; dd += w; prev = cg; }
                        for (int c : b) { int cg = I.m + c; double w = I.d(prev, cg); arr += w; tot += arr; dd += w; prev = cg; }
                        cands.push_back({i, j, ord, cdep[di], tot - old_obj, tot, dd});
                    }
            }
        if (cands.empty()) break;
        std::stable_sort(cands.begin(), cands.end(), [](const ECand &x, const ECand &y) { return x.delta < y.delta; });
        int actual = std::min((int)cands.size(), std::max(1, rcl_size));
        int pick = RNG.choice(actual);
        const ECand ch = cands[pick];
        Route nr;
        const Route &r1 = sol.routes[idx[ch.i]], &r2 = sol.routes[idx[ch.j]];
        nr.depot = ch.dep;
        const vector<int> &a = ch.ord == 0 ? r1.path : r2.path;
        const vector<int> &b = ch.ord == 0 ? r2.path : r1.path;
        nr.path = a; nr.path.insert(nr.path.end(), b.begin(), b.end());
        nr.load = r1.load + r2.load; nr.dist = ch.nd; nr.latency = ch.nl;
        int hi = std::max(idx[ch.i], idx[ch.j]), lo = std::min(idx[ch.i], idx[ch.j]);
        sol.routes.erase(sol.routes.begin() + hi);
        sol.routes.erase(sol.routes.begin() + lo);
        sol.routes.push_back(nr);
    }
    repair_route_count_by_relocation(sol);
    // force exactly Ng depots (not in --atmost mode)
    if (!g_atmost) {
        int req = I.Ng;
        std::set<int> used;
        for (auto &r : sol.routes) if (!r.path.empty()) used.insert(r.depot);
        if ((int)used.size() < req) {
            vector<int> unused;
            for (int d : allowed) if (!used.count(d)) unused.push_back(d);
            vector<int> ri(sol.routes.size());
            for (size_t i = 0; i < ri.size(); i++) ri[i] = (int)i;
            std::stable_sort(ri.begin(), ri.end(), [&](int a, int b) { return sol.routes[a].load < sol.routes[b].load; });
            size_t ip = 0;
            while ((int)used.size() < req && !unused.empty() && ip < ri.size()) {
                int nd = unused.front();
                unused.erase(unused.begin());
                sol.routes[ri[ip]].depot = nd;
                used.insert(nd);
                ip++;
            }
            calculate_cost(sol);
        }
    }
    return sol;
}


// ================================================================================================ timers
static double now_cpu() { timespec t; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
static double now_wall() { timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }

// ================================================================================================ search settings
// tunable constants (command-line flags; defaults = the values the engine always used, so results are unchanged unless a flag is given)
static int g_it_div = 5, g_it_int = 3;                 // GRASP depot cycle: diversification / intensification iterations
static int g_win_up = 4, g_win_down = 4;               // SO: consecutive infeasible / feasible local optima before beta is changed
static double g_so_f1 = 1.5, g_so_f2 = 2.5;            // SO: beta is multiplied (divided) by one of these two factors, chosen at random
static double g_beta_min = 1e-6, g_beta_max = 1e9;     // SO: bounds of beta
static double g_beta0_scale = 1.0;                     // SO: beta0 = max(1, f(S0)/sum of demands) * scale
static bool g_so = false;          // strategic oscillation: penalised objective latency + beta * overload, best feasible solution returned
static bool g_first = false;       // neighbourhood selection: false = best improvement (Silva et al. 2012), true = first improvement
static bool g_random = true;       // neighbourhood order: true = RVND (random order), false = fixed order (classic VND)
static bool g_check = false;       // debugging: verify every accepted move against a from-scratch evaluation
static double g_beta = 0.0;        // current penalty weight (SO)
static const double EPS_IMP = 1e-6;

// granular neighbourhoods (--gran D, after Toth & Vigo 2003; D = 0 switches them off and leaves every result unchanged).  For every customer the D
// nearest customers are listed (ties by index); a move between two routes is evaluated only if it creates at least one edge between two customers
// that are neighbours in this sense (symmetric: u in N(v) or v in N(u)) or an edge that touches a depot.  Moves inside one route and the depot-level
// operators are not restricted.  swapstar considers a pair (a, b) only if a and b are neighbours.
static int g_gran = 0;
static int g_nn = 0;
static vector<unsigned char> g_near;
static inline bool nearc(int u, int v) { return u < 0 || v < 0 || g_near[(size_t)u * g_nn + v] != 0; }   // -1 = depot
static void build_gran(const Inst &I, int delta) {
    const int n = I.n, m = I.m;
    g_nn = n;
    if (delta <= 0 || delta >= n - 1) { g_gran = 0; g_near.clear(); return; }      // D >= n-1: every customer is a neighbour, nothing to restrict
    g_gran = delta;
    g_near.assign((size_t)n * n, 0);
    vector<int> idx;
    for (int c = 0; c < n; c++) {
        idx.clear();
        for (int o = 0; o < n; o++) if (o != c) idx.push_back(o);
        std::sort(idx.begin(), idx.end(), [&](int a, int b) {
            const double da = I.d(m + c, m + a), db = I.d(m + c, m + b);
            return da < db || (da == db && a < b);
        });
        for (int k = 0; k < delta; k++) { g_near[(size_t)c * n + idx[k]] = 1; g_near[(size_t)idx[k] * n + c] = 1; }
    }
}

static inline double ovalue(double lat, double load) {
    if (!g_so) return lat;
    double v = load - G->Q;
    return v > 0.0 ? lat + g_beta * v : lat;
}
// a load is acceptable if SO is on, or it respects the capacity (same tolerance as check_validity), or it does not get worse
static inline bool okload(double nl, double ol) { return g_so || nl <= G->Q + 1e-4 || nl <= ol; }

// ================================================================================================ re-optimisation data structures
// Silva, Subramanian, Vidal, Ochi (2012), EJOR 221(3):513-520, Proposition 1.  For a visit sequence sigma:
//   T = duration, C = sum of the arrival times when the sequence starts at time 0, W = number of customers.
//   sigma (+) sigma' : T = T + t(last, first') + T',  C = C + W' (T + t) + C',  W = W + W'
// Any move built from a bounded number of sub-sequences is evaluated with a bounded number of concatenations: O(1).
struct Seg { double T, C; int W, f, l; };
static inline Seg seg_node(int g, int w) { Seg s; s.T = 0.0; s.C = 0.0; s.W = w; s.f = g; s.l = g; return s; }
static inline Seg cat(const Seg &a, const Seg &b) {
    const double t = a.T + G->d(a.l, b.f);
    Seg r;
    r.T = t + b.T;
    r.C = a.C + (double)b.W * t + b.C;
    r.W = a.W + b.W;
    r.f = a.f;
    r.l = b.l;
    return r;
}

struct RT {                       // one route with its re-optimisation tables (rebuilt in O(L^2) whenever the route changes)
    int depot = 0, L = 0;
    double load = 0, lat = 0;
    vector<int> p;
    vector<double> P;             // P[k] = demand of the first k customers
    vector<Seg> F, B;             // F[i*L+j] = customers i..j in route order, B[i*L+j] = the same customers reversed
    void build() {
        L = (int)p.size();
        const int m = G->m;
        P.assign(L + 1, 0.0);
        for (int i = 0; i < L; i++) P[i + 1] = P[i] + G->dem[p[i]];
        load = P[L];
        F.resize((size_t)L * L);
        B.resize((size_t)L * L);
        for (int i = 0; i < L; i++) F[(size_t)i * L + i] = B[(size_t)i * L + i] = seg_node(m + p[i], 1);
        for (int i = 0; i < L; i++)
            for (int j = i + 1; j < L; j++) {
                F[(size_t)i * L + j] = cat(F[(size_t)i * L + j - 1], F[(size_t)j * L + j]);
                B[(size_t)i * L + j] = cat(F[(size_t)j * L + j], B[(size_t)i * L + j - 1]);
            }
        lat = cat(seg_node(depot, 0), F[L - 1]).C;
    }
};
struct State {
    vector<RT> rt;
    double beta = 1.0, tot = 0.0;
    vector<double> base;          // penalised value of every route (refreshed before every operator call)
};
static void state_from(const Sol &s, State &S) {
    S.rt.clear();
    for (auto &r : s.routes) {
        if (r.path.empty()) continue;
        RT t;
        t.depot = r.depot;
        t.p = r.path;
        t.build();
        S.rt.push_back(std::move(t));
    }
    S.tot = 0.0;
    for (auto &t : S.rt) S.tot += t.lat;
}
static Sol sol_from(const State &S) {         // cost is recomputed from scratch (direct sum of arrival times)
    Sol s;
    for (auto &t : S.rt) {
        Route r;
        r.depot = t.depot;
        r.path = t.p;
        r.load = path_load(r.path.data(), r.path.size());
        s.routes.push_back(r);
    }
    calculate_cost(s);
    return s;
}
static bool state_feasible(const State &S) {
    for (auto &t : S.rt) if (t.load > G->Q + 1e-4) return false;
    return true;
}

// ================================================================================================ moves as recipes
// A candidate is described by the new content of at most two routes; every route is a concatenation of at most 6 pieces
// (a piece = customers i..j of route r, optionally reversed).  The same description is used to evaluate the move in O(1)
// and to apply it, so evaluation and application cannot disagree.
struct Pc { int r, i, j; bool rev; };
struct Rec {
    int depot = 0, n = 0;
    Pc pc[6];
    inline void add(int r, int i, int j, bool rev = false) { if (i <= j) { pc[n].r = r; pc[n].i = i; pc[n].j = j; pc[n].rev = rev; n++; } }
};
static inline double rec_lat(const State &S, const Rec &R) {
    Seg a = seg_node(R.depot, 0);
    for (int k = 0; k < R.n; k++) {
        const Pc &q = R.pc[k];
        const RT &t = S.rt[q.r];
        a = cat(a, q.rev ? t.B[(size_t)q.i * t.L + q.j] : t.F[(size_t)q.i * t.L + q.j]);
    }
    return a.C;
}
enum { K_REC = 0, K_DS = 1 };
struct Cand {
    int kind = K_REC, nr = 0, r[2] = {0, 0}, a = 0, b = 0;
    Rec rec[2];
};
static inline Cand mk1(int r1, const Rec &a) { Cand c; c.kind = K_REC; c.nr = 1; c.r[0] = r1; c.rec[0] = a; return c; }
static inline Cand mk2(int r1, const Rec &a, int r2, const Rec &b) {
    Cand c; c.kind = K_REC; c.nr = 2; c.r[0] = r1; c.r[1] = r2; c.rec[0] = a; c.rec[1] = b; return c;
}
struct Best { double delta; bool have, first, done; Cand c; };
#define OFFER(DELTA, CAND) do { double _d = (DELTA); if (_d < B.delta) { B.delta = _d; B.c = (CAND); B.have = true; if (B.first) { B.done = true; return; } } } while (0)

static void apply_cand(State &S, const Cand &C) {
    if (C.kind == K_DS) {
        for (auto &t : S.rt) if (t.depot == C.a) { t.depot = C.b; t.build(); }
    } else {
        vector<int> np[2];
        for (int e = 0; e < C.nr; e++) {
            const Rec &R = C.rec[e];
            for (int k = 0; k < R.n; k++) {
                const Pc &q = R.pc[k];
                const vector<int> &src = S.rt[q.r].p;
                if (q.rev) for (int x = q.j; x >= q.i; x--) np[e].push_back(src[x]);
                else for (int x = q.i; x <= q.j; x++) np[e].push_back(src[x]);
            }
        }
        for (int e = 0; e < C.nr; e++) {
            RT &t = S.rt[C.r[e]];
            t.depot = C.rec[e].depot;
            t.p.swap(np[e]);
            t.build();
        }
    }
    S.tot = 0.0;
    for (auto &t : S.rt) S.tot += t.lat;
}

// ================================================================================================ neighbourhoods
// Every operator scans its complete neighbourhood and keeps the best (or, with --select first, the first) improving move.
// Invariants kept by all operators: no route becomes empty, the number of routes is unchanged, the open-depot set is unchanged
// except by `ds`, every customer is in exactly one route.
//   relocate / oropt2 / oropt3 : a block of k = 1/2/3 consecutive customers moves to another position of its route or into another
//                                route, forward or reversed
//   swapKL (11 21 22 31 32)    : a block of K customers and a block of L customers are exchanged (inter-route and intra-route,
//                                every orientation)
//   2opt                       : reversal of a segment of one route
//   2opt*                      : the tails of two routes are exchanged
//   swapstar                   : one customer of each of two routes, each re-inserted at its best position of the other route
//   dexch                      : two routes with different depots exchange their depots
//   rdepot                     : a route moves to another open depot (forward or reversed), the open-depot set is unchanged
//   ds                         : one open depot is replaced by a closed one, all its routes move with it

static void op_oropt(const State &S, Best &B, long &ev, int k) {
    const int R = (int)S.rt.size();
    for (int r1 = 0; r1 < R; r1++) {
        const RT &A = S.rt[r1];
        for (int i = 0; i + k <= A.L; i++) {
            const double sl = A.P[i + k] - A.P[i];
            if (A.L > k) {                                                             // ---- into another route
                Rec ra; ra.depot = A.depot; ra.add(r1, 0, i - 1); ra.add(r1, i + k, A.L - 1);
                const double v1 = ovalue(rec_lat(S, ra), A.load - sl);
                for (int r2 = 0; r2 < R; r2++) {
                    if (r2 == r1) continue;
                    const RT &Bt = S.rt[r2];
                    const double l2 = Bt.load + sl;
                    if (!okload(l2, Bt.load)) continue;
                    const double rest = v1 - S.base[r1] - S.base[r2];
                    for (int rev = 0; rev <= (k > 1 ? 1 : 0); rev++) {
                        const int gf = rev ? A.p[i + k - 1] : A.p[i], gl = rev ? A.p[i] : A.p[i + k - 1];      // first / last customer of the moved segment
                        for (int p = 0; p <= Bt.L; p++) {
                            if (g_gran && !(nearc(p > 0 ? Bt.p[p - 1] : -1, gf) || nearc(gl, p < Bt.L ? Bt.p[p] : -1))) continue;
                            Rec rb; rb.depot = Bt.depot; rb.add(r2, 0, p - 1); rb.add(r1, i, i + k - 1, rev); rb.add(r2, p, Bt.L - 1);
                            ev++;
                            OFFER(rest + ovalue(rec_lat(S, rb), l2), mk2(r1, ra, r2, rb));
                        }
                    }
                }
            }
            for (int rev = 0; rev <= (k > 1 ? 1 : 0); rev++)                           // ---- inside the route
                for (int q = 0; q <= A.L; q++) {
                    if (q >= i && q <= i + k) continue;
                    Rec rc; rc.depot = A.depot;
                    if (q < i) { rc.add(r1, 0, q - 1); rc.add(r1, i, i + k - 1, rev); rc.add(r1, q, i - 1); rc.add(r1, i + k, A.L - 1); }
                    else { rc.add(r1, 0, i - 1); rc.add(r1, i + k, q - 1); rc.add(r1, i, i + k - 1, rev); rc.add(r1, q, A.L - 1); }
                    ev++;
                    OFFER(ovalue(rec_lat(S, rc), A.load) - S.base[r1], mk1(r1, rc));
                }
        }
    }
}

static void op_exch(const State &S, Best &B, long &ev, int k1, int k2) {
    const int R = (int)S.rt.size();
    for (int r1 = 0; r1 < R; r1++) {                                                   // ---- between two routes
        const RT &A = S.rt[r1];
        for (int r2 = 0; r2 < R; r2++) {
            if (r2 == r1 || (k1 == k2 && r2 < r1)) continue;
            const RT &Bt = S.rt[r2];
            for (int i = 0; i + k1 <= A.L; i++) {
                const double s1 = A.P[i + k1] - A.P[i];
                for (int j = 0; j + k2 <= Bt.L; j++) {
                    const double s2 = Bt.P[j + k2] - Bt.P[j];
                    const double l1 = A.load - s1 + s2, l2 = Bt.load - s2 + s1;
                    if (!okload(l1, A.load) || !okload(l2, Bt.load)) continue;
                    for (int rv1 = 0; rv1 <= (k1 > 1 ? 1 : 0); rv1++)
                        for (int rv2 = 0; rv2 <= (k2 > 1 ? 1 : 0); rv2++) {
                            if (g_gran) {                                                    // four new joints: both ends of both moved segments
                                const int s1f = rv1 ? A.p[i + k1 - 1] : A.p[i], s1l = rv1 ? A.p[i] : A.p[i + k1 - 1];
                                const int s2f = rv2 ? Bt.p[j + k2 - 1] : Bt.p[j], s2l = rv2 ? Bt.p[j] : Bt.p[j + k2 - 1];
                                if (!(nearc(i > 0 ? A.p[i - 1] : -1, s2f) || nearc(s2l, i + k1 < A.L ? A.p[i + k1] : -1) ||
                                      nearc(j > 0 ? Bt.p[j - 1] : -1, s1f) || nearc(s1l, j + k2 < Bt.L ? Bt.p[j + k2] : -1))) continue;
                            }
                            Rec ra; ra.depot = A.depot; ra.add(r1, 0, i - 1); ra.add(r2, j, j + k2 - 1, rv2); ra.add(r1, i + k1, A.L - 1);
                            Rec rb; rb.depot = Bt.depot; rb.add(r2, 0, j - 1); rb.add(r1, i, i + k1 - 1, rv1); rb.add(r2, j + k2, Bt.L - 1);
                            ev++;
                            OFFER(ovalue(rec_lat(S, ra), l1) + ovalue(rec_lat(S, rb), l2) - S.base[r1] - S.base[r2], mk2(r1, ra, r2, rb));
                        }
                }
            }
        }
    }
    for (int r1 = 0; r1 < R; r1++) {                                                   // ---- inside one route
        const RT &A = S.rt[r1];
        for (int ord = 0; ord < (k1 == k2 ? 1 : 2); ord++) {
            const int ka = ord == 0 ? k1 : k2, kb = ord == 0 ? k2 : k1;
            for (int i = 0; i + ka <= A.L; i++)
                for (int j = i + ka; j + kb <= A.L; j++)
                    for (int rva = 0; rva <= (ka > 1 ? 1 : 0); rva++)
                        for (int rvb = 0; rvb <= (kb > 1 ? 1 : 0); rvb++) {
                            Rec rc; rc.depot = A.depot;
                            rc.add(r1, 0, i - 1); rc.add(r1, j, j + kb - 1, rvb); rc.add(r1, i + ka, j - 1); rc.add(r1, i, i + ka - 1, rva); rc.add(r1, j + kb, A.L - 1);
                            ev++;
                            OFFER(ovalue(rec_lat(S, rc), A.load) - S.base[r1], mk1(r1, rc));
                        }
        }
    }
}

static void op_2opt(const State &S, Best &B, long &ev) {
    for (int r1 = 0; r1 < (int)S.rt.size(); r1++) {
        const RT &A = S.rt[r1];
        for (int i = 0; i < A.L; i++)
            for (int j = i + 1; j < A.L; j++) {
                Rec rc; rc.depot = A.depot; rc.add(r1, 0, i - 1); rc.add(r1, i, j, true); rc.add(r1, j + 1, A.L - 1);
                ev++;
                OFFER(ovalue(rec_lat(S, rc), A.load) - S.base[r1], mk1(r1, rc));
            }
    }
}

static void op_2optstar(const State &S, Best &B, long &ev) {
    const int R = (int)S.rt.size();
    for (int r1 = 0; r1 < R; r1++)
        for (int r2 = r1 + 1; r2 < R; r2++) {
            const RT &A = S.rt[r1], &Bt = S.rt[r2];
            for (int i = 0; i <= A.L; i++)
                for (int j = 0; j <= Bt.L; j++) {
                    if (i == 0 && j == 0) continue;                       // = dexch
                    if (i == A.L && j == Bt.L) continue;                  // identity
                    if (i == 0 && j == Bt.L) continue;                    // first route would be empty
                    if (j == 0 && i == A.L) continue;                     // second route would be empty
                    if (g_gran && !(nearc(i > 0 ? A.p[i - 1] : -1, j < Bt.L ? Bt.p[j] : -1) || nearc(j > 0 ? Bt.p[j - 1] : -1, i < A.L ? A.p[i] : -1))) continue;
                    const double l1 = A.P[i] + (Bt.load - Bt.P[j]), l2 = Bt.P[j] + (A.load - A.P[i]);
                    if (!okload(l1, A.load) || !okload(l2, Bt.load)) continue;
                    Rec ra; ra.depot = A.depot; ra.add(r1, 0, i - 1); ra.add(r2, j, Bt.L - 1);
                    Rec rb; rb.depot = Bt.depot; rb.add(r2, 0, j - 1); rb.add(r1, i, A.L - 1);
                    ev++;
                    OFFER(ovalue(rec_lat(S, ra), l1) + ovalue(rec_lat(S, rb), l2) - S.base[r1] - S.base[r2], mk2(r1, ra, r2, rb));
                }
        }
}

// recipe of route rx (length Lx) without its customer at `pos`, with customer jy of route ry inserted before original index q (q != pos+1)
static inline void mk_swapins(Rec &rc, int depot, int rx, int Lx, int pos, int q, int ry, int jy) {
    rc.depot = depot; rc.n = 0;
    if (q <= pos) { rc.add(rx, 0, q - 1); rc.add(ry, jy, jy); rc.add(rx, q, pos - 1); rc.add(rx, pos + 1, Lx - 1); }
    else { rc.add(rx, 0, pos - 1); rc.add(rx, pos + 1, q - 1); rc.add(ry, jy, jy); rc.add(rx, q, Lx - 1); }
}
static void op_swapstar(const State &S, Best &B, long &ev) {
    const int R = (int)S.rt.size();
    for (int r1 = 0; r1 < R; r1++)
        for (int r2 = r1 + 1; r2 < R; r2++) {
            const RT &A = S.rt[r1], &Bt = S.rt[r2];
            for (int i = 0; i < A.L; i++) {
                const double da = G->dem[A.p[i]];
                for (int j = 0; j < Bt.L; j++) {
                    if (g_gran && !nearc(A.p[i], Bt.p[j])) continue;
                    const double db = G->dem[Bt.p[j]];
                    const double l1 = A.load - da + db, l2 = Bt.load - db + da;
                    if (!okload(l1, A.load) || !okload(l2, Bt.load)) continue;
                    double b1 = INFINITY, b2 = INFINITY;
                    int q1 = -1, q2 = -1;
                    Rec rc;
                    for (int q = 0; q <= A.L; q++) {                      // best place of b in route 1 without a
                        if (q == i + 1) continue;
                        mk_swapins(rc, A.depot, r1, A.L, i, q, r2, j);
                        const double v = rec_lat(S, rc);
                        if (v < b1) { b1 = v; q1 = q; }
                    }
                    for (int q = 0; q <= Bt.L; q++) {                     // best place of a in route 2 without b
                        if (q == j + 1) continue;
                        mk_swapins(rc, Bt.depot, r2, Bt.L, j, q, r1, i);
                        const double v = rec_lat(S, rc);
                        if (v < b2) { b2 = v; q2 = q; }
                    }
                    ev++;
                    const double d = ovalue(b1, l1) + ovalue(b2, l2) - S.base[r1] - S.base[r2];
                    if (d < B.delta) {
                        Rec ra, rb;
                        mk_swapins(ra, A.depot, r1, A.L, i, q1, r2, j);
                        mk_swapins(rb, Bt.depot, r2, Bt.L, j, q2, r1, i);
                        OFFER(d, mk2(r1, ra, r2, rb));
                    }
                }
            }
        }
}

static void op_dexch(const State &S, Best &B, long &ev) {
    const int R = (int)S.rt.size();
    for (int r1 = 0; r1 < R; r1++)
        for (int r2 = r1 + 1; r2 < R; r2++) {
            const RT &A = S.rt[r1], &Bt = S.rt[r2];
            if (A.depot == Bt.depot) continue;
            Rec ra; ra.depot = Bt.depot; ra.add(r1, 0, A.L - 1);
            Rec rb; rb.depot = A.depot; rb.add(r2, 0, Bt.L - 1);
            ev++;
            OFFER(ovalue(rec_lat(S, ra), A.load) + ovalue(rec_lat(S, rb), Bt.load) - S.base[r1] - S.base[r2], mk2(r1, ra, r2, rb));
        }
}

static void op_rdepot(const State &S, Best &B, long &ev) {
    const int R = (int)S.rt.size();
    vector<int> cnt(G->m, 0);
    for (auto &t : S.rt) cnt[t.depot]++;
    for (int r1 = 0; r1 < R; r1++) {
        const RT &A = S.rt[r1];
        if (cnt[A.depot] < 2) continue;                                    // the depot must stay open
        for (int d = 0; d < G->m; d++) {
            if (d == A.depot || cnt[d] == 0) continue;                     // only to another OPEN depot
            for (int rev = 0; rev <= 1; rev++) {
                if (rev && A.L < 2) continue;
                Rec rc; rc.depot = d; rc.add(r1, 0, A.L - 1, rev);
                ev++;
                OFFER(ovalue(rec_lat(S, rc), A.load) - S.base[r1], mk1(r1, rc));
            }
        }
    }
}

static void op_ds(const State &S, Best &B, long &ev) {
    const int m = G->m;
    vector<int> cnt(m, 0);
    for (auto &t : S.rt) cnt[t.depot]++;
    for (int o = 0; o < m; o++) {
        if (cnt[o] == 0) continue;
        for (int c = 0; c < m; c++) {
            if (cnt[c] != 0) continue;
            double d = 0.0;
            for (auto &t : S.rt)
                if (t.depot == o) d += cat(seg_node(c, 0), t.F[t.L - 1]).C - t.lat;     // loads do not change: only latencies
            ev++;
            Cand cd; cd.kind = K_DS; cd.a = o; cd.b = c;
            OFFER(d, cd);
        }
    }
}

// ================================================================================================ neighbourhood table
struct OpDef { const char *name; int kind, a, b; };
enum { OK_OROPT = 0, OK_EXCH, OK_2OPT, OK_2OPTSTAR, OK_SWAPSTAR, OK_DEXCH, OK_RDEPOT, OK_DS };
static const OpDef OPS_ALL[] = {
    {"relocate", OK_OROPT, 1, 0}, {"oropt2", OK_OROPT, 2, 0}, {"oropt3", OK_OROPT, 3, 0},
    {"swap11", OK_EXCH, 1, 1}, {"swap21", OK_EXCH, 2, 1}, {"swap22", OK_EXCH, 2, 2}, {"swap31", OK_EXCH, 3, 1}, {"swap32", OK_EXCH, 3, 2},
    {"2opt", OK_2OPT, 0, 0}, {"2opt*", OK_2OPTSTAR, 0, 0}, {"swapstar", OK_SWAPSTAR, 0, 0},
    {"dexch", OK_DEXCH, 0, 0}, {"rdepot", OK_RDEPOT, 0, 0}, {"ds", OK_DS, 0, 0}};
static const int NALL = (int)(sizeof(OPS_ALL) / sizeof(OPS_ALL[0]));
struct OpStat { long calls = 0, evals = 0, applied = 0; double gain_lat = 0, gain_obj = 0, cpu = 0; };
static OpStat OSTAT[NALL];
static vector<int> g_pool;                   // indices into OPS_ALL, in the order given on the command line

static string preset_ops(const string &s) {
    if (s == "legacy5") return "relocate,swap11,2opt,swap22,swap21";                                         // ~ VND0 (5 neighbourhoods)
    if (s == "zou") return "relocate,swap11,2opt,oropt2,swap21,swap22,swapstar,dexch";                       // ~ VNDZou without DS
    if (s == "full") return "relocate,oropt2,oropt3,swap11,swap21,swap22,swap31,swap32,2opt,2opt*,swapstar,dexch,rdepot,ds";
    return s;
}
static int op_index(const string &nm0) {
    const string nm = (nm0 == "2optstar") ? string("2opt*") : nm0;        // '2optstar' = shell/file-name safe alias of '2opt*'
    for (int i = 0; i < NALL; i++) if (nm == OPS_ALL[i].name) return i;
    return -1;
}
static void parse_ops(const string &spec) {
    g_pool.clear();
    std::stringstream ss(spec);
    string tok;
    while (std::getline(ss, tok, ',')) {
        if (tok.empty()) continue;
        int k = op_index(tok);
        if (k < 0) die("unknown operator '" + tok + "' (legacy5 | zou | full | list of: relocate oropt2 oropt3 swap11 swap21 swap22 swap31 swap32 2opt 2opt* swapstar dexch rdepot ds)");
        if (std::find(g_pool.begin(), g_pool.end(), k) == g_pool.end()) g_pool.push_back(k);
    }
    if (g_pool.empty()) die("empty operator pool");
}

static void prep_base(State &S) {
    g_beta = S.beta;
    S.base.resize(S.rt.size());
    for (size_t r = 0; r < S.rt.size(); r++) S.base[r] = ovalue(S.rt[r].lat, S.rt[r].load);
}
static double penalised_total(const State &S) {        // from-scratch value with the DIRECT latency evaluation (debug check)
    double v = 0.0;
    for (auto &t : S.rt) v += ovalue(eval_lat(t.depot, t.p.data(), t.p.size()), path_load(t.p.data(), t.p.size()));
    return v;
}
// one call of an operator: scans the neighbourhood, applies the best (or first) improving move; returns true if a move was applied
static bool run_op(State &S, int oi) {
    const OpDef &d = OPS_ALL[oi];
    OpStat &st = OSTAT[oi];
    const double t0 = now_cpu();
    st.calls++;
    prep_base(S);
    Best B;
    B.delta = -EPS_IMP; B.have = false; B.first = g_first; B.done = false;
    long ev = 0;
    switch (d.kind) {
        case OK_OROPT: op_oropt(S, B, ev, d.a); break;
        case OK_EXCH: op_exch(S, B, ev, d.a, d.b); break;
        case OK_2OPT: op_2opt(S, B, ev); break;
        case OK_2OPTSTAR: op_2optstar(S, B, ev); break;
        case OK_SWAPSTAR: op_swapstar(S, B, ev); break;
        case OK_DEXCH: op_dexch(S, B, ev); break;
        case OK_RDEPOT: op_rdepot(S, B, ev); break;
        case OK_DS: op_ds(S, B, ev); break;
    }
    st.evals += ev;
    bool imp = false;
    if (B.have) {
        const double lat0 = S.tot;
        double before = 0.0;
        if (g_check) before = penalised_total(S);
        apply_cand(S, B.c);
        st.applied++;
        st.gain_obj += -B.delta;
        st.gain_lat += lat0 - S.tot;
        imp = true;
        if (g_check) {
            const double after = penalised_total(S);
            const double err = std::fabs((after - before) - B.delta), scale = std::max(1.0, std::fabs(before));
            double dl = 0.0;
            for (auto &t : S.rt) dl += eval_lat(t.depot, t.p.data(), t.p.size());
            if (err > 1e-7 * scale || std::fabs(dl - S.tot) > 1e-7 * scale) {
                fprintf(stderr, "llrp_fast: CHECK FAILED in %s: predicted delta %.12g, actual %.12g, engine total %.12g, direct total %.12g\n",
                        d.name, B.delta, after - before, S.tot, dl);
                exit(3);
            }
        }
    }
    st.cpu += now_cpu() - t0;
    return imp;
}

// ================================================================================================ local search (RVND / VND, optional SO)
static double initial_beta(Sol &sol) {
    double total_demand = np_pairwise_sum(G->dem.data(), G->dem.size());
    calculate_cost(sol);
    if (total_demand <= 0) return 1.0 * g_beta0_scale;
    return std::max(1.0, sol.cost / total_demand) * g_beta0_scale;
}
struct Track {                                  // strategic-oscillation bookkeeping of one local search
    int fc = 0, ic = 0;
    bool have = false;
    Sol best;
    double best_cost = INFINITY;
};
static void after_accept(State &S, Track &T) {
    if (!g_so) return;
    if (state_feasible(S)) {
        T.fc++; T.ic = 0;
        if (S.tot < T.best_cost) { T.best = sol_from(S); T.have = true; T.best_cost = S.tot; }
    } else { T.ic++; T.fc = 0; }
    if (T.ic >= g_win_up) { S.beta = std::min(g_beta_max, S.beta * (RNG.choice(2) == 0 ? g_so_f1 : g_so_f2)); T.ic = 0; }
    if (T.fc >= g_win_down) { S.beta = std::max(g_beta_min, S.beta / (RNG.choice(2) == 0 ? g_so_f1 : g_so_f2)); T.fc = 0; }
}
static void descent(State &S, Track &T) {
    if (g_random) {                              // RVND: random neighbourhood among the not yet exhausted ones; list refilled after every improvement
        vector<int> NL = g_pool;
        while (!NL.empty()) {
            const int idx = RNG.choice((int)NL.size());
            if (run_op(S, NL[idx])) { after_accept(S, T); NL = g_pool; }
            else NL.erase(NL.begin() + idx);
        }
    } else {                                     // classic VND: after an improvement go back to the first neighbourhood
        size_t k = 0;
        while (k < g_pool.size()) {
            if (run_op(S, g_pool[k])) { after_accept(S, T); k = 0; } else k++;
        }
    }
}
// returns the local optimum (SO: the best feasible solution met during the descent)
static Sol local_search(const Sol &start) {
    State S;
    state_from(start, S);
    Track T;
    if (g_so) {
        Sol tmp = start;
        S.beta = initial_beta(tmp);
        if (state_feasible(S)) { T.best = sol_from(S); T.have = true; T.best_cost = S.tot; }
    }
    descent(S, T);
    if (g_so && T.have) return T.best;
    return sol_from(S);
}

// ILS (optional): double-bridge perturbation of the best local optimum of the GRASP iteration, local search, acceptance of improvements only,
// stop after `ils` consecutive perturbations without improvement (Silva et al. 2012, Algorithm 1, lines 8-16)
static bool perturb_double_bridge(Sol &s) {
    vector<int> cand;
    for (size_t r = 0; r < s.routes.size(); r++) if (s.routes[r].path.size() >= 4) cand.push_back((int)r);
    if (cand.empty()) return false;
    Route &R = s.routes[cand[RNG.choice((int)cand.size())]];
    const int L = (int)R.path.size();
    vector<int> pop;
    for (int x = 1; x < L; x++) pop.push_back(x);
    vector<int> cut = RNG.sample(pop, 3);
    std::sort(cut.begin(), cut.end());
    vector<int> np;
    np.insert(np.end(), R.path.begin(), R.path.begin() + cut[0]);                       // A
    np.insert(np.end(), R.path.begin() + cut[1], R.path.begin() + cut[2]);              // C
    np.insert(np.end(), R.path.begin() + cut[0], R.path.begin() + cut[1]);              // B
    np.insert(np.end(), R.path.begin() + cut[2], R.path.end());                         // D
    R.path = np;
    R.load = path_load(R.path.data(), R.path.size());
    return true;
}
static int g_ils = 0;
// ---- v7: in-run route pool + SP recombination (all behind --pool-sp; default off -> identical to v6)
static bool g_pool_on = false;
static int g_pool_src = 1;                 // 1: final solution of each GRASP iteration;  2: + every feasible ILS local optimum within (1+theta) of the ILS best
static double g_pool_tl = 3.0;             // CPU seconds per SP call (also reserved at the end of the budget for the final call)
static double g_pool_theta = 0.02;
static int g_pool_sets = 3, g_pool_first = 8;
static long g_pool_nodes = 300000;
static psp::Pool *PL = nullptr;
static std::map<vector<int>, double> g_set_best;           // open depot set -> best cost seen
static void pool_add_sol(const Sol &s) {                   // s feasible, cost computed
    for (auto &r : s.routes) if (!r.path.empty()) PL->add(r.depot, r.path);
    auto it = g_set_best.find(s.open);
    if (it == g_set_best.end() || s.cost < it->second) g_set_best[s.open] = s.cost;
}
static Sol local_search_ils(const Sol &start) {
    Sol best = local_search(start);
    if (g_ils <= 0) return best;
    int cnt = 0;
    while (cnt < g_ils) {
        Sol p = best;
        if (!perturb_double_bridge(p)) break;
        Sol res = local_search(p);
        const bool vres = check_validity(res);
        if (vres && g_pool_on && g_pool_src >= 2 && res.cost <= best.cost * (1.0 + g_pool_theta)) pool_add_sol(res);
        if (vres && res.cost < best.cost - 1e-9) { best = res; cnt = 0; }
        else cnt++;
    }
    return best;
}

// ================================================================================================ fast construction (ECWA)
// Same construction as ECWA() (Clarke-Wright-like merging of routes with a restricted candidate list of rcl_size best merges, then
// repair of the route count and forcing of exactly Ng depots), but every merge candidate is evaluated in O(1) with the sub-sequence
// concatenation instead of re-scanning both routes, and only the rcl_size best candidates are kept instead of sorting all of them.
// The candidates are enumerated in the same order, ties keep that order (stable), the random draw is the same.
struct RS { int depot; vector<int> path; double load; Seg seg; };       // seg = the customers of the route (without the depot)
struct MC { double delta; int i, j, ord, dep; };
static Sol ECWA_fast(vector<int> allowed, int rcl_size) {
    const Inst &I = *G;
    Sol sol;
    {
        vector<int> u;
        for (int d : allowed) if (std::find(u.begin(), u.end(), d) == u.end()) u.push_back(d);
        allowed = u;
        int max_open = std::max(1, std::min(I.Ng, I.m));
        if ((int)allowed.size() > max_open) allowed = RNG.sample(allowed, max_open);
        if (allowed.empty()) die("empty allowed depot list");
    }
    vector<RS> rs;
    for (int c = 0; c < I.n; c++) {
        int cg = I.m + c, best = allowed[0];
        double bd = I.d(allowed[0], cg);
        for (size_t k = 1; k < allowed.size(); k++) {
            double dd = I.d(allowed[k], cg);
            if (dd < bd) { bd = dd; best = allowed[k]; }
        }
        RS r; r.depot = best; r.path.assign(1, c); r.load = I.dem[c]; r.seg = seg_node(cg, 1);
        rs.push_back(r);
    }
    const int target = I.Nv, K = std::max(1, rcl_size);
    vector<MC> top;
    while ((int)rs.size() > target) {
        const int R = (int)rs.size();
        top.clear();
        long ncand = 0;
        for (int i = 0; i < R; i++) {
            const double oi = cat(seg_node(rs[i].depot, 0), rs[i].seg).C;
            for (int j = 0; j < R; j++) {
                if (i == j) continue;
                if (rs[i].load + rs[j].load > I.Q + 1e-4) continue;
                const double old_obj = oi + cat(seg_node(rs[j].depot, 0), rs[j].seg).C;
                int cdep[2], nd = 0;
                cdep[nd++] = rs[i].depot;
                if (rs[j].depot != rs[i].depot) cdep[nd++] = rs[j].depot;
                for (int di = 0; di < nd; di++)
                    for (int ord = 0; ord < 2; ord++) {
                        const Seg &a = ord == 0 ? rs[i].seg : rs[j].seg, &b = ord == 0 ? rs[j].seg : rs[i].seg;
                        const double tot = cat(cat(seg_node(cdep[di], 0), a), b).C;
                        const double delta = tot - old_obj;
                        ncand++;
                        size_t pos = top.size();
                        while (pos > 0 && top[pos - 1].delta > delta) pos--;           // after the last element with delta <= new delta (stable)
                        if (pos >= (size_t)K) continue;
                        MC c; c.delta = delta; c.i = i; c.j = j; c.ord = ord; c.dep = cdep[di];
                        top.insert(top.begin() + pos, c);
                        if ((int)top.size() > K) top.pop_back();
                    }
            }
        }
        if (ncand == 0) break;
        const int actual = (int)std::min<long>(ncand, K);
        const MC ch = top[RNG.choice(actual)];
        RS nr;
        const RS &r1 = rs[ch.i], &r2 = rs[ch.j];
        nr.depot = ch.dep;
        const RS &ra = ch.ord == 0 ? r1 : r2, &rb = ch.ord == 0 ? r2 : r1;
        nr.path = ra.path;
        nr.path.insert(nr.path.end(), rb.path.begin(), rb.path.end());
        nr.load = r1.load + r2.load;
        nr.seg = cat(ra.seg, rb.seg);
        const int hi = std::max(ch.i, ch.j), lo = std::min(ch.i, ch.j);
        rs.erase(rs.begin() + hi);
        rs.erase(rs.begin() + lo);
        rs.push_back(nr);
    }
    for (auto &r : rs) { Route o; o.depot = r.depot; o.path = r.path; o.load = r.load; sol.routes.push_back(o); }
    calculate_cost(sol);
    repair_route_count_by_relocation(sol);
    if (!g_atmost) {
        int req = I.Ng;
        std::set<int> used;
        for (auto &r : sol.routes) if (!r.path.empty()) used.insert(r.depot);
        if ((int)used.size() < req) {
            vector<int> unused;
            for (int d : allowed) if (!used.count(d)) unused.push_back(d);
            vector<int> ri(sol.routes.size());
            for (size_t i = 0; i < ri.size(); i++) ri[i] = (int)i;
            std::stable_sort(ri.begin(), ri.end(), [&](int a, int b) { return sol.routes[a].load < sol.routes[b].load; });
            size_t ip = 0;
            while ((int)used.size() < req && !unused.empty() && ip < ri.size()) {
                int nd = unused.front();
                unused.erase(unused.begin());
                sol.routes[ri[ip]].depot = nd;
                used.insert(nd);
                ip++;
            }
            calculate_cost(sol);
        }
    }
    return sol;
}
static bool g_ecwa_ref = false;
static Sol construct(const vector<int> &allowed, int rcl) { return g_ecwa_ref ? ECWA(allowed, rcl) : ECWA_fast(allowed, rcl); }

// ================================================================================================ depot layer (v6; ALL OFF by default -> bit-identical to v5)
// p-median lower bound of a depot set S:  LB(S) = sum over customers c of min_{d in S} dist(d, c).  Every route of a solution that opens only depots of S
// serves its customers in some order after leaving its depot; the arrival time at c is at least the straight-line distance (triangle inequality, no service
// times), so the latency of every solution restricted to S is >= LB(S).  The table sorts all C(m, Ng) subsets by LB (ascending, ties lexicographic).
//   --dpm-rank K[,eps]  D2: a diversification start set is drawn from the K smallest-LB sets with probability 1-eps and uniformly from all sets with
//                       probability eps (default eps 0.25; K = 0 or flag absent: uniform draw as in v5).
//   --dpm-prune         D1: a drawn start set with LB(S) >= incumbent cost is redrawn (no GRASP iteration is spent on it).  NOTE: this filters START sets
//                       only; the depot operators of the local search may still leave S.
//   --dpm-memory        D3: (a) a start set is used at most once per run (until every set has been used); (b) the elite depot set (best open set of any
//                       diversification iteration so far) is kept across cycles and is the start set of the intensification iterations.
// Not combinable with --atmost (the table is built for exactly min(Ng, m) open depots).
//   --dpm-tabu          v8 (EXPERIMENTAL, default off): converged-set tabu.  A cycle "converges" on the depot set of its best diversification solution (the set the
//                       intensification phase refines); that set (and the open set of the best intensification solution) goes on a tabu list for the rest of the run.
//                       Later start-set draws skip tabu sets (top-K and uniform draws); when the diversification phase of a later cycle ends on a tabu set,
//                       its intensification phase is skipped.  Not combinable with --dpm-memory.
//   --dpm-tabu-parts P  v8 (EXPERIMENTAL): with --dpm-tabu, which of the two rules is active: draw (start-set draws avoid tabu sets; intensification is never skipped),
//                       skip (draws unchanged; intensification skipped when the diversification phase ends on a tabu set) or both (default = plain --dpm-tabu).
static bool g_dpm_prune = false, g_dpm_mem = false, g_dpm_tabu = false;
static bool g_tabu_draw = true, g_tabu_skip = true, g_tabu_parts_set = false;    // v8: parts of --dpm-tabu (default both); --dpm-tabu-parts draw|skip|both
static int g_dpm_K = 0;
static double g_dpm_eps = 0.25;
static long g_dpm_cap = 200000;                       // largest number of subsets that is enumerated
struct Dpm {
    bool on = false;
    vector<vector<int>> sets;                         // sorted by lb
    vector<double> lb;
    vector<char> used;
    long used_count = 0;
    long draws = 0, top_draws = 0, uni_draws = 0, pruned = 0, mem_skips = 0, fallback = 0, resets = 0;
    double build_s = 0.0;
};
static Dpm DP;
struct DpmTabu {
    std::map<vector<int>, long> idx;                  // sorted depot set -> rank in DP.sets
    vector<char> flag;                                // tabu flag by rank
    long count = 0, adds = 0, skipped_int = 0, draw_skips = 0, resets = 0, cycles = 0;
    vector<std::pair<int, string>> events;            // (GRASP iteration, text) for the sidecar
};
static DpmTabu TB;
static string set_text(const vector<int> &v) { string s; for (size_t i = 0; i < v.size(); i++) { if (i) s += " "; s += std::to_string(v[i]); } return s; }
static bool tabu_has(vector<int> s) { std::sort(s.begin(), s.end()); auto it = TB.idx.find(s); return it != TB.idx.end() && TB.flag[it->second]; }
static void tabu_add(vector<int> s, int iter, const char *why) {
    std::sort(s.begin(), s.end());
    auto it = TB.idx.find(s);
    if (it == TB.idx.end() || TB.flag[it->second]) return;
    TB.flag[it->second] = 1; TB.count++; TB.adds++;
    TB.events.push_back({iter, string("add:") + why + ":" + set_text(s)});
}
static void dpm_build(const Inst &I) {
    const double t0 = now_cpu();
    const int k = std::max(1, std::min(I.Ng, I.m)), m = I.m, n = I.n;
    double ncomb = 1.0;
    for (int i = 1; i <= k; i++) ncomb = ncomb * (m - k + i) / i;
    if (ncomb > (double)g_dpm_cap) die("--dpm-*: C(" + std::to_string(m) + "," + std::to_string(k) + ") = " + std::to_string((long long)ncomb) + " subsets exceed --dpm-cap " + std::to_string(g_dpm_cap));
    vector<double> dc((size_t)m * n);
    for (int d = 0; d < m; d++) for (int c = 0; c < n; c++) dc[(size_t)d * n + c] = I.d(d, m + c);
    vector<vector<int>> sets;
    vector<double> lb;
    vector<int> idx(k);
    for (int i = 0; i < k; i++) idx[i] = i;
    for (;;) {
        double s = 0.0;
        for (int c = 0; c < n; c++) {
            double b = dc[(size_t)idx[0] * n + c];
            for (int j = 1; j < k; j++) { double v = dc[(size_t)idx[j] * n + c]; if (v < b) b = v; }
            s += b;
        }
        sets.push_back(idx); lb.push_back(s);
        int i = k - 1;
        while (i >= 0 && idx[i] == m - k + i) i--;
        if (i < 0) break;
        idx[i]++;
        for (int j = i + 1; j < k; j++) idx[j] = idx[j - 1] + 1;
    }
    vector<size_t> ord(sets.size());
    for (size_t i = 0; i < ord.size(); i++) ord[i] = i;
    std::stable_sort(ord.begin(), ord.end(), [&](size_t a, size_t b) { return lb[a] < lb[b]; });      // stable: ties keep lexicographic order
    DP.sets.resize(sets.size()); DP.lb.resize(sets.size());
    for (size_t i = 0; i < ord.size(); i++) { DP.sets[i] = sets[ord[i]]; DP.lb[i] = lb[ord[i]]; }
    DP.used.assign(sets.size(), 0); DP.used_count = 0;
    if (g_dpm_tabu) { TB.flag.assign(sets.size(), 0); for (size_t i = 0; i < DP.sets.size(); i++) TB.idx[DP.sets[i]] = (long)i; }
    DP.on = true;
    DP.build_s = now_cpu() - t0;
}
// one start set for a diversification iteration; `incumbent` = cost of the best feasible solution so far (INFINITY before the first one)
static vector<int> dpm_draw(double incumbent) {
    const long C = (long)DP.sets.size();
    DP.draws++;
    for (int attempt = 0; attempt < 1000; attempt++) {
        long r = -1;
        bool top = g_dpm_K > 0 && RNG.choice(1000) >= (int)std::lround(1000.0 * g_dpm_eps);
        if (top) {
            const long Kc = std::min<long>(g_dpm_K, C);
            if (g_dpm_mem) {
                vector<long> cand;
                for (long i = 0; i < Kc; i++) if (!DP.used[i]) cand.push_back(i);
                if (cand.empty()) top = false; else r = cand[RNG.choice((int)cand.size())];
            } else r = RNG.choice((int)Kc);
        }
        if (!top) {
            if (g_dpm_mem) {
                if (DP.used_count >= C) { std::fill(DP.used.begin(), DP.used.end(), 0); DP.used_count = 0; DP.resets++; }
                for (int t = 0; t < 200 && r < 0; t++) { long x = RNG.choice((int)C); if (!DP.used[x]) r = x; else DP.mem_skips++; }
                if (r < 0) { vector<long> un; for (long i = 0; i < C; i++) if (!DP.used[i]) un.push_back(i); r = un[RNG.choice((int)un.size())]; }
            } else r = RNG.choice((int)C);
        }
        if (g_dpm_prune && std::isfinite(incumbent) && DP.lb[r] >= incumbent - 1e-9) { DP.pruned++; continue; }
        if (g_dpm_mem && !DP.used[r]) { DP.used[r] = 1; DP.used_count++; }
        if (top) DP.top_draws++; else DP.uni_draws++;
        return DP.sets[r];
    }
    DP.fallback++;                                    // (practically) every drawn set is pruned: the bound proves no start set can improve the incumbent
    return DP.sets[RNG.choice((int)C)];
}

// v8: dpm_draw with the converged-set tabu (same two-component draw; tabu sets are never returned; the tabu list is cleared if every set is tabu)
static vector<int> dpm_draw_tabu(double incumbent) {
    const long C = (long)DP.sets.size();
    DP.draws++;
    for (int attempt = 0; attempt < 1000; attempt++) {
        long r = -1;
        bool top = g_dpm_K > 0 && RNG.choice(1000) >= (int)std::lround(1000.0 * g_dpm_eps);
        if (top) {
            const long Kc = std::min<long>(g_dpm_K, C);
            vector<long> cand;
            for (long i = 0; i < Kc; i++) if (!TB.flag[i]) cand.push_back(i);
            if (cand.empty()) top = false; else r = cand[RNG.choice((int)cand.size())];
        }
        if (!top) {
            if (TB.count >= C) { std::fill(TB.flag.begin(), TB.flag.end(), 0); TB.count = 0; TB.resets++; }
            for (int t = 0; t < 200 && r < 0; t++) { long x = RNG.choice((int)C); if (!TB.flag[x]) r = x; else TB.draw_skips++; }
            if (r < 0) { vector<long> un; for (long i = 0; i < C; i++) if (!TB.flag[i]) un.push_back(i); r = un[RNG.choice((int)un.size())]; }
        }
        if (g_dpm_prune && std::isfinite(incumbent) && DP.lb[r] >= incumbent - 1e-9) { DP.pruned++; continue; }
        if (top) DP.top_draws++; else DP.uni_draws++;
        return DP.sets[r];
    }
    DP.fallback++;
    return DP.sets[RNG.choice((int)C)];
}

static vector<int> initial_allowed(bool div_mode, const vector<int> &best_depots_div, double incumbent = INFINITY) {
    const Inst &I = *G;
    int max_open = std::max(1, std::min(I.Ng, I.m));
    vector<int> res;
    if (DP.on && (div_mode || best_depots_div.empty())) {
        res = (g_dpm_tabu && g_tabu_draw) ? dpm_draw_tabu(incumbent) : dpm_draw(incumbent);
        RNG.order('A', res);
        return res;
    }
    if (div_mode || best_depots_div.empty()) {
        vector<int> pop(I.m);
        for (int i = 0; i < I.m; i++) pop[i] = i;
        int k = max_open;
        if (g_atmost && max_open > 1) {                                  // at most Ng: the number of candidate depots is drawn uniformly from 1..Ng
            vector<int> ks(max_open);
            for (int i = 0; i < max_open; i++) ks[i] = i + 1;
            k = RNG.sample(ks, 1)[0];
        }
        res = RNG.sample(pop, k);
    } else {
        vector<int> depots = best_depots_div;
        if ((int)depots.size() > max_open) depots = RNG.sample(depots, max_open);
        else if ((int)depots.size() < max_open && !g_atmost) {
            vector<int> missing;
            for (int d = 0; d < I.m; d++) if (std::find(depots.begin(), depots.end(), d) == depots.end()) missing.push_back(d);
            vector<int> add = RNG.sample(missing, max_open - (int)depots.size());
            depots.insert(depots.end(), add.begin(), add.end());
        }
        res = depots;
    }
    RNG.order('A', res);
    return res;
}

// ================================================================================================ GRASP loop
static double T_CONSTR = 0.0, T_LS = 0.0;
struct IterLog { int k; bool div, feas, improved; double cost, best, cpu; int nroutes; vector<int> open; };
struct TraceRow { int iter; double cpu, best; };
struct PoolLog { int call, iter; double cpu, sp_cpu, before, after, lb; long routes, nodes; int sets, improved, complete; };
struct RunInfo {
    vector<PoolLog> pool_logs;
    int iters = 0, last_impr_iter = -1, best_iter = -1;
    double last_impr_cpu = 0.0;
    string stop = "none";
    vector<IterLog> logs;
    vector<TraceRow> trace;
    long best_iter_applied[NALL] = {0};
    double best_iter_gain_lat[NALL] = {0};
};
static void pool_sp_call(int iter, double c0, bool &have_best, Sol &best_sol, double &best_cost, int &since, RunInfo &RI) {
    if (!have_best || PL->R.empty()) return;
    const double t0 = now_cpu(), deadline = t0 + g_pool_tl, before = best_cost;
    vector<std::pair<double, vector<int>>> cand;
    for (auto &kv : g_set_best) if ((int)kv.first.size() == G->Ng || (g_atmost && (int)kv.first.size() <= G->Ng)) cand.push_back({kv.second, kv.first});
    std::sort(cand.begin(), cand.end(), [](const std::pair<double, vector<int>> &a, const std::pair<double, vector<int>> &b) { return a.first < b.first; });
    long nodes = 0; double lb = -INFINITY; int tried = 0, comp = 1, imp = 0;
    for (size_t ci = 0; ci < cand.size() && (int)ci < g_pool_sets; ci++) {
        if (now_cpu() >= deadline) { comp = 0; break; }
        psp::SPResult r = PL->solve_set(cand[ci].second, best_cost, deadline, g_pool_nodes);
        tried++; nodes += r.nodes; if (!r.complete) comp = 0; lb = std::max(lb, r.lb);
        if (r.improved) {
            Sol s;
            for (int j : r.sel) { Route rt; rt.depot = PL->R[j].depot; rt.path = PL->R[j].path; rt.load = path_load(rt.path.data(), rt.path.size()); s.routes.push_back(rt); }
            if (check_validity(s) && s.cost < best_cost - 1e-9) {
                best_sol = s; best_cost = s.cost; imp = 1; since = 0;
                const double now = now_cpu() - c0;
                RI.last_impr_iter = iter; RI.last_impr_cpu = now; RI.best_iter = iter; RI.trace.push_back({iter, now, best_cost});
                auto it = g_set_best.find(s.open); if (it == g_set_best.end() || s.cost < it->second) g_set_best[s.open] = s.cost;
            }
        }
    }
    PL->new_since_call = 0;
    RI.pool_logs.push_back({(int)RI.pool_logs.size() + 1, iter, now_cpu() - c0, now_cpu() - t0, before, best_cost, lb, (long)PL->R.size(), nodes, tried, imp, comp});
}
// ---- v8 (EXPERIMENTAL; default off): --pr-elite E
// Assignment path relinking.  An elite list (at most E feasible GRASP-iteration solutions with pairwise different customer->depot assignments, cheapest kept) is
// maintained.  At the end of every diversification/intensification cycle the incumbent and a random elite with a different assignment are relinked in a random
// direction: the customers whose depot differs are moved (random order) from the initiating solution towards the guiding solution's depots (cheapest insertion
// into a route of the target depot, capacity violations allowed -> strategic oscillation repairs them); only elites with the SAME open depot set as the incumbent
// are used as guides (the moves change the customer->depot assignment inside one depot set); the half-way and the final point are improved by
// local_search_ils (as every GRASP iteration is).  Results enter the elite list, the route pool and (if better) the incumbent.
struct PRStats { long calls = 0, nodiff = 0, skipped_time = 0, points = 0, feasible_points = 0, improved_best = 0, elite_adds = 0; };
static PRStats PRS;
static int g_pr_elite = 0;
static vector<Sol> g_elite;
struct PRLog { int iter, dir, ndiff, nmoved; double c1, c2, before, after, cpu; };
static vector<PRLog> g_pr_log;
static vector<int> assign_of(const Sol &s) {
    vector<int> a(G->n, -1);
    for (auto &r : s.routes) for (int c : r.path) a[c] = r.depot;
    return a;
}
static void elite_add(const Sol &s) {
    if (g_pr_elite <= 0) return;
    const vector<int> a = assign_of(s);
    for (auto &e : g_elite) if (assign_of(e) == a) { if (s.cost < e.cost - 1e-9) e = s; return; }
    g_elite.push_back(s); PRS.elite_adds++;
    if ((int)g_elite.size() > g_pr_elite) {
        size_t w = 0;
        for (size_t i = 1; i < g_elite.size(); i++) if (g_elite[i].cost > g_elite[w].cost) w = i;
        g_elite.erase(g_elite.begin() + w);
    }
}
// move customer c into a route of depot d: cheapest insertion among routes with room; if none has room, the route with the smallest overload
static bool pr_move(Sol &W, int c, int d) {
    const Inst &I = *G;
    int src = -1, spos = -1;
    for (size_t r = 0; r < W.routes.size() && src < 0; r++)
        for (size_t p = 0; p < W.routes[r].path.size(); p++) if (W.routes[r].path[p] == c) { src = (int)r; spos = (int)p; break; }
    if (src < 0 || W.routes[src].depot == d) return false;
    int bt = -1, bp = -1;
    double bover = INFINITY, bdelta = INFINITY;
    for (size_t t = 0; t < W.routes.size(); t++) {
        Route &tr = W.routes[t];
        if ((int)t == src || tr.depot != d || tr.path.empty()) continue;
        const double over = std::max(0.0, tr.load + I.dem[c] - I.Q);
        const double old_lat = eval_lat(tr.depot, tr.path.data(), tr.path.size());
        vector<int> np;
        for (size_t pos = 0; pos <= tr.path.size(); pos++) {
            np.assign(tr.path.begin(), tr.path.begin() + pos);
            np.push_back(c);
            np.insert(np.end(), tr.path.begin() + pos, tr.path.end());
            const double delta = eval_lat(tr.depot, np.data(), np.size()) - old_lat;
            if (over < bover - 1e-9 || (std::fabs(over - bover) <= 1e-9 && delta < bdelta)) { bover = over; bdelta = delta; bt = (int)t; bp = (int)pos; }
        }
    }
    if (bt < 0) return false;
    Route &sr = W.routes[src];
    sr.path.erase(sr.path.begin() + spos);
    sr.load = path_load(sr.path.data(), sr.path.size());
    Route &tr = W.routes[bt];
    tr.path.insert(tr.path.begin() + bp, c);
    tr.load = path_load(tr.path.data(), tr.path.size());
    return true;
}
static vector<Sol> pr_relink(const Sol &a, const Sol &b, PRLog &lg) {
    vector<Sol> res;
    const vector<int> da = assign_of(a), db = assign_of(b);
    vector<int> D;
    for (int c = 0; c < G->n; c++) if (da[c] != db[c]) D.push_back(c);
    lg.ndiff = (int)D.size();
    if (D.size() < 2) return res;
    D = RNG.sample(D, (int)D.size());
    const int T = (int)D.size();
    vector<int> pts(1, (T + 1) / 2);
    if (T > pts[0]) pts.push_back(T);
    Sol W = a;
    size_t pi = 0;
    int moved = 0;
    for (int t = 0; t < T && pi < pts.size(); t++) {
        if (pr_move(W, D[t], db[D[t]])) moved++;
        if (t + 1 == pts[pi]) {
            Sol s = W;
            drop_empty(s);
            for (auto &r : s.routes) r.load = path_load(r.path.data(), r.path.size());
            calculate_cost(s);
            PRS.points++;
            Sol r = local_search_ils(s);
            if (check_validity(r)) { PRS.feasible_points++; res.push_back(r); }
            else r.cost = INFINITY;
            (pi == 0 ? lg.c1 : lg.c2) = r.cost;
            pi++;
        }
    }
    lg.nmoved = moved;
    return res;
}
static void pr_step(int k, bool have_best, Sol &best_sol, double &best_cost, int &since, RunInfo &RI, double c0, double tlimit, double tl_eff) {
    if (g_pr_elite <= 0 || !have_best || g_elite.size() < 2) return;
    const double now = now_cpu() - c0;
    if (tlimit > 0 && now + 2.5 * (now / std::max(1, k + 1)) > tl_eff) { PRS.skipped_time++; return; }
    const vector<int> ab = assign_of(best_sol);
    vector<int> cand;
    for (size_t i = 0; i < g_elite.size(); i++) if (g_elite[i].open == best_sol.open && assign_of(g_elite[i]) != ab) cand.push_back((int)i);   // same open depot set, different assignment
    if (cand.empty()) { PRS.nodiff++; return; }
    const int gi = cand[RNG.choice((int)cand.size())];
    const int dir = RNG.choice(2);
    const Sol A = dir == 0 ? best_sol : g_elite[gi], B = dir == 0 ? g_elite[gi] : best_sol;
    PRLog lg{k, dir, 0, 0, NAN, NAN, best_cost, best_cost, 0.0};
    PRS.calls++;
    vector<Sol> res = pr_relink(A, B, lg);
    for (auto &r : res) {
        if (g_pool_on) pool_add_sol(r);
        elite_add(r);
        if (r.cost < best_cost - 1e-9) {
            best_sol = r; best_cost = r.cost; since = 0; PRS.improved_best++;
            const double t = now_cpu() - c0;
            RI.last_impr_iter = k; RI.last_impr_cpu = t; RI.best_iter = k; RI.trace.push_back({k, t, best_cost});
        }
    }
    lg.after = best_cost; lg.cpu = now_cpu() - c0 - now;
    g_pr_log.push_back(lg);
}
static Sol run_grasp(int max_iter, int stall, double tlimit, int alpha_max, RunInfo &RI) {
    bool have_best = false;
    Sol best_sol, current;
    double best_cost = INFINITY;
    bool div_mode = true;
    const int max_it_div = g_it_div, max_it_int = g_it_int;
    int period = 0, since = 0;
    vector<int> best_depots_div;
    bool have_div = false;
    double best_cost_div = INFINITY;
    const double c0 = now_cpu();
    const double tl_eff = (tlimit > 0 && g_pool_on) ? std::max(0.0, tlimit - g_pool_tl) : tlimit;   // v7: the final SP call is paid out of the same CPU budget
    long next_sp = g_pool_first;
    double int_best_cost = INFINITY;                  // v8 --dpm-tabu: best feasible solution of the current intensification phase
    vector<int> int_best_set;
    for (int k = 0;; k++) {
        if (max_iter > 0 && k >= max_iter) { RI.stop = "max_iter"; break; }
        if (stall > 0 && since >= stall) { RI.stop = "stall"; break; }
        if (tlimit > 0 && now_cpu() - c0 >= tl_eff) { RI.stop = "time"; break; }
        vector<int> allowed = initial_allowed(div_mode, have_div ? best_depots_div : vector<int>(), best_cost);
        const double tc0 = now_cpu();
        current = construct(allowed, alpha_max);
        T_CONSTR += now_cpu() - tc0;
        OpStat snap[NALL];
        for (int o = 0; o < NALL; o++) snap[o] = OSTAT[o];
        const double tl0 = now_cpu();
        current = local_search_ils(current);
        T_LS += now_cpu() - tl0;
        const bool feasible = check_validity(current);
        if (g_check && feasible) {                                    // --check: latency >= p-median bound of the open set (validity of the depot-layer bound)
            const Inst &I = *G; double lbs = 0.0;
            for (int c = 0; c < I.n; c++) { double b = INFINITY; for (int d : current.open) b = std::min(b, I.d(d, I.m + c)); lbs += b; }
            if (current.cost + 1e-6 < lbs) die("p-median bound violated: cost " + std::to_string(current.cost) + " < LB " + std::to_string(lbs));
        }
        bool improved = false;
        if (feasible && current.cost < best_cost - 1e-9) {
            best_sol = current; best_cost = current.cost; have_best = true; improved = true; since = 0;
            RI.last_impr_iter = k; RI.last_impr_cpu = now_cpu() - c0; RI.best_iter = k;
            for (int o = 0; o < NALL; o++) {
                RI.best_iter_applied[o] = OSTAT[o].applied - snap[o].applied;
                RI.best_iter_gain_lat[o] = OSTAT[o].gain_lat - snap[o].gain_lat;
            }
            RI.trace.push_back({k, now_cpu() - c0, best_cost});
        } else since++;
        if (div_mode && feasible && current.cost < best_cost_div) {
            best_cost_div = current.cost;
            best_depots_div = py_open_set(current).copy().items();
            have_div = !best_depots_div.empty();
        }
        RI.logs.push_back({k, div_mode, feasible, improved, current.cost, have_best ? best_cost : NAN, now_cpu() - c0, route_count(current), current.open});
        RI.iters = k + 1;
        if (g_dpm_tabu && !div_mode && feasible && current.cost < int_best_cost) { int_best_cost = current.cost; int_best_set = current.open; }
        if (g_pr_elite > 0 && feasible) elite_add(current);
        if (g_pool_on) {
            if (feasible) pool_add_sol(current);
            if ((long)(k + 1) >= next_sp) { pool_sp_call(k, c0, have_best, best_sol, best_cost, since, RI); next_sp *= 2; }
        }
        period++;
        if (div_mode && period >= max_it_div) {
            if (g_dpm_tabu && g_tabu_skip && have_div && tabu_has(best_depots_div)) {       // v8: the cycle converged on an already converged set -> no intensification
                TB.skipped_int++; TB.cycles++;
                TB.events.push_back({k, string("skip_int:") + set_text(best_depots_div)});
                period = 0; best_depots_div.clear(); have_div = false; best_cost_div = INFINITY;
                pr_step(k, have_best, best_sol, best_cost, since, RI, c0, tlimit, tl_eff);
            } else { div_mode = false; period = 0; int_best_cost = INFINITY; int_best_set.clear(); }
        }
        else if (!div_mode && period >= max_it_int) {
            div_mode = true; period = 0;
            if (g_dpm_tabu) {                                               // v8: the cycle's converged sets become tabu
                TB.cycles++;
                if (have_div) tabu_add(best_depots_div, k, "div");
                if (!int_best_set.empty()) tabu_add(int_best_set, k, "int");
            }
            if (!(DP.on && g_dpm_mem)) { best_depots_div.clear(); have_div = false; best_cost_div = INFINITY; }    // --dpm-memory: the elite set survives the cycle
            pr_step(k, have_best, best_sol, best_cost, since, RI, c0, tlimit, tl_eff);
        }
    }
    if (g_pool_on) pool_sp_call(RI.iters > 0 ? RI.iters - 1 : 0, c0, have_best, best_sol, best_cost, since, RI);
    return have_best ? best_sol : current;
}

// ================================================================================================ output
static string g12(double x) { char b[64]; snprintf(b, sizeof b, "%.12g", x); return b; }
static string list_str(const vector<int> &v) {
    string s = "[";
    for (size_t i = 0; i < v.size(); i++) { if (i) s += ", "; s += std::to_string(v[i]); }
    return s + "]";
}
static string q(const string &s) { return "\"" + s + "\""; }

static int g_out_level = 2;       // 0: run + operator statistics; 1: + routes + anytime trace; 2: + GRASP iteration log
static void write_outputs(const string &prefix, const Inst &I, const Sol &best, bool feas, const RunInfo &RI, const string &algo,
                          long long seed, double cpu, double wall) {
    const double bks = I.bks;
    auto gap = [&](double c) { return bks > 0 ? 100.0 * (c - bks) / bks : NAN; };
    double tot_dem = 0.0;
    for (double d : I.dem) tot_dem += d;
    double maxload = 0.0, total_evals = 0.0;
    for (int o : g_pool) total_evals += (double)OSTAT[o].evals;
    int nr = 0;
    for (auto &r : best.routes) if (!r.path.empty()) { nr++; maxload = std::max(maxload, r.load); }
    FILE *f;
    // ---- routes of the best solution (columns of Rank_Best_Routes, plus Seed)
    if (g_out_level >= 1) {
    f = fopen((prefix + ".routes.csv").c_str(), "w");
    if (!f) die("cannot write " + prefix + ".routes.csv");
    int rid = 0;
    for (auto &r : best.routes) {
        if (r.path.empty()) continue;
        rid++;
        string cs, as;
        double arr = 0.0, lat = 0.0, dist = 0.0;
        int prev = r.depot;
        for (size_t k = 0; k < r.path.size(); k++) {
            const int cg = I.m + r.path[k];
            const double dd = I.d(prev, cg);
            arr += dd; lat += arr; dist += dd; prev = cg;
            char b[64];
            snprintf(b, sizeof b, "%.2f", arr);
            if (k) { cs += " -> "; as += " -> "; }
            cs += std::to_string(r.path[k]);
            as += b;
        }
        fprintf(f, "%s,%s,%lld,%d,%d,%s,%s,%d,%s,%s,%s\n", I.name.c_str(), algo.c_str(), seed, rid, r.depot, cs.c_str(), as.c_str(), (int)r.path.size(),
                g12(r.load).c_str(), g12(lat).c_str(), g12(dist).c_str());
    }
    fclose(f);
    }
    // ---- GRASP iteration log (columns of All_Iteration_Logs)
    if (g_out_level >= 2) {
    f = fopen((prefix + ".iter.csv").c_str(), "w");
    if (!f) die("cannot write " + prefix + ".iter.csv");
    for (auto &l : RI.logs) {
        fprintf(f, "%s,%s,%lld,%lld,%d,%s,%s,%s,%s,%s,%s,%s,%s,%d,%d,%d,%s\n", I.name.c_str(), algo.c_str(), seed + 1, seed, l.k,
                l.div ? "Diversification" : "Intensification", l.feas ? "True" : "False", g12(l.cost).c_str(),
                std::isnan(l.best) ? "" : g12(l.best).c_str(), l.improved ? "True" : "False", g12(bks).c_str(),
                std::isnan(l.best) ? "" : g12(gap(l.best)).c_str(), q(list_str(l.open)).c_str(), l.nroutes, I.Nv, I.Ng, g12(l.cpu).c_str());
    }
    fclose(f);
    }
    // ---- operator statistics
    f = fopen((prefix + ".ops.csv").c_str(), "w");
    if (!f) die("cannot write " + prefix + ".ops.csv");
    for (int o : g_pool) {
        const OpStat &s = OSTAT[o];
        fprintf(f, "%s,%s,%lld,%s,%ld,%ld,%ld,%s,%s,%s,%ld,%s\n", I.name.c_str(), algo.c_str(), seed, OPS_ALL[o].name, s.calls, s.evals, s.applied,
                g12(s.gain_lat).c_str(), g12(s.gain_obj).c_str(), g12(s.cpu).c_str(), RI.best_iter_applied[o], g12(RI.best_iter_gain_lat[o]).c_str());
    }
    fclose(f);
    // ---- anytime trace (every improvement of the best solution)
    if (g_out_level >= 1) {
    f = fopen((prefix + ".trace.csv").c_str(), "w");
    if (!f) die("cannot write " + prefix + ".trace.csv");
    for (auto &t : RI.trace) fprintf(f, "%s,%s,%lld,%d,%s,%s\n", I.name.c_str(), algo.c_str(), seed, t.iter, g12(t.cpu).c_str(), g12(t.best).c_str());
    fclose(f);
    }
    // ---- run level (columns of All_Run_Level_Details, then extras); written LAST: its existence marks a completed run
    f = fopen((prefix + ".run.csv").c_str(), "w");
    if (!f) die("cannot write " + prefix + ".run.csv");
    fprintf(f, "%s,%s,%lld,%lld,%s,%s,%s,%s,%s,%s,%d,%d,%d,%d,%d,%s,%s,%s,%s,%d,%d,%d,%s,%d,%s,%s,%s\n", I.name.c_str(), algo.c_str(), seed + 1, seed,
            feas ? "True" : "False", g12(best.cost).c_str(), g12(bks).c_str(), g12(gap(best.cost)).c_str(), g12(cpu).c_str(),
            q(list_str(best.open)).c_str(), nr, (int)best.open.size(), I.Ng, nr, I.Nv, g12(maxload).c_str(), g12(I.Q).c_str(),
            g12(tot_dem).c_str(), g12(I.Nv * I.Q).c_str(), I.Nv, I.Ng, RI.iters, RI.stop.c_str(), RI.last_impr_iter, g12(RI.last_impr_cpu).c_str(),
            g12(wall).c_str(), g12((double)total_evals).c_str());
    fclose(f);
}

// ================================================================================================ main
int main(int argc, char **argv) {
    string inst_path, ops_arg = "zou", out_prefix, algo_arg, select = "best", order = "random";
    long long seed = 0;
    int max_iter = 1000, stall = 0, rcl = 5;
    double tlimit = 0.0;
    bool quiet = false, pyrng = true, add_ds = false, list_ops = false, construct_only = false;
    int gran_arg = 0;
    bool dpm_requested = false;
    for (int i = 1; i < argc; i++) {
        string a = argv[i];
        auto val = [&]() -> string { if (i + 1 >= argc) die("missing value for " + a); return argv[++i]; };
        if (a == "--instance") inst_path = val();
        else if (a == "--ops") ops_arg = val();
        else if (a == "--so") g_so = true;
        else if (a == "--ds") add_ds = true;
        else if (a == "--select") select = val();
        else if (a == "--order") order = val();
        else if (a == "--seed") seed = atoll(val().c_str());
        else if (a == "--max-iter") max_iter = atoi(val().c_str());
        else if (a == "--stall") stall = atoi(val().c_str());
        else if (a == "--time") tlimit = atof(val().c_str());
        else if (a == "--ils") g_ils = atoi(val().c_str());
        else if (a == "--gran") gran_arg = atoi(val().c_str());
        else if (a == "--atmost") g_atmost = true;
        else if (a == "--dpm-rank") {                                       // K[,eps]
            string v = val(); size_t cm = v.find(',');
            g_dpm_K = atoi(v.substr(0, cm).c_str());
            if (cm != string::npos) g_dpm_eps = atof(v.substr(cm + 1).c_str());
            dpm_requested = true;
        }
        else if (a == "--dpm-prune") { g_dpm_prune = true; dpm_requested = true; }
        else if (a == "--dpm-memory") { g_dpm_mem = true; dpm_requested = true; }
        else if (a == "--dpm-tabu") { g_dpm_tabu = true; dpm_requested = true; }
        else if (a == "--dpm-tabu-parts") {
            string v = val(); g_tabu_parts_set = true;
            if (v == "draw") { g_tabu_draw = true; g_tabu_skip = false; }
            else if (v == "skip") { g_tabu_draw = false; g_tabu_skip = true; }
            else if (v == "both") { g_tabu_draw = true; g_tabu_skip = true; }
            else die("--dpm-tabu-parts must be draw, skip or both");
        }
        else if (a == "--pr-elite") g_pr_elite = atoi(val().c_str());
        else if (a == "--dpm-cap") g_dpm_cap = atol(val().c_str());
        else if (a == "--pool-sp") g_pool_on = true;
        else if (a == "--pool-tl") g_pool_tl = atof(val().c_str());
        else if (a == "--pool-sets") g_pool_sets = atoi(val().c_str());
        else if (a == "--pool-first") g_pool_first = atoi(val().c_str());
        else if (a == "--pool-src") g_pool_src = atoi(val().c_str());
        else if (a == "--pool-theta") g_pool_theta = atof(val().c_str());
        else if (a == "--pool-nodes") g_pool_nodes = atol(val().c_str());
        else if (a == "--rcl") rcl = atoi(val().c_str());
        else if (a == "--it-div") g_it_div = atoi(val().c_str());
        else if (a == "--it-int") g_it_int = atoi(val().c_str());
        else if (a == "--so-win-up") g_win_up = atoi(val().c_str());
        else if (a == "--so-win-down") g_win_down = atoi(val().c_str());
        else if (a == "--so-f1") g_so_f1 = atof(val().c_str());
        else if (a == "--so-f2") g_so_f2 = atof(val().c_str());
        else if (a == "--beta-min") g_beta_min = atof(val().c_str());
        else if (a == "--beta-max") g_beta_max = atof(val().c_str());
        else if (a == "--beta0-scale") g_beta0_scale = atof(val().c_str());
        else if (a == "--out") out_prefix = val();
        else if (a == "--out-level") g_out_level = atoi(val().c_str());
        else if (a == "--algo") algo_arg = val();
        else if (a == "--check") g_check = true;
        else if (a == "--quiet") quiet = true;
        else if (a == "--no-pyrng") pyrng = false;
        else if (a == "--list-ops") list_ops = true;
        else if (a == "--ecwa-ref") g_ecwa_ref = true;
        else if (a == "--construct-only") construct_only = true;
        else die("unknown option " + a);
    }
    if (list_ops) {
        for (int i = 0; i < NALL; i++) printf("%s\n", OPS_ALL[i].name);
        return 0;
    }
    if (inst_path.empty()) die("--instance required");
    if (g_it_div < 1 || g_it_int < 1) die("--it-div and --it-int must be >= 1");
    if (g_win_up < 1 || g_win_down < 1) die("--so-win-up and --so-win-down must be >= 1");
    if (!(g_so_f1 > 1.0) || !(g_so_f2 > 1.0)) die("--so-f1 and --so-f2 must be > 1");
    if (!(g_beta_min > 0.0) || !(g_beta_max > g_beta_min)) die("need 0 < --beta-min < --beta-max");
    if (!(g_beta0_scale > 0.0)) die("--beta0-scale must be > 0");
    if (rcl < 1) die("--rcl must be >= 1");
    if (select == "best") g_first = false; else if (select == "first") g_first = true; else die("--select best|first");
    if (order == "random") g_random = true; else if (order == "fixed") g_random = false; else die("--order random|fixed");
    string spec = preset_ops(ops_arg);
    parse_ops(spec);
    if (add_ds && std::find(g_pool.begin(), g_pool.end(), op_index("ds")) == g_pool.end()) g_pool.push_back(op_index("ds"));
    string pool_names;
    for (size_t k = 0; k < g_pool.size(); k++) { if (k) pool_names += "+"; pool_names += OPS_ALL[g_pool[k]].name; }
    string algo = algo_arg;
    if (algo.empty()) {
        algo = string("GRASP-") + (g_random ? "RVND" : "VND") + (g_ils > 0 ? "-ILS" : "") + (g_so ? "-SO" : "-CL") + "[" + pool_names + "]";
    }
    Inst I = read_instance(inst_path);
    G = &I;
    if (gran_arg < 0) die("--gran must be >= 0");
    build_gran(I, gran_arg);
    if (dpm_requested) {
        if (g_atmost) die("--dpm-* cannot be combined with --atmost");
        if (g_dpm_K < 0 || g_dpm_eps < 0.0 || g_dpm_eps > 1.0) die("--dpm-rank K[,eps]: K >= 0 and 0 <= eps <= 1");
        if (g_dpm_tabu && g_dpm_mem) die("--dpm-tabu cannot be combined with --dpm-memory");
        if (g_tabu_parts_set && !g_dpm_tabu) die("--dpm-tabu-parts needs --dpm-tabu");
        dpm_build(I);
    }
    if (g_pr_elite < 0) die("--pr-elite E: E >= 0");
    if (g_pool_on) {
        if (I.n > 1024) die("--pool-sp: n too large");
        if (g_pool_tl < 0 || g_pool_sets < 1 || g_pool_first < 1 || g_pool_src < 1 || g_pool_src > 2) die("--pool-*: invalid value");
        psp::Params PP; PP.n = I.n; PP.m = I.m; PP.Nv = I.Nv; PP.Ng = I.Ng; PP.atmost = g_atmost; PP.D = I.D.data(); PP.NN = I.N;
        PL = new psp::Pool(PP);
    }
    RNG.gen.seed((unsigned long long)seed);
    if (pyrng) { RNG.pyrng = true; RNG.mt.seed((unsigned long long)seed); }

    if (construct_only) {                       // test: cost of the constructed solution (no local search) of the first max_iter GRASP draws
        double t0 = now_cpu();
        for (int k = 0; k < max_iter; k++) {
            vector<int> allowed = initial_allowed(true, vector<int>());
            Sol s = construct(allowed, rcl);
            printf("%d %.17g %d\n", k, s.cost, check_validity(s) ? 1 : 0);
        }
        fprintf(stderr, "construction cpu %.3f s\n", now_cpu() - t0);
        return 0;
    }
    RunInfo RI;
    const double c0 = now_cpu(), w0 = now_wall();
    Sol best = run_grasp(max_iter, stall, tlimit, rcl, RI);
    const double cpu = now_cpu() - c0, wall = now_wall() - w0;
    const bool feas = check_validity(best);

    printf("instance %s\nalgo %s\nseed %lld\nfinal_cost %.17g\nfeasible %d\niterations %d\nstop %s\nlast_improvement_iter %d\ncpu_s %.6f\nwall_s %.6f\n",
           I.name.c_str(), algo.c_str(), seed, best.cost, feas ? 1 : 0, RI.iters, RI.stop.c_str(), RI.last_impr_iter, cpu, wall);
    printf("params rcl=%d it_div=%d it_int=%d so=%d so_win_up=%d so_win_down=%d so_f1=%.17g so_f2=%.17g beta_min=%.17g beta_max=%.17g beta0_scale=%.17g ils=%d select=%s order=%s ops=%s\n",
           rcl, g_it_div, g_it_int, g_so ? 1 : 0, g_win_up, g_win_down, g_so_f1, g_so_f2, g_beta_min, g_beta_max, g_beta0_scale, g_ils, select.c_str(), order.c_str(), pool_names.c_str());
    if (g_gran > 0) printf("gran %d\n", g_gran);
    if (g_atmost) printf("atmost 1\n");
    if (DP.on) {
        printf("dpm rank_K=%d eps=%.3f prune=%d memory=%d sets=%zu build_cpu_s=%.4f draws=%ld top_draws=%ld uniform_draws=%ld pruned=%ld mem_skips=%ld fallback=%ld resets=%ld\n",
               g_dpm_K, g_dpm_eps, g_dpm_prune ? 1 : 0, g_dpm_mem ? 1 : 0, DP.sets.size(), DP.build_s, DP.draws, DP.top_draws, DP.uni_draws, DP.pruned, DP.mem_skips, DP.fallback, DP.resets);
        if (!out_prefix.empty()) {                                   // sidecar for the run script (only when a --dpm-* flag is on)
            FILE *g = fopen((out_prefix + ".dpm.csv").c_str(), "w");
            if (g) {
                fprintf(g, "Instance,Seed,rank_K,eps,prune,memory,sets,build_cpu_s,draws,top_draws,uniform_draws,pruned,mem_skips,fallback,resets\n");
                fprintf(g, "%s,%lld,%d,%.3f,%d,%d,%zu,%.4f,%ld,%ld,%ld,%ld,%ld,%ld,%ld\n", I.name.c_str(), seed, g_dpm_K, g_dpm_eps, g_dpm_prune ? 1 : 0, g_dpm_mem ? 1 : 0, DP.sets.size(), DP.build_s,
                        DP.draws, DP.top_draws, DP.uni_draws, DP.pruned, DP.mem_skips, DP.fallback, DP.resets);
                fclose(g);
            }
        }
    }
    if (g_dpm_tabu) {
        printf("tabu on=1 cycles=%ld adds=%ld skipped_int=%ld draw_skips=%ld resets=%ld size_end=%ld draw=%d skip=%d\n", TB.cycles, TB.adds, TB.skipped_int, TB.draw_skips, TB.resets, TB.count, g_tabu_draw ? 1 : 0, g_tabu_skip ? 1 : 0);
        if (!out_prefix.empty()) {
            FILE *g = fopen((out_prefix + ".tabu.csv").c_str(), "w");
            if (g) { fprintf(g, "Instance,Seed,iter,event\n"); for (auto &e : TB.events) fprintf(g, "%s,%lld,%d,%s\n", I.name.c_str(), seed, e.first, e.second.c_str()); fclose(g); }
        }
    }
    if (g_pr_elite > 0) {
        printf("pr on=1 elite=%d calls=%ld nodiff=%ld skipped_time=%ld points=%ld feasible_points=%ld improved_best=%ld elite_adds=%ld\n", g_pr_elite, PRS.calls, PRS.nodiff, PRS.skipped_time,
               PRS.points, PRS.feasible_points, PRS.improved_best, PRS.elite_adds);
        if (!out_prefix.empty()) {
            FILE *g = fopen((out_prefix + ".pr.csv").c_str(), "w");
            if (g) {
                fprintf(g, "Instance,Seed,iter,dir,ndiff,nmoved,cost_half,cost_end,best_before,best_after,cpu_s\n");
                for (auto &l : g_pr_log) fprintf(g, "%s,%lld,%d,%d,%d,%d,%.9g,%.9g,%.9g,%.9g,%.4f\n", I.name.c_str(), seed, l.iter, l.dir, l.ndiff, l.nmoved, l.c1, l.c2, l.before, l.after, l.cpu);
                fclose(g);
            }
        }
    }
    if (g_pool_on) {
        double sp_cpu = 0; int nimp = 0; for (auto &l : RI.pool_logs) { sp_cpu += l.sp_cpu; nimp += l.improved; }
        printf("pool on=1 src=%d tl=%.2f sets=%d first=%d calls=%zu improved_calls=%d sp_cpu_s=%.3f routes=%zu new=%ld hit=%ld dp_calls=%ld dp_gain=%ld dp_skipped=%ld\n", g_pool_src, g_pool_tl, g_pool_sets, g_pool_first,
               RI.pool_logs.size(), nimp, sp_cpu, PL->R.size(), PL->n_new, PL->n_hit, PL->dp_calls, PL->dp_gain, PL->dp_skipped);
        if (!out_prefix.empty()) {
            FILE *g = fopen((out_prefix + ".pool.csv").c_str(), "w");
            if (g) {
                fprintf(g, "Instance,Seed,call,iter,cpu_s,sp_cpu_s,best_before,best_after,root_lb,pool_routes,nodes,sets_tried,improved,complete\n");
                for (auto &l : RI.pool_logs) fprintf(g, "%s,%lld,%d,%d,%.4f,%.4f,%.9g,%.9g,%.9g,%ld,%ld,%d,%d,%d\n", I.name.c_str(), seed, l.call, l.iter, l.cpu, l.sp_cpu, l.before, l.after, l.lb, l.routes, l.nodes, l.sets, l.improved, l.complete);
                fclose(g);
            }
        }
    }
    if (!out_prefix.empty()) write_outputs(out_prefix, I, best, feas, RI, algo, seed, cpu, wall);
    if (!quiet) {
        for (auto &r : best.routes) {
            if (r.path.empty()) continue;
            printf("route depot=%d load=%g :", r.depot, r.load);
            for (int c : r.path) printf(" %d", c);
            printf("\n");
        }
        printf("time construction %.3f s, local search %.3f s\n", T_CONSTR, T_LS);
        printf("operators (calls evals applied gain_lat cpu_s):\n");
        for (int o : g_pool) printf("  %-9s %8ld %12ld %7ld %12.2f %8.3f\n", OPS_ALL[o].name, OSTAT[o].calls, OSTAT[o].evals, OSTAT[o].applied, OSTAT[o].gain_lat, OSTAT[o].cpu);
    }
    return 0;
}
