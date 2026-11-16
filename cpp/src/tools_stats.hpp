// llrp_tools -- small statistics library (mean, sd, quantiles, Wilcoxon signed-rank, Holm, rank-biserial, bootstrap)
#ifndef LLRP_TOOLS_STATS_HPP
#define LLRP_TOOLS_STATS_HPP
#include "tools_common.hpp"
#include <random>

static double mean_of(const vector<double> &v) {
    if (v.empty()) return NaN;
    double s = 0;
    for (size_t i = 0; i < v.size(); i++) s += v[i];
    return s / v.size();
}
static double sd_of(const vector<double> &v) {
    if (v.size() < 2) return NaN;
    double m = mean_of(v), s = 0;
    for (size_t i = 0; i < v.size(); i++) s += (v[i] - m) * (v[i] - m);
    return std::sqrt(s / (v.size() - 1));
}
static double median_of(vector<double> v) {
    if (v.empty()) return NaN;
    std::sort(v.begin(), v.end());
    size_t n = v.size();
    return n % 2 ? v[n / 2] : 0.5 * (v[n / 2 - 1] + v[n / 2]);
}
static double pct_of(vector<double> v, double p) {                 // linear interpolation (numpy default)
    if (v.empty()) return NaN;
    std::sort(v.begin(), v.end());
    double k = (v.size() - 1) * p / 100.0;
    size_t lo = (size_t)std::floor(k), hi = (size_t)std::ceil(k);
    return v[lo] + (v[hi] - v[lo]) * (k - lo);
}
static double max_of(const vector<double> &v) {
    double m = -INFINITY;
    for (size_t i = 0; i < v.size(); i++) m = std::max(m, v[i]);
    return m;
}
static double min_of(const vector<double> &v) {
    double m = INFINITY;
    for (size_t i = 0; i < v.size(); i++) m = std::min(m, v[i]);
    return m;
}
static double sum_of(const vector<double> &v) { double s = 0; for (size_t i = 0; i < v.size(); i++) s += v[i]; return s; }

// ranks of |d| (average ranks for ties); returns tie correction term sum(c^3 - c)
static double abs_ranks(const vector<double> &d, vector<double> &rank, bool &has_ties) {
    size_t n = d.size();
    vector<size_t> idx(n);
    for (size_t i = 0; i < n; i++) idx[i] = i;
    std::sort(idx.begin(), idx.end(), [&](size_t a, size_t b) { return std::fabs(d[a]) < std::fabs(d[b]); });
    rank.assign(n, 0.0);
    double tie = 0.0;
    has_ties = false;
    size_t i = 0;
    while (i < n) {
        size_t j = i;
        while (j + 1 < n && std::fabs(std::fabs(d[idx[j + 1]]) - std::fabs(d[idx[i]])) < 1e-12) j++;
        double r = (i + j) / 2.0 + 1.0;
        for (size_t t = i; t <= j; t++) rank[idx[t]] = r;
        double c = (double)(j - i + 1);
        if (c > 1) has_ties = true;
        tie += c * c * c - c;
        i = j + 1;
    }
    return tie;
}

