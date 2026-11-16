// llrp_tools -- common helpers (C++11, no external libraries)
#ifndef LLRP_TOOLS_COMMON_HPP
#define LLRP_TOOLS_COMMON_HPP
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>
#include <vector>

using std::string;
using std::vector;
using std::map;
using std::set;
using std::pair;

[[noreturn]] static void die(const string &msg) {
    fprintf(stderr, "llrp_tools: %s\n", msg.c_str());
    exit(2);
}

static string fmt(const char *f, ...) {
    va_list ap;
    va_start(ap, f);
    char buf[4096];
    int n = vsnprintf(buf, sizeof buf, f, ap);
    va_end(ap);
    if (n < (int)sizeof buf) return string(buf, n < 0 ? 0 : n);
    string big(n + 1, '\0');
    va_start(ap, f);
    vsnprintf(&big[0], big.size(), f, ap);
    va_end(ap);
    big.resize(n);
    return big;
}

static const double NaN = std::numeric_limits<double>::quiet_NaN();
static inline bool isnan_(double x) { return x != x; }

static vector<string> split(const string &s, char sep) {
    vector<string> out;
    string cur;
    for (char c : s) {
        if (c == sep) { out.push_back(cur); cur.clear(); }
        else cur += c;
    }
    out.push_back(cur);
    return out;
}
static string trim(const string &s) {
    size_t a = 0, b = s.size();
    while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r' || s[a] == '\n')) a++;
    while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r' || s[b - 1] == '\n')) b--;
    return s.substr(a, b - a);
}
static bool starts_with(const string &s, const string &p) { return s.size() >= p.size() && s.compare(0, p.size(), p) == 0; }
static bool ends_with(const string &s, const string &p) { return s.size() >= p.size() && s.compare(s.size() - p.size(), p.size(), p) == 0; }
static string join(const vector<string> &v, const string &sep) {
    string s;
    for (size_t i = 0; i < v.size(); i++) { if (i) s += sep; s += v[i]; }
    return s;
}

// ---- files -------------------------------------------------------------------------------------------------------
static bool file_exists(const string &p) { struct stat st; return stat(p.c_str(), &st) == 0 && S_ISREG(st.st_mode); }
static bool dir_exists(const string &p) { struct stat st; return stat(p.c_str(), &st) == 0 && S_ISDIR(st.st_mode); }
static vector<string> list_dir(const string &p) {
    vector<string> out;
    DIR *d = opendir(p.c_str());
    if (!d) return out;
    while (struct dirent *e = readdir(d)) {
        string n = e->d_name;
        if (n != "." && n != "..") out.push_back(n);
    }
    closedir(d);
    return out;
}
static string base_name(const string &p) {
    string s = p;
    while (s.size() > 1 && s.back() == '/') s.pop_back();
    size_t k = s.rfind('/');
    return k == string::npos ? s : s.substr(k + 1);
}
static string dir_name(const string &p) {
    size_t k = p.rfind('/');
    return k == string::npos ? string(".") : (k == 0 ? string("/") : p.substr(0, k));
}
static void mkdir_p(const string &p) {
    string cur;
    for (size_t i = 0; i <= p.size(); i++) {
        if (i == p.size() || p[i] == '/') {
            if (!cur.empty() && !dir_exists(cur)) mkdir(cur.c_str(), 0755);
        }
        if (i < p.size()) cur += p[i];
    }
}
static string read_all(const string &p) {
    std::ifstream f(p.c_str(), std::ios::binary);
    if (!f) die("cannot read " + p);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}
static void write_all(const string &p, const string &s) {
    FILE *f = fopen(p.c_str(), "wb");
    if (!f) die("cannot write " + p);
    fwrite(s.data(), 1, s.size(), f);
    fclose(f);
}

