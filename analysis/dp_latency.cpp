// Exact minimum-latency visiting order of a fixed customer set from a fixed depot (Held-Karp over subsets).
// Latency = sum of arrival times; an edge travelled with r customers still to be reached contributes r * length.
// Build: g++ -O2 -shared -fPIC -o libdp_latency.so dp_latency.cpp      (k <= 20 customers; memory 2^k * k * 9 bytes)
#include <cstdint>
#include <limits>
#include <vector>

extern "C" double dp_min_latency(int k, const double* d0, const double* D, int* order) {
    const double INF = std::numeric_limits<double>::infinity();
    const uint32_t full = (1u << k) - 1;
    std::vector<double> f((size_t(full) + 1) * k, INF);
    std::vector<int8_t> par((size_t(full) + 1) * k, -1);
    for (int j = 0; j < k; ++j) f[(size_t(1) << j) * k + j] = d0[j] * k;
    for (uint32_t S = 1; S < full; ++S) {
        const int rem = k - __builtin_popcount(S);
        for (int i = 0; i < k; ++i) {
            if (!((S >> i) & 1u)) continue;
            const double fi = f[size_t(S) * k + i];
            if (fi == INF) continue;
            for (int j = 0; j < k; ++j) {
                if ((S >> j) & 1u) continue;
                const size_t idx = size_t(S | (1u << j)) * k + j;
                const double v = fi + D[i * k + j] * rem;
                if (v < f[idx]) { f[idx] = v; par[idx] = (int8_t)i; }
            }
        }
    }
    int last = 0;
    double best = INF;
    for (int j = 0; j < k; ++j)
        if (f[size_t(full) * k + j] < best) { best = f[size_t(full) * k + j]; last = j; }
    uint32_t S = full;
    for (int pos = k - 1; pos >= 0; --pos) {
        order[pos] = last;
        const int p = par[size_t(S) * k + last];
        S &= ~(1u << last);
        last = p;
    }
    return best;
}
