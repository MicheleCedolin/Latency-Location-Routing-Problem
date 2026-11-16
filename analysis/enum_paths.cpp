// Enumerate all capacity-feasible elementary paths of a sparse customer graph and keep, for every (customer set, depot),
// the cheapest path (latency = sum of arrival times, the route starting at the depot).
//
// stdin : n m Q kmax maxpaths maxcols ndep
//         n lines "demand x y", m lines "x y" (depots), n lines "deg nb_1 ... nb_deg" (0-based customer ids)
// stdout: "#" summary line, then one line per kept column: depot cost k c_1 ... c_k   (c_1 is the first customer after the depot)
// A path can start at any customer; its depot is one of the `ndep` depots nearest to the first customer.
// Compile: g++ -O2 -std=c++11 -o enum_paths enum_paths.cpp
#include <cstdio>
#include <cmath>
#include <cstdlib>
#include <vector>
#include <unordered_map>
#include <random>
#include <algorithm>
#include <cstdint>
using namespace std;

static int n, m, kmax, ndep;
static double Q;
static long long maxpaths, maxcols, npaths = 0;
static bool capped_paths = false, capped_cols = false;
static vector<double> dem, X, Y, DX, DY;
static vector<vector<int>> adj, topdep;
static vector<vector<double>> D, D0;
static vector<uint64_t> z1, z2;
static vector<char> vis;
static vector<int> path;

struct Col { int depot; double cost; vector<int> order; };
static vector<Col> cols;
struct H { size_t operator()(const pair<uint64_t, uint64_t>& p) const { return p.first ^ (p.second * 0x9E3779B97F4A7C15ULL); } };
static unordered_map<pair<uint64_t, uint64_t>, int, H> index_of;

static void emit(uint64_t h1, uint64_t h2, double T, int k) {
    int c1 = path[0];
    for (int t = 0; t < (int)topdep[c1].size(); t++) {
        int d = topdep[c1][t];
        double cost = k * D0[d][c1] + T;
        pair<uint64_t, uint64_t> key(h1 ^ (0xD1B54A32D192ED03ULL * (uint64_t)(d + 1)), h2 + 0x94D049BB133111EBULL * (uint64_t)(d + 1));
        auto it = index_of.find(key);
        if (it == index_of.end()) {
            if ((long long)cols.size() >= maxcols) { capped_cols = true; continue; }
            index_of[key] = (int)cols.size();
            cols.push_back({d, cost, vector<int>(path.begin(), path.begin() + k)});
        } else if (cost < cols[it->second].cost - 1e-12) {
            cols[it->second].cost = cost;
            cols[it->second].order.assign(path.begin(), path.begin() + k);
        }
    }
}

static void dfs(int last, int k, double load, double L, double T, uint64_t h1, uint64_t h2) {
    if (capped_paths) return;
    if (++npaths > maxpaths) { capped_paths = true; return; }
    emit(h1, h2, T, k);
    if (k >= kmax) return;
    for (int j : adj[last]) {
        if (vis[j] || load + dem[j] > Q + 1e-9) continue;
        double L2 = L + D[last][j];
        vis[j] = 1; path[k] = j;
        dfs(j, k + 1, load + dem[j], L2, T + L2, h1 ^ z1[j], h2 ^ z2[j]);
        vis[j] = 0;
        if (capped_paths) return;
    }
}

int main() {
    if (scanf("%d %d %lf %d %lld %lld %d", &n, &m, &Q, &kmax, &maxpaths, &maxcols, &ndep) != 7) return 1;
    dem.resize(n); X.resize(n); Y.resize(n); DX.resize(m); DY.resize(m);
    for (int i = 0; i < n; i++) if (scanf("%lf %lf %lf", &dem[i], &X[i], &Y[i]) != 3) return 1;
    for (int d = 0; d < m; d++) if (scanf("%lf %lf", &DX[d], &DY[d]) != 2) return 1;
    adj.assign(n, {});
    for (int i = 0; i < n; i++) {
        int deg; if (scanf("%d", &deg) != 1) return 1;
        adj[i].resize(deg);
        for (int t = 0; t < deg; t++) if (scanf("%d", &adj[i][t]) != 1) return 1;
    }
    D.assign(n, vector<double>(n)); D0.assign(m, vector<double>(n));
    for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) D[i][j] = hypot(X[i] - X[j], Y[i] - Y[j]);
    for (int d = 0; d < m; d++) for (int i = 0; i < n; i++) D0[d][i] = hypot(DX[d] - X[i], DY[d] - Y[i]);
    topdep.assign(n, {});
    for (int i = 0; i < n; i++) {
        vector<int> o(m); for (int d = 0; d < m; d++) o[d] = d;
        sort(o.begin(), o.end(), [&](int a, int b) { return D0[a][i] < D0[b][i]; });
        topdep[i].assign(o.begin(), o.begin() + min(ndep, m));
    }
    mt19937_64 rng(12345); z1.resize(n); z2.resize(n);
    for (int i = 0; i < n; i++) { z1[i] = rng(); z2[i] = rng(); }
    vis.assign(n, 0); path.assign(kmax + 1, 0);
    for (int s = 0; s < n && !capped_paths; s++) {
        vis[s] = 1; path[0] = s;
        dfs(s, 1, dem[s], 0.0, 0.0, z1[s], z2[s]);
        vis[s] = 0;
    }
    printf("# paths %lld capped_paths %d cols %d capped_cols %d\n", npaths, (int)capped_paths, (int)cols.size(), (int)capped_cols);
    for (const Col& c : cols) {
        printf("%d %.9f %d", c.depot, c.cost, (int)c.order.size());
        for (int v : c.order) printf(" %d", v);
        printf("\n");
    }
    return 0;
}