// natural ordering: "Ch50-5" < "Ch100-10", "s2" < "s10"
static bool nat_less(const string &a, const string &b) {
    size_t i = 0, j = 0;
    while (i < a.size() && j < b.size()) {
        if (isdigit((unsigned char)a[i]) && isdigit((unsigned char)b[j])) {
            size_t i2 = i, j2 = j;
            while (i2 < a.size() && isdigit((unsigned char)a[i2])) i2++;
            while (j2 < b.size() && isdigit((unsigned char)b[j2])) j2++;
            string x = a.substr(i, i2 - i), y = b.substr(j, j2 - j);
            while (x.size() > 1 && x[0] == '0') x.erase(0, 1);
            while (y.size() > 1 && y[0] == '0') y.erase(0, 1);
            if (x.size() != y.size()) return x.size() < y.size();
            if (x != y) return x < y;
            i = i2; j = j2;
        } else {
            if (a[i] != b[j]) return a[i] < b[j];
            i++; j++;
        }
    }
    return (a.size() - i) < (b.size() - j);
}

// ---- CSV ---------------------------------------------------------------------------------------------------------
static vector<string> parse_csv_line(const string &line) {
    vector<string> out;
    string cur;
    bool q = false;
    for (size_t i = 0; i < line.size(); i++) {
        char c = line[i];
        if (q) {
            if (c == '"') { if (i + 1 < line.size() && line[i + 1] == '"') { cur += '"'; i++; } else q = false; }
            else cur += c;
        } else if (c == '"') q = true;
        else if (c == ',') { out.push_back(cur); cur.clear(); }
        else if (c != '\r') cur += c;
    }
    out.push_back(cur);
    return out;
}

// canonical headers of the files written by llrp_fast (one source of truth for the whole kit)
static const char *HDR_RUN = "Instance,Algorithm,Run,Seed,Feasible,Total Latency,Reference BKS,Gap to BKS (%),CPU Time,Open Depots,Number of Routes,Actual Open Depot Count,Required Ng,Actual Route Count,Required Nv,Max Route Load,Vehicle Capacity,Total Demand,Total Vehicle Capacity,Nv,Ng,Iterations,Stop Reason,Last Improvement Iteration,Last Improvement CPU,Wall Time,Move Evaluations";
static const char *HDR_ROUTES = "Instance,Algorithm,Seed,Route ID,Depot,Customers,Arrival Times,Number of Customers,Load,Route Latency,Open Route Distance";
static const char *HDR_ITER = "Instance,Algorithm,Run,Seed,Iteration,Mode,Feasible,Current Total Latency,Best Latency So Far,Improved Best,BKS/Reference,Gap (%),Open Depots,Number of Routes,Nv,Ng,CPU Time";
static const char *HDR_OPS = "Instance,Algorithm,Seed,Operator,Calls,Evaluations,Applied,Gain Latency,Gain Objective,CPU Seconds,Best Iteration Applied,Best Iteration Gain Latency";
static const char *HDR_TRACE = "Instance,Algorithm,Seed,Iteration,CPU Seconds,Best Latency";
static const char *kind_header(const string &kind) {
    if (kind == "run") return HDR_RUN;
    if (kind == "routes") return HDR_ROUTES;
    if (kind == "iter") return HDR_ITER;
    if (kind == "ops") return HDR_OPS;
    if (kind == "trace") return HDR_TRACE;
    die("unknown result kind '" + kind + "'");
}
static const char *KINDS[] = {"run", "routes", "iter", "ops", "trace"};

struct Tbl {
    vector<string> hdr;
    vector<vector<string> > rows;
    int col(const string &name) const {
        for (size_t i = 0; i < hdr.size(); i++) if (hdr[i] == name) return (int)i;
        die("column '" + name + "' not found");
    }
};

static double to_num(const string &s) {
    if (s.empty()) return NaN;
    char *e = 0;
    double v = strtod(s.c_str(), &e);
    if (e == s.c_str()) return NaN;
    return v;
}
static bool to_bool(const string &s) { return s == "True" || s == "true" || s == "1"; }

// calls cb(fields) for every data row of a result CSV (merged file with header, or a per-run file without one)
static void scan_csv(const string &path, const vector<string> &default_hdr, vector<string> &hdr_out,
                     const std::function<void(const vector<string> &)> &cb) {
    std::ifstream f(path.c_str());
    if (!f) die("cannot read " + path);
    string line;
    hdr_out = default_hdr;
    while (std::getline(f, line)) {
        if (line.empty() || line == "\r") continue;
        vector<string> r = parse_csv_line(line);
        if (!r.empty() && r[0] == "Instance") { hdr_out = r; continue; }
        cb(r);
    }
}