// two-sided Wilcoxon signed-rank test of H0: median(d) = 0.   Zeros (|d| <= 1e-9) are dropped (Wilcoxon's zero method).
// Same decision rule as scipy.stats.wilcoxon(method='auto') (scipy 1.18) applied to the non-zero differences:
//   no ties & n <= 50 -> exact null distribution (DP over rank sums);  ties & n <= 13 -> exact sign-flip distribution of the tie-averaged ranks;
//   otherwise -> normal approximation with tie correction, no continuity correction.   neff = number of non-zero differences.
static double wilcoxon_p(const vector<double> &d_in, int *neff = 0) {
    vector<double> d;
    for (size_t i = 0; i < d_in.size(); i++) if (std::fabs(d_in[i]) > 1e-9) d.push_back(d_in[i]);
    int n = (int)d.size();
    if (neff) *neff = n;
    if (n == 0) return 1.0;
    vector<double> rank;
    bool ties;
    double tie = abs_ranks(d, rank, ties);
    double wp = 0, wm = 0;
    for (int i = 0; i < n; i++) { if (d[i] > 0) wp += rank[i]; else wm += rank[i]; }
    // scipy.stats.wilcoxon(method='auto') on the non-zero differences: exact if n <= 50 and no ties; sign-flip permutation (deterministic) if ties and n <= 13;
    // otherwise asymptotic (tie-corrected, no continuity correction).
    if ((n <= 50 && !ties) || n <= 13) {              // exact sign-flip distribution of the (tie-averaged) ranks; ranks are multiples of 1/2 -> use 2*rank
        vector<int> r2(n);
        int total2 = 0;
        for (int i = 0; i < n; i++) { r2[i] = (int)std::lround(2.0 * rank[i]); total2 += r2[i]; }
        vector<double> cnt(total2 + 1, 0.0);
        cnt[0] = 1.0;
        for (int i = 0; i < n; i++)
            for (int s = total2; s >= r2[i]; s--) cnt[s] += cnt[s - r2[i]];
        const double total = std::ldexp(1.0, n);
        const int lo = (int)std::lround(2.0 * std::min(wp, wm));
        double c = 0;
        for (int s = 0; s <= lo; s++) c += cnt[s];
        return std::min(1.0, 2.0 * c / total);
    }
    const double mu = n * (n + 1) / 4.0;
    const double var = n * (n + 1.0) * (2.0 * n + 1.0) / 24.0 - tie / 48.0;
    if (var <= 0) return 1.0;
    const double z = std::fabs(wp - mu) / std::sqrt(var);                    // no continuity correction (= scipy.stats.wilcoxon, method='approx')
    return std::erfc(std::max(z, 0.0) / std::sqrt(2.0));
}

static vector<double> holm_adjust(const vector<double> &ps) {
    size_t m = ps.size();
    vector<size_t> order(m);
    for (size_t i = 0; i < m; i++) order[i] = i;
    std::sort(order.begin(), order.end(), [&](size_t a, size_t b) { return ps[a] < ps[b]; });
    vector<double> adj(m, 0.0);
    double run = 0.0;
    for (size_t r = 0; r < m; r++) {
        size_t i = order[r];
        run = std::max(run, std::min(1.0, (double)(m - r) * ps[i]));
        adj[i] = run;
    }
    return adj;
}

// rank-biserial correlation of paired differences (matched-pairs effect size, in [-1, 1])
static double rank_biserial(const vector<double> &d_in) {
    vector<double> d;
    for (size_t i = 0; i < d_in.size(); i++) if (std::fabs(d_in[i]) > 1e-12) d.push_back(d_in[i]);
    if (d.empty()) return 0.0;
    vector<double> rank;
    bool ties;
    abs_ranks(d, rank, ties);
    double wp = 0, wm = 0;
    for (size_t i = 0; i < d.size(); i++) { if (d[i] > 0) wp += rank[i]; else wm += rank[i]; }
    return (wp - wm) / (wp + wm);
}

// percentile bootstrap CI of the mean of v (resampling elements), fixed seed -> reproducible
static void bootstrap_ci_mean(const vector<double> &v, int B, unsigned long long seed, double &lo, double &hi) {
    lo = hi = NaN;
    if (v.empty()) return;
    std::mt19937_64 g(seed);
    vector<double> bs(B);
    for (int b = 0; b < B; b++) {
        double s = 0;
        for (size_t i = 0; i < v.size(); i++) s += v[g() % v.size()];
        bs[b] = s / v.size();
    }
    std::sort(bs.begin(), bs.end());
    lo = bs[(size_t)(0.025 * B)];
    hi = bs[std::min((size_t)B - 1, (size_t)(0.975 * B))];
}

#endif