// the files of one result kind inside DIR: DIR/kind.csv (merged) or DIR/*.kind.csv and DIR/runs/*.kind.csv (per run)
static vector<string> kind_files(const string &dir, const string &kind) {
    vector<string> out;
    if (file_exists(dir + "/" + kind + ".csv")) { out.push_back(dir + "/" + kind + ".csv"); return out; }
    vector<string> cand;
    for (int pass = 0; pass < 2; pass++) {
        string d = pass == 0 ? dir : dir + "/runs";
        vector<string> names = list_dir(d);
        for (size_t i = 0; i < names.size(); i++)
            if (ends_with(names[i], "." + kind + ".csv")) cand.push_back(d + "/" + names[i]);
    }
    std::sort(cand.begin(), cand.end(), nat_less);
    return cand;
}
static vector<string> hdr_vec(const char *h) { return split(h, ','); }

static Tbl load_tbl(const string &dir, const string &kind) {
    Tbl t;
    t.hdr = hdr_vec(kind_header(kind));
    vector<string> files = kind_files(dir, kind);
    for (size_t i = 0; i < files.size(); i++) {
        vector<string> h;
        scan_csv(files[i], t.hdr, h, [&](const vector<string> &r) { t.rows.push_back(r); });
        if (h != t.hdr && !t.rows.empty() && i == 0) t.hdr = h;
    }
    return t;
}

// ---- command-line helpers ----------------------------------------------------------------------------------------
struct Args {
    vector<string> pos;
    map<string, string> opt;
    Args(int argc, char **argv, int from, const set<string> &flags_without_value = set<string>()) {
        for (int i = from; i < argc; i++) {
            string a = argv[i];
            if (a.size() > 1 && a[0] == '-' && !isdigit((unsigned char)a[1]) && a[1] != '.') {
                if (flags_without_value.count(a)) { opt[a] = "1"; continue; }
                if (i + 1 >= argc) die("missing value for " + a);
                opt[a] = argv[++i];
            } else pos.push_back(a);
        }
    }
    bool has(const string &k) const { return opt.count(k) > 0; }
    string get(const string &k, const string &d = "") const { map<string, string>::const_iterator it = opt.find(k); return it == opt.end() ? d : it->second; }
    double num(const string &k, double d) const { return has(k) ? atof(get(k).c_str()) : d; }
    long long inum(const string &k, long long d) const { return has(k) ? atoll(get(k).c_str()) : d; }
};

// ---- instance files (*.inst) -------------------------------------------------------------------------------------
struct Instance {
    string name;
    int n = 0, m = 0, Nv = 0, Ng = 0;
    double Q = 0, bks = NaN;
    vector<pair<double, double> > depots;
    struct C { double x, y, d; };
    vector<C> cust;
    double total_demand() const { double s = 0; for (size_t i = 0; i < cust.size(); i++) s += cust[i].d; return s; }
};
static Instance read_instance(const string &path) {
    std::ifstream f(path.c_str());
    if (!f) die("cannot read instance " + path);
    Instance I;
    string tok;
    f >> tok;
    if (tok != "LLRP_INSTANCE") die("not an LLRP instance file: " + path);
    f >> tok;                                         // format version
    while (f >> tok) {
        if (tok == "name") f >> I.name;
        else if (tok == "n") f >> I.n;
        else if (tok == "m") f >> I.m;
        else if (tok == "Nv") f >> I.Nv;
        else if (tok == "Ng") f >> I.Ng;
        else if (tok == "Q") f >> I.Q;
        else if (tok == "bks") f >> I.bks;
        else if (tok == "depots") { for (int i = 0; i < I.m; i++) { double x, y; f >> x >> y; I.depots.push_back(std::make_pair(x, y)); } }
        else if (tok == "customers") { for (int i = 0; i < I.n; i++) { Instance::C c; f >> c.x >> c.y >> c.d; I.cust.push_back(c); } }
        else if (tok == "dist_hex") break;            // optional cross-check block (ignored here)
    }
    if ((int)I.depots.size() != I.m || (int)I.cust.size() != I.n) die("incomplete instance file " + path);
    return I;
}

#endif
