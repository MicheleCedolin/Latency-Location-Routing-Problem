// llrp_tools -- manifest, select, merge, check-csv, verify, summarize, compare, calibrate
#ifndef LLRP_TOOLS_CORE_HPP
#define LLRP_TOOLS_CORE_HPP
#include "tools_stats.hpp"

static double nz(double x) { return isnan_(x) ? NaN : x; }
static const char *OPCOLS[8] = {"Calls", "Evaluations", "Applied", "Gain Latency", "Gain Objective", "CPU Seconds", "Best Iteration Applied", "Best Iteration Gain Latency"};

// ================================================================================================ manifest
struct MEntry {
    string family, name, size, flag;
    int n = 0, m = 0, Nv = 0, Ng = 0, minveh = 0;
    double Q = 0, bks = NaN, demand = 0, tight = 0;
};
static string size_class(int n, const vector<int> &thr) {            // thresholds ascending: n < thr[0] -> S, < thr[1] -> M, < thr[2] -> L, else XL
    static const char *lab[] = {"S", "M", "L", "XL"};
    size_t k = 0;
    while (k < thr.size() && n >= thr[k]) k++;
    return lab[std::min<size_t>(k, 3)];
}
static int family_rank(const string &f) { return f == "barreto" ? 0 : f == "tuzun" ? 1 : f == "prins" ? 2 : 3; }

static vector<MEntry> load_manifest(const string &path) {
    vector<MEntry> out;
    std::ifstream f(path.c_str());
    if (!f) die("cannot read manifest " + path + "  (create it with: llrp_tools manifest inst)");
    string line;
    std::getline(f, line);                                         // header
    vector<string> h = split(trim(line), '\t');
    map<string, int> ix;
    for (size_t i = 0; i < h.size(); i++) ix[h[i]] = (int)i;
    const char *need[] = {"family", "name", "n", "m", "Q", "Nv", "Ng", "bks", "total_demand", "min_vehicles", "tightness", "size", "flag"};
    for (size_t i = 0; i < sizeof(need) / sizeof(need[0]); i++) if (!ix.count(need[i])) die(string("manifest column missing: ") + need[i]);
    while (std::getline(f, line)) {
        if (trim(line).empty()) continue;
        vector<string> r = split(line, '\t');
        while (r.size() < h.size()) r.push_back("");
        MEntry e;
        e.family = r[ix["family"]]; e.name = r[ix["name"]]; e.size = r[ix["size"]]; e.flag = r[ix["flag"]];
        e.n = atoi(r[ix["n"]].c_str()); e.m = atoi(r[ix["m"]].c_str()); e.Nv = atoi(r[ix["Nv"]].c_str()); e.Ng = atoi(r[ix["Ng"]].c_str());
        e.minveh = atoi(r[ix["min_vehicles"]].c_str());
        e.Q = atof(r[ix["Q"]].c_str()); e.bks = atof(r[ix["bks"]].c_str()); e.demand = atof(r[ix["total_demand"]].c_str()); e.tight = atof(r[ix["tightness"]].c_str());
        out.push_back(e);
    }
    return out;
}

// instance-name list (one 'family/name' or 'name' [.inst] per line; '#' comments) -> set of instance names
static set<string> load_name_set(const string &path) {
    set<string> s;
    std::ifstream f(path.c_str());
    if (!f) die("cannot read " + path);
    string line;
    while (std::getline(f, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        size_t sp = line.find_first_of(" \t");
        if (sp != string::npos) line = line.substr(0, sp);
        size_t k = line.rfind('/');
        if (k != string::npos) line = line.substr(k + 1);
        if (ends_with(line, ".inst")) line = line.substr(0, line.size() - 5);
        s.insert(line);
    }
    return s;
}

static int cmd_manifest(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools manifest INSTROOT [--out manifest.tsv] [--bins 60,130,180]   (INSTROOT/<family>/*.inst)");
    const string root = A.pos[0];
    const string outp = A.get("--out", "manifest.tsv");
    vector<int> thr;
    { vector<string> b = split(A.get("--bins", "60,130,180"), ','); for (size_t i = 0; i < b.size(); i++) thr.push_back(atoi(b[i].c_str())); }
    if (thr.empty() || thr.size() > 3 || !std::is_sorted(thr.begin(), thr.end())) die("--bins: 1-3 ascending thresholds, e.g. 60,130,180");
    static const char *SUSPECT[] = {"50-5-2BIS-5", "50-5-2b-5", "50-5-2bBIS-5"};
    vector<string> fams = list_dir(root);
    vector<string> fl;
    for (size_t i = 0; i < fams.size(); i++) if (dir_exists(root + "/" + fams[i])) fl.push_back(fams[i]);
    std::sort(fl.begin(), fl.end(), [](const string &a, const string &c) { int ra = family_rank(a), rc = family_rank(c); return ra != rc ? ra < rc : a < c; });
    if (fl.empty()) die("no family folders under " + root);
    vector<MEntry> all;
    set<string> seen;
    int nerr = 0;
    for (size_t fi = 0; fi < fl.size(); fi++) {
        vector<string> names = list_dir(root + "/" + fl[fi]), insts;
        for (size_t i = 0; i < names.size(); i++) if (ends_with(names[i], ".inst")) insts.push_back(names[i].substr(0, names[i].size() - 5));
        std::sort(insts.begin(), insts.end(), nat_less);
        for (size_t i = 0; i < insts.size(); i++) {
            Instance I = read_instance(root + "/" + fl[fi] + "/" + insts[i] + ".inst");
            MEntry e;
            e.family = fl[fi]; e.name = insts[i]; e.n = I.n; e.m = I.m; e.Q = I.Q; e.Nv = I.Nv; e.Ng = I.Ng; e.bks = I.bks;
            e.demand = I.total_demand();
            e.minveh = (int)std::ceil(e.demand / e.Q - 1e-9);
            e.tight = e.demand / (e.Nv * e.Q);
            e.size = size_class(e.n, thr);
            vector<string> fg;
            if (I.name != insts[i]) fg.push_back("ERROR:file-name!=header-name");
            if (e.Nv < e.minveh) fg.push_back("ERROR:Nv<ceil(demand/Q)");
            if (e.Nv * e.Q < e.demand - 1e-9) fg.push_back("ERROR:Nv*Q<demand");
            if (e.Ng < 1 || e.Ng > e.m) fg.push_back("ERROR:Ng-out-of-range");
            if (isnan_(e.bks) || e.bks <= 0) fg.push_back("WARN:no-bks");
            for (size_t k = 0; k < sizeof(SUSPECT) / sizeof(SUSPECT[0]); k++)
                if (e.name == SUSPECT[k]) fg.push_back("CHECK:Nv/Ng-tablo-kod-uyusmazligi-suphesi(dogrulayin)");
            if (seen.count(e.name)) fg.push_back("ERROR:duplicate-name");
            seen.insert(e.name);
            for (size_t k = 0; k < fg.size(); k++) if (starts_with(fg[k], "ERROR")) nerr++;
            e.flag = fg.empty() ? "-" : join(fg, ";");
            all.push_back(e);
        }
    }
    FILE *o = fopen(outp.c_str(), "w");
    if (!o) die("cannot write " + outp);
    fprintf(o, "family\tname\tn\tm\tQ\tNv\tNg\tbks\ttotal_demand\tmin_vehicles\ttightness\tsize\tflag\n");
    for (size_t i = 0; i < all.size(); i++) {
        const MEntry &e = all[i];
        fprintf(o, "%s\t%s\t%d\t%d\t%.10g\t%d\t%d\t%.10g\t%.10g\t%d\t%.4f\t%s\t%s\n", e.family.c_str(), e.name.c_str(), e.n, e.m, e.Q, e.Nv, e.Ng, e.bks, e.demand,
                e.minveh, e.tight, e.size.c_str(), e.flag.c_str());
    }
    fclose(o);
    printf("%-8s %-14s %5s %4s %9s %4s %3s %10s %7s %4s  %s\n", "family", "name", "n", "m", "Q", "Nv", "Ng", "bks", "tight", "size", "flag");
    for (size_t i = 0; i < all.size(); i++) {
        const MEntry &e = all[i];
        printf("%-8s %-14s %5d %4d %9.6g %4d %3d %10.2f %7.3f %4s  %s\n", e.family.c_str(), e.name.c_str(), e.n, e.m, e.Q, e.Nv, e.Ng, e.bks, e.tight, e.size.c_str(), e.flag.c_str());
    }
    map<string, int> cnt;
    for (size_t i = 0; i < all.size(); i++) cnt[all[i].family + " " + all[i].size]++;
    printf("\nmanifest: %zu instances -> %s   (boyut siniflari: S n<%d", all.size(), outp.c_str(), thr[0]);
    { const char *lab[] = {"M", "L", "XL"}; for (size_t i = 1; i < thr.size(); i++) printf(", %s n<%d", lab[i - 1], thr[i]); printf(", %s n>=%d)\n", thr.size() == 1 ? "M" : thr.size() == 2 ? "L" : "XL", thr.back()); }
    for (map<string, int>::iterator it = cnt.begin(); it != cnt.end(); ++it) printf("  %-12s %3d\n", it->first.c_str(), it->second);
    printf("hatali satir: %d\n", nerr);
    return nerr ? 1 : 0;
}

// ================================================================================================ select (stratified, deterministic)
struct SplitMix {
    unsigned long long s;
    explicit SplitMix(unsigned long long seed) : s(seed) {}
    unsigned long long next() {
        unsigned long long z = (s += 0x9e3779b97f4a7c15ULL);
        z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
        z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
        return z ^ (z >> 31);
    }
};

static int cmd_select(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools select MANIFEST [--k 2] [--seed 1] [--out-dir selection]");
    vector<MEntry> M = load_manifest(A.pos[0]);
    const int k = (int)A.inum("--k", 2);
    SplitMix rng((unsigned long long)A.inum("--seed", 1));
    const string od = A.get("--out-dir", "selection");
    mkdir_p(od);
    // features (min-max scaled over the whole manifest): log n, depot density m/n, open depots Ng, capacity tightness
    const size_t N = M.size();
    vector<vector<double> > F(N, vector<double>(4));
    for (size_t i = 0; i < N; i++) { F[i][0] = std::log((double)M[i].n); F[i][1] = (double)M[i].m / M[i].n; F[i][2] = M[i].Ng; F[i][3] = M[i].tight; }
    for (int c = 0; c < 4; c++) {
        double lo = INFINITY, hi = -INFINITY;
        for (size_t i = 0; i < N; i++) { lo = std::min(lo, F[i][c]); hi = std::max(hi, F[i][c]); }
        for (size_t i = 0; i < N; i++) F[i][c] = hi > lo ? (F[i][c] - lo) / (hi - lo) : 0.0;
    }
    map<string, vector<size_t> > cells;
    vector<string> cell_order;
    for (size_t i = 0; i < N; i++) {
        string key = M[i].family + "|" + M[i].size;
        if (!cells.count(key)) cell_order.push_back(key);
        cells[key].push_back(i);
    }
    std::sort(cell_order.begin(), cell_order.end(), [&](const string &a, const string &b) {
        size_t ia = cells[a][0], ib = cells[b][0];
        int ra = family_rank(M[ia].family), rb = family_rank(M[ib].family);
        if (ra != rb) return ra < rb;
        return a < b;
    });
    vector<char> train(N, 0);
    for (size_t ci = 0; ci < cell_order.size(); ci++) {
        vector<size_t> &c = cells[cell_order[ci]];
        std::sort(c.begin(), c.end(), [&](size_t a, size_t b) { return nat_less(M[a].name, M[b].name); });
        vector<size_t> el;                                       // instances with a doubtful parameter record (flag CHECK/ERROR) never enter the training set
        for (size_t q = 0; q < c.size(); q++) if (M[c[q]].flag.find("CHECK") == string::npos && M[c[q]].flag.find("ERROR") == string::npos) el.push_back(c[q]);
        if (el.empty()) continue;
        const size_t take = std::min((size_t)k, el.size());
        vector<size_t> chosen;
        if (take == el.size()) chosen = el;
        else {
            chosen.push_back(el[rng.next() % el.size()]);
            while (chosen.size() < take) {                       // farthest-point (max-min distance) in feature space
                size_t best = el[0];
                double bd = -1;
                for (size_t a = 0; a < el.size(); a++) {
                    if (std::find(chosen.begin(), chosen.end(), el[a]) != chosen.end()) continue;
                    double dmin = INFINITY;
                    for (size_t b = 0; b < chosen.size(); b++) {
                        double s = 0;
                        for (int q = 0; q < 4; q++) { double df = F[el[a]][q] - F[chosen[b]][q]; s += df * df; }
                        dmin = std::min(dmin, std::sqrt(s));
                    }
                    if (dmin > bd + 1e-12) { bd = dmin; best = el[a]; }
                }
                chosen.push_back(best);
            }
        }
        for (size_t q = 0; q < chosen.size(); q++) train[chosen[q]] = 1;
    }
    FILE *ft = fopen((od + "/train.txt").c_str(), "w"), *fe = fopen((od + "/test.txt").c_str(), "w"), *fs = fopen((od + "/selection.tsv").c_str(), "w");
    if (!ft || !fe || !fs) die("cannot write into " + od);
    fprintf(fs, "set\tfamily\tname\tn\tm\tNv\tNg\ttightness\tsize\n");
    printf("Stratifiye secim: katman = aile x boyut sinifi, katman basina k=%d, tohum=%lld (farthest-point; ozellikler: log n, m/n, Ng, kapasite sikligi)\n", k, A.inum("--seed", 1));
    printf("%-6s %-8s %-14s %5s %4s %4s %3s %7s %4s\n", "kume", "aile", "ornek", "n", "m", "Nv", "Ng", "sikilik", "boyut");
    int nt = 0, ne = 0;
    for (size_t pass = 0; pass < 2; pass++)
        for (size_t i = 0; i < N; i++) {
            if ((pass == 0) != (train[i] != 0)) continue;
            const MEntry &e = M[i];
            if (pass == 0) { fprintf(ft, "%s/%s\n", e.family.c_str(), e.name.c_str()); nt++; } else { fprintf(fe, "%s/%s\n", e.family.c_str(), e.name.c_str()); ne++; }
            fprintf(fs, "%s\t%s\t%s\t%d\t%d\t%d\t%d\t%.4f\t%s\n", pass == 0 ? "train" : "test", e.family.c_str(), e.name.c_str(), e.n, e.m, e.Nv, e.Ng, e.tight, e.size.c_str());
            if (pass == 0) printf("%-6s %-8s %-14s %5d %4d %4d %3d %7.3f %4s\n", "EGITIM", e.family.c_str(), e.name.c_str(), e.n, e.m, e.Nv, e.Ng, e.tight, e.size.c_str());
        }
    fclose(ft); fclose(fe); fclose(fs);
    map<string, pair<int, int> > per;
    for (size_t i = 0; i < N; i++) { if (train[i]) per[M[i].family].first++; else per[M[i].family].second++; }
    printf("\negitim=%d  test=%d   (", nt, ne);
    for (map<string, pair<int, int> >::iterator it = per.begin(); it != per.end(); ++it) printf("%s %d/%d  ", it->first.c_str(), it->second.first, it->second.first + it->second.second);
    printf(")\nyazildi: %s/train.txt  %s/test.txt  %s/selection.tsv\n", od.c_str(), od.c_str(), od.c_str());
    return 0;
}

// ================================================================================================ merge / check-csv
static int cmd_merge(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools merge DIR      (DIR/runs/*.KIND.csv -> DIR/KIND.csv with the canonical header)");
    const string dir = A.pos[0];
    int total = 0;
    for (size_t k = 0; k < sizeof(KINDS) / sizeof(KINDS[0]); k++) {
        const string kind = KINDS[k];
        vector<string> names = list_dir(dir + "/runs"), files;
        for (size_t i = 0; i < names.size(); i++) if (ends_with(names[i], "." + kind + ".csv")) files.push_back(names[i]);
        if (files.empty()) continue;
        std::sort(files.begin(), files.end(), nat_less);
        FILE *o = fopen((dir + "/" + kind + ".csv").c_str(), "w");
        if (!o) die("cannot write " + dir + "/" + kind + ".csv");
        fprintf(o, "%s\n", kind_header(kind));
        for (size_t i = 0; i < files.size(); i++) {
            string s = read_all(dir + "/runs/" + files[i]);
            if (!s.empty() && s[s.size() - 1] != '\n') s += '\n';
            fwrite(s.data(), 1, s.size(), o);
        }
        fclose(o);
        if (kind == "run") total = (int)files.size();
    }
    printf("birlestirildi: %s  (%d kosu)\n", dir.c_str(), total);
    return 0;
}

static int cmd_check_csv(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools check-csv DIR      (merged CSV headers and column counts)");
    int bad = 0, seen = 0;
    for (size_t k = 0; k < sizeof(KINDS) / sizeof(KINDS[0]); k++) {
        const string p = A.pos[0] + "/" + KINDS[k] + ".csv";
        if (!file_exists(p)) continue;
        seen++;
        std::ifstream f(p.c_str());
        string line;
        std::getline(f, line);
        vector<string> h = parse_csv_line(line), want = hdr_vec(kind_header(KINDS[k]));
        if (h != want) { printf("baslik uyusmuyor: %s\n", p.c_str()); bad++; continue; }
        long badrows = 0;
        while (std::getline(f, line)) { if (line.empty()) continue; if (parse_csv_line(line).size() != want.size()) badrows++; }
        if (badrows) { printf("%ld satirda sutun sayisi hatali: %s\n", badrows, p.c_str()); bad++; }
    }
    printf("CSV basliklari/sutunlari: %s (%d dosya)\n", bad || !seen ? "BASARISIZ" : "TAMAM", seen);
    return bad || !seen ? 1 : 0;
}

// ================================================================================================ verify (independent re-computation)
static vector<int> parse_int_list(const string &s) {                // "[2, 3]" -> {2,3}
    vector<int> v;
    string cur;
    for (size_t i = 0; i <= s.size(); i++) {
        if (i < s.size() && (isdigit((unsigned char)s[i]) || s[i] == '-')) cur += s[i];
        else { if (!cur.empty()) v.push_back(atoi(cur.c_str())); cur.clear(); }
    }
    return v;
}
static vector<string> split_arrow(const string &s) {
    vector<string> out;
    size_t i = 0;
    while (true) {
        size_t k = s.find(" -> ", i);
        if (k == string::npos) { out.push_back(s.substr(i)); break; }
        out.push_back(s.substr(i, k - i));
        i = k + 4;
    }
    return out;
}
static bool verify_one(const Instance &I, const string &prefix, double &total_out, string &msg) {
    const double tol = 1e-6;
    vector<string> errs;
    std::ifstream fr((prefix + ".run.csv").c_str());
    if (!fr) { msg = "no " + prefix + ".run.csv"; return false; }
    string line;
    std::getline(fr, line);
    vector<string> run = parse_csv_line(line);
    if (run.size() < 10) { msg = "malformed run.csv"; return false; }
    const double reported = atof(run[5].c_str());
    const bool feas_reported = run[4] == "True";
    vector<int> depots_rep = parse_int_list(run[9]);
    std::ifstream fo((prefix + ".routes.csv").c_str());
    if (!fo) { msg = "no " + prefix + ".routes.csv (run with --out-level >= 1)"; return false; }
    vector<int> seen;
    set<int> open_set;
    double total = 0.0;
    int nroutes = 0;
    while (std::getline(fo, line)) {
        if (line.empty()) continue;
        vector<string> r = parse_csv_line(line);
        if (r.size() < 10) { errs.push_back("malformed routes.csv row"); continue; }
        nroutes++;
        const int dep = atoi(r[4].c_str());
        vector<string> cs = split_arrow(r[5]), as = split_arrow(r[6]);
        if (dep < 0 || dep >= I.m) { errs.push_back("depot index out of range"); continue; }
        open_set.insert(dep);
        double px = I.depots[dep].first, py = I.depots[dep].second, t = 0, lat = 0, load = 0;
        for (size_t q = 0; q < cs.size(); q++) {
            const int c = atoi(cs[q].c_str());
            if (c < 0 || c >= I.n) { errs.push_back("customer index out of range"); break; }
            t += std::hypot(px - I.cust[c].x, py - I.cust[c].y);
            lat += t; load += I.cust[c].d; px = I.cust[c].x; py = I.cust[c].y;
            seen.push_back(c);
            if (q < as.size() && std::fabs(t - atof(as[q].c_str())) > 0.0051) errs.push_back(fmt("arrival time mismatch route %s pos %zu: %.4f vs %s", r[3].c_str(), q, t, as[q].c_str()));
        }
        if (std::fabs(lat - atof(r[9].c_str())) > tol * std::max(1.0, lat)) errs.push_back(fmt("route latency mismatch route %s: %.9g vs %s", r[3].c_str(), lat, r[9].c_str()));
        if (std::fabs(load - atof(r[8].c_str())) > 1e-6) errs.push_back("load mismatch route " + r[3]);
        if (load > I.Q + 1e-4) errs.push_back(fmt("capacity exceeded on route %s: %.6g > %.6g", r[3].c_str(), load, I.Q));
        total += lat;
    }
    std::sort(seen.begin(), seen.end());
    bool part = (int)seen.size() == I.n;
    for (size_t i = 0; part && i < seen.size(); i++) if (seen[i] != (int)i) part = false;
    if (!part) errs.push_back("customers are not a partition of 0..n-1");
    if (nroutes > I.Nv) errs.push_back(fmt("%d routes > Nv=%d", nroutes, I.Nv));
    if ((int)open_set.size() > I.Ng) errs.push_back(fmt("%zu open depots > Ng=%d", open_set.size(), I.Ng));   // v5: en fazla Ng depo (>=1); eski kosular tam Ng acar, hala gecerli
    vector<int> os(open_set.begin(), open_set.end()), dr = depots_rep;
    std::sort(dr.begin(), dr.end());
    if (os != dr) errs.push_back("open depots in run.csv differ from the routes");
    if (std::fabs(total - reported) > tol * std::max(1.0, total)) errs.push_back(fmt("total latency recomputed %.12g != reported %.12g", total, reported));
    if (feas_reported && !errs.empty()) errs.push_back("reported feasible but violations found");
    total_out = total;
    msg = join(errs, "; ");
    return errs.empty();
}
static int cmd_verify(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.size() < 2) die("usage: llrp_tools verify INSTANCE.inst PREFIX [PREFIX ...]     (exit code 0 = all runs verified)");
    Instance I = read_instance(A.pos[0]);
    int bad = 0;
    for (size_t i = 1; i < A.pos.size(); i++) {
        double tot = 0;
        string msg;
        bool ok = verify_one(I, A.pos[i], tot, msg);
        printf("%s%s  latency=%.6f%s%s\n", ok ? "OK   " : "FAIL ", A.pos[i].c_str(), tot, ok ? "" : "  ", msg.c_str());
        bad += !ok;
    }
    return bad ? 1 : 0;
}

// ================================================================================================ summarize
struct GroupAgg { vector<double> gb, go, cp; };
static int cmd_summarize(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools summarize DIR|run.csv [--csv out.csv] [--manifest manifest.tsv] [--train train.txt]");
    string d = A.pos[0];
    if (ends_with(d, ".csv")) d = dir_name(d);
    Tbl T = load_tbl(d, "run");
    if (T.rows.empty()) die("run.csv is empty / not found: " + d);
    const int cI = T.col("Instance"), cA = T.col("Algorithm"), cF = T.col("Feasible"), cL = T.col("Total Latency"), cB = T.col("Reference BKS"), cC = T.col("CPU Time"),
              cIt = T.col("Iterations"), cLi = T.col("Last Improvement Iteration"), cS = T.col("Stop Reason");
    map<pair<string, string>, vector<const vector<string> *> > g;
    for (size_t i = 0; i < T.rows.size(); i++) g[std::make_pair(T.rows[i][cI], T.rows[i][cA])].push_back(&T.rows[i]);
    vector<pair<string, string> > keys;
    for (map<pair<string, string>, vector<const vector<string> *> >::iterator it = g.begin(); it != g.end(); ++it) keys.push_back(it->first);
    std::sort(keys.begin(), keys.end(), [](const pair<string, string> &a, const pair<string, string> &b) { return nat_less(a.first, b.first); });
    map<string, MEntry> man;
    bool have_man = A.has("--manifest");
    if (have_man) { vector<MEntry> M = load_manifest(A.get("--manifest")); for (size_t i = 0; i < M.size(); i++) man[M[i].name] = M[i]; }
    set<string> train;
    bool have_train = A.has("--train");
    if (have_train) train = load_name_set(A.get("--train"));
    printf("%-14s %4s %4s %12s %12s %12s %7s %7s %8s %6s %6s  %s\n", "ornek", "kosu", "uyg", "en_iyi", "ort", "std", "gapBest", "gapOrt", "cpu_ort", "iter", "sonIyi", "durma");
    vector<double> gb, go, cp;
    map<string, GroupAgg> by;                                    // 'ALL', family, 'family/size', 'EGITIM', 'TEST'
    FILE *csv = A.has("--csv") ? fopen(A.get("--csv").c_str(), "w") : 0;
    if (csv) fprintf(csv, "instance,runs,feasible,best,mean,std,gap_best,gap_mean,cpu_mean,iter_mean,last_impr_mean,stops\n");
    for (size_t q = 0; q < keys.size(); q++) {
        const vector<const vector<string> *> &rs = g[keys[q]];
        vector<double> lat, cpu, its, lis;
        int nf = 0;
        map<string, int> stops;
        for (size_t i = 0; i < rs.size(); i++) {
            const vector<string> &r = *rs[i];
            if (to_bool(r[cF])) { nf++; lat.push_back(to_num(r[cL])); }
            cpu.push_back(to_num(r[cC])); its.push_back(to_num(r[cIt])); lis.push_back(to_num(r[cLi]));
            stops[r[cS]]++;
        }
        if (lat.empty()) { printf("%-14s %4zu %4d  (uygun cozum yok)\n", keys[q].first.c_str(), rs.size(), 0); continue; }
        const double bks = to_num((*rs[0])[cB]);
        const double best = min_of(lat), mu = mean_of(lat), sd = sd_of(lat);
        const double gbest = bks > 0 ? 100.0 * (best - bks) / bks : NaN, gmean = bks > 0 ? 100.0 * (mu - bks) / bks : NaN;
        string st;
        for (map<string, int>::iterator it = stops.begin(); it != stops.end(); ++it) st += (st.empty() ? "" : " ") + it->first + ":" + std::to_string(it->second);
        printf("%-14s %4zu %4d %12.2f %12.2f %12.2f %7.3f %7.3f %8.2f %6.0f %6.0f  %s\n", keys[q].first.c_str(), rs.size(), nf, best, mu, nz(sd), gbest, gmean, mean_of(cpu), mean_of(its), mean_of(lis), st.c_str());
        if (csv) fprintf(csv, "%s,%zu,%d,%.6g,%.6g,%.6g,%.6g,%.6g,%.6g,%.6g,%.6g,\"%s\"\n", keys[q].first.c_str(), rs.size(), nf, best, mu, nz(sd), gbest, gmean, mean_of(cpu), mean_of(its), mean_of(lis), st.c_str());
        gb.push_back(gbest); go.push_back(gmean); cp.push_back(mean_of(cpu));
        GroupAgg *tg[5]; int nt = 0;
        tg[nt++] = &by["0 HEPSI"];
        if (have_man && man.count(keys[q].first)) {
            const MEntry &e = man[keys[q].first];
            tg[nt++] = &by["1 aile " + e.family];
            tg[nt++] = &by["2 aile/boyut " + e.family + "/" + e.size];
            if (have_train) tg[nt++] = &by[train.count(e.name) ? "3 EGITIM kumesi" : "3 TEST kumesi"];
        }
        for (int t = 0; t < nt; t++) { tg[t]->gb.push_back(gbest); tg[t]->go.push_back(gmean); tg[t]->cp.push_back(mean_of(cpu)); }
    }
    if (csv) fclose(csv);
    printf("%-14s %4s %4s %12s %12s %12s %7.3f %7.3f %8.2f   (ornek ortalamasi; ort. cpu = surec basina saniye)\n", "ORTALAMA", "", "", "", "", "", mean_of(gb), mean_of(go), mean_of(cp));
    if (by.size() > 1) {
        printf("\n%-26s %6s %8s %8s %9s %10s\n", "grup (ornek ortalamalari)", "ornek", "gapBest", "gapOrt", "cpu_ort", "cpu_toplam");
        for (map<string, GroupAgg>::iterator it = by.begin(); it != by.end(); ++it)
            printf("%-26s %6zu %8.3f %8.3f %9.2f %10.1f\n", it->first.substr(2).c_str(), it->second.go.size(), mean_of(it->second.gb), mean_of(it->second.go), mean_of(it->second.cp), sum_of(it->second.cp));
    }
    return 0;
}

// ================================================================================================ compare (paired, two result directories)
static int cmd_compare(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.size() != 2) die("usage: llrp_tools compare DIR_A DIR_B [--tol 1e-9]    B's improvement over A, paired by (instance, seed)");
    const double tol = A.num("--tol", 1e-9);
    struct R { double lat, bks, cpu; };
    vector<map<pair<string, int>, R> > M(2);
    for (int s = 0; s < 2; s++) {
        Tbl T = load_tbl(A.pos[s], "run");
        const int cI = T.col("Instance"), cS = T.col("Seed"), cF = T.col("Feasible"), cL = T.col("Total Latency"), cB = T.col("Reference BKS"), cC = T.col("CPU Time");
        for (size_t i = 0; i < T.rows.size(); i++) {
            const vector<string> &r = T.rows[i];
            if (!to_bool(r[cF])) continue;
            R x; x.lat = to_num(r[cL]); x.bks = to_num(r[cB]); x.cpu = to_num(r[cC]);
            M[s][std::make_pair(r[cI], atoi(r[cS].c_str()))] = x;
        }
    }
    vector<pair<string, int> > keys;
    for (map<pair<string, int>, R>::iterator it = M[0].begin(); it != M[0].end(); ++it) if (M[1].count(it->first)) keys.push_back(it->first);
    if (keys.empty()) die("no common (instance, seed) pairs");
    std::sort(keys.begin(), keys.end(), [](const pair<string, int> &a, const pair<string, int> &b) { return a.first != b.first ? nat_less(a.first, b.first) : a.second < b.second; });
    map<string, vector<pair<string, int> > > per;
    vector<string> order;
    for (size_t i = 0; i < keys.size(); i++) { if (!per.count(keys[i].first)) order.push_back(keys[i].first); per[keys[i].first].push_back(keys[i]); }
    printf("A = %s\nB = %s   (iyilesme = B'nin A'ya gore gecikme azalmasi, %% ; pozitif = B daha iyi)\n", A.pos[0].c_str(), A.pos[1].c_str());
    printf("%-14s %5s %9s %9s %9s %5s %5s %5s %8s %9s %9s\n", "ornek", "cift", "gapA%", "gapB%", "iyilesme%", "B>A", "esit", "B<A", "ayni%", "cpuA", "cpuB");
    vector<double> imp_inst, pair_d;
    double cA = 0, cB = 0;
    long ident = 0;
    for (size_t o = 0; o < order.size(); o++) {
        const vector<pair<string, int> > &ks = per[order[o]];
        vector<double> la, lb, imp, ca, cb;
        int win = 0, los = 0;
        for (size_t i = 0; i < ks.size(); i++) {
            const R &a = M[0][ks[i]], &b = M[1][ks[i]];
            la.push_back(a.lat); lb.push_back(b.lat); imp.push_back(100.0 * (a.lat - b.lat) / a.lat); ca.push_back(a.cpu); cb.push_back(b.cpu);
            if (b.lat < a.lat - tol * a.lat) win++; else if (b.lat > a.lat + tol * a.lat) los++;
        }
        const int tie = (int)ks.size() - win - los;
        const double bks = M[0][ks[0]].bks;
        cA += sum_of(ca); cB += sum_of(cb); ident += tie;
        imp_inst.push_back(mean_of(imp));
        pair_d.insert(pair_d.end(), imp.begin(), imp.end());
        printf("%-14s %5zu %9.3f %9.3f %9.3f %5d %5d %5d %8.1f %9.2f %9.2f\n", order[o].c_str(), ks.size(), 100.0 * (mean_of(la) - bks) / bks, 100.0 * (mean_of(lb) - bks) / bks, mean_of(imp), win, tie, los,
               100.0 * tie / ks.size(), mean_of(ca), mean_of(cb));
    }
    double lo, hi;
    bootstrap_ci_mean(imp_inst, 10000, 0, lo, hi);
    int ni = 0, np = 0;
    const double p_i = wilcoxon_p(imp_inst, &ni), p_p = wilcoxon_p(pair_d, &np);
    printf("\nOrnek duzeyi (n=%zu): ortalama iyilesme %.3f%%  (%%95 bootstrap GA [%.3f, %.3f]);  Wilcoxon p=%.4g (n_eff=%d), rank-biserial=%+.3f\n", imp_inst.size(), mean_of(imp_inst), lo, hi, p_i, ni, rank_biserial(imp_inst));
    printf("Cift duzeyi  (n=%zu): Wilcoxon p=%.4g (n_eff=%d), rank-biserial=%+.3f;  B'nin hicbir sey degistirmedigi cift orani: %.1f%% (%ld/%zu)\n", pair_d.size(), p_p, np, rank_biserial(pair_d),
           100.0 * ident / keys.size(), ident, keys.size());
    printf("Toplam CPU: A=%.1f s, B=%.1f s  -> B/A = %.3f\n", cA, cB, cA ? cB / cA : NaN);
    printf("Not: cift duzeyindeki p-degerleri ayni ornekten gelen seedleri bagimsiz sayar; ornek duzeyi daha muhafazakardir. Esit = gecikme farki <= tol*gecikme (tol=%g).\n", tol);
    return 0;
}

// ================================================================================================ calibrate (stall threshold from long runs)
static int cmd_calibrate(int argc, char **argv) {
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools calibrate DIR [--K 25,50,100,150,200,300] [--target 0.05]\n"
                           "  DIR: uzun kosular (ornegin MAXITER=600 STALL=0 OUTLEVEL=2) ; run.csv + trace.csv (+ iter.csv)");
    const string d = A.pos[0];
    vector<int> Ks;
    { vector<string> p = split(A.get("--K", "25,50,100,150,200,300"), ','); for (size_t i = 0; i < p.size(); i++) Ks.push_back(atoi(p[i].c_str())); }
    const double target = A.num("--target", 0.05);
    struct Run { vector<double> it, cpu, best; int horizon; double cpu_total, bks; string stop; vector<double> iter_cpu; };
    map<pair<string, int>, Run> data;
    {
        Tbl T = load_tbl(d, "run");
        const int cI = T.col("Instance"), cS = T.col("Seed"), cH = T.col("Iterations"), cC = T.col("CPU Time"), cB = T.col("Reference BKS"), cSt = T.col("Stop Reason");
        for (size_t i = 0; i < T.rows.size(); i++) {
            Run r;
            r.horizon = atoi(T.rows[i][cH].c_str()); r.cpu_total = to_num(T.rows[i][cC]); r.bks = to_num(T.rows[i][cB]); r.stop = T.rows[i][cSt];
            data[std::make_pair(T.rows[i][cI], atoi(T.rows[i][cS].c_str()))] = r;
        }
        Tbl X = load_tbl(d, "trace");
        const int tI = X.col("Instance"), tS = X.col("Seed"), tIt = X.col("Iteration"), tC = X.col("CPU Seconds"), tB = X.col("Best Latency");
        vector<vector<double> > rows;
        map<pair<string, int>, vector<vector<double> > > tr;
        for (size_t i = 0; i < X.rows.size(); i++) {
            vector<double> v(3);
            v[0] = atof(X.rows[i][tIt].c_str()); v[1] = to_num(X.rows[i][tC]); v[2] = to_num(X.rows[i][tB]);
            tr[std::make_pair(X.rows[i][tI], atoi(X.rows[i][tS].c_str()))].push_back(v);
        }
        for (map<pair<string, int>, Run>::iterator it = data.begin(); it != data.end();) {
            map<pair<string, int>, vector<vector<double> > >::iterator f = tr.find(it->first);
            if (f == tr.end()) { data.erase(it++); continue; }
            std::sort(f->second.begin(), f->second.end());
            for (size_t j = 0; j < f->second.size(); j++) { it->second.it.push_back(f->second[j][0]); it->second.cpu.push_back(f->second[j][1]); it->second.best.push_back(f->second[j][2]); }
            ++it;
        }
        if (file_exists(d + "/iter.csv") || !kind_files(d, "iter").empty()) {
            vector<string> files = kind_files(d, "iter"), hdr;
            for (size_t i = 0; i < files.size(); i++)
                scan_csv(files[i], hdr_vec(HDR_ITER), hdr, [&](const vector<string> &r) {
                    map<pair<string, int>, Run>::iterator f = data.find(std::make_pair(r[0], atoi(r[3].c_str())));
                    if (f == data.end()) return;
                    const size_t k = (size_t)atoi(r[4].c_str());
                    if (f->second.iter_cpu.size() <= k) f->second.iter_cpu.resize(k + 1, NaN);
                    f->second.iter_cpu[k] = atof(r[16].c_str());
                });
        }
    }
    if (data.empty()) die("trace/run not found: " + d);
    map<int, int> hz;
    map<string, int> stp;
    for (map<pair<string, int>, Run>::iterator it = data.begin(); it != data.end(); ++it) { hz[it->second.horizon]++; stp[it->second.stop]++; }
    printf("kosu sayisi: %zu   ufuk (iterasyon):", data.size());
    for (map<int, int>::iterator it = hz.begin(); it != hz.end(); ++it) printf(" %d x%d", it->first, it->second);
    printf("   [stop:");
    for (map<string, int>::iterator it = stp.begin(); it != stp.end(); ++it) printf(" %s:%d", it->first.c_str(), it->second);
    printf("]\n");
    if (stp.size() > 1 || !stp.count("max_iter")) printf("UYARI: bazi kosular max_iter ile bitmedi (stall/time ile erken durmus) -> ufuk tahmini yanlis olabilir\n");

    // replay of 'stop after K consecutive non-improving iterations' on the anytime trace
    struct Rep { double cost; int iters; };
    auto replay = [&](const Run &v, int K) -> Rep {
        double prev = -1, cost = INFINITY;
        const int H = v.horizon;
        for (size_t j = 0; j <= v.it.size(); j++) {
            const double nxt = j < v.it.size() ? v.it[j] : H + 1e9;
            if (nxt - prev > K) {
                const int stop_iters = (int)std::min(prev + K + 1, (double)H);
                if (stop_iters >= H) return Rep{v.best.back(), H};
                return Rep{cost, stop_iters};
            }
            prev = v.it[j]; cost = v.best[j];
        }
        return Rep{v.best.back(), H};
    };
    auto cpu_at = [&](const Run &v, int it) -> double {
        if (it >= 1 && (size_t)(it - 1) < v.iter_cpu.size() && !isnan_(v.iter_cpu[it - 1])) return v.iter_cpu[it - 1];
        return v.cpu_total * it / std::max(1, v.horizon);
    };
    vector<string> insts;
    { set<string> s; for (map<pair<string, int>, Run>::iterator it = data.begin(); it != data.end(); ++it) s.insert(it->first.first); insts.assign(s.begin(), s.end()); std::sort(insts.begin(), insts.end(), nat_less); }
    auto of_inst = [&](const string &ins) -> vector<const Run *> { vector<const Run *> v; for (map<pair<string, int>, Run>::iterator it = data.begin(); it != data.end(); ++it) if (it->first.first == ins) v.push_back(&it->second); return v; };

    printf("\n== Son iyilesme iterasyonu (0 tabanli), ornek bazinda; ufuktaki maliyet farki BKS'ye gore ==\n");
    printf("%-14s %3s %6s %6s %6s %6s %7s %7s\n", "ornek", "n", "medyan", "p90", "maks", "ufuk", "gap_uf%", "cpu_s");
    for (size_t q = 0; q < insts.size(); q++) {
        vector<const Run *> ks = of_inst(insts[q]);
        vector<double> L, g, c;
        for (size_t i = 0; i < ks.size(); i++) { L.push_back(ks[i]->it.back()); g.push_back(100 * (ks[i]->best.back() - ks[i]->bks) / ks[i]->bks); c.push_back(ks[i]->cpu_total); }
        printf("%-14s %3zu %6.0f %6.0f %6.0f %6d %7.3f %7.1f\n", insts[q].c_str(), ks.size(), median_of(L), pct_of(L, 90), max_of(L), ks[0]->horizon, mean_of(g), mean_of(c));
    }
    printf("\n== K'ya gore pismanlik ve tasarruf (tum kosular) ==\n");
    printf("regret%% = (durdurulan - ufuk)/ufuk ; 'etkilenen' = ufuktan daha kotu kalan kosu orani ; tasarruf = 1 - (CPU_K / CPU_ufuk)\n");
    printf("%5s %9s %9s %9s %10s %10s %10s\n", "K", "regret_ort", "regret_p95", "regret_max", "etkilenen", "iter_ort", "cpu_tasarruf");
    map<int, double> best;
    for (size_t kk = 0; kk < Ks.size(); kk++) {
        const int K = Ks[kk];
        vector<double> reg, its;
        double c_stop = 0, c_all = 0;
        int aff = 0;
        for (map<pair<string, int>, Run>::iterator it = data.begin(); it != data.end(); ++it) {
            Rep r = replay(it->second, K);
            const double f = it->second.best.back(), x = 100 * (r.cost - f) / f;
            reg.push_back(x); its.push_back(r.iters); aff += x > 1e-9;
            c_stop += cpu_at(it->second, r.iters); c_all += it->second.cpu_total;
        }
        printf("%5d %9.4f %9.4f %9.4f %9.1f%% %10.0f %10.1f%%\n", K, mean_of(reg), pct_of(reg, 95), max_of(reg), 100.0 * aff / reg.size(), mean_of(its), 100 * (1 - c_stop / c_all));
        best[K] = mean_of(reg);
    }
    printf("\n== Ornek bazinda ortalama regret %% (satir=ornek, sutun=K) ==\n%-14s", "ornek");
    for (size_t kk = 0; kk < Ks.size(); kk++) printf("%9d", Ks[kk]);
    printf("\n");
    for (size_t q = 0; q < insts.size(); q++) {
        vector<const Run *> ks = of_inst(insts[q]);
        printf("%-14s", insts[q].c_str());
        for (size_t kk = 0; kk < Ks.size(); kk++) {
            vector<double> v;
            for (size_t i = 0; i < ks.size(); i++) { Rep r = replay(*ks[i], Ks[kk]); v.push_back(100 * (r.cost - ks[i]->best.back()) / ks[i]->best.back()); }
            printf("%9.3f", mean_of(v));
        }
        printf("\n");
    }
    printf("\n== Ornek bazinda ortalama yurutulen iterasyon (satir=ornek, sutun=K) ==\n%-14s", "ornek");
    for (size_t kk = 0; kk < Ks.size(); kk++) printf("%9d", Ks[kk]);
    printf("\n");
    for (size_t q = 0; q < insts.size(); q++) {
        vector<const Run *> ks = of_inst(insts[q]);
        printf("%-14s", insts[q].c_str());
        for (size_t kk = 0; kk < Ks.size(); kk++) {
            vector<double> v;
            for (size_t i = 0; i < ks.size(); i++) v.push_back(replay(*ks[i], Ks[kk]).iters);
            printf("%9.0f", mean_of(v));
        }
        printf("\n");
    }
    int pick = -1;
    for (size_t kk = 0; kk < Ks.size(); kk++) if (best[Ks[kk]] <= target && (pick < 0 || Ks[kk] < pick)) pick = Ks[kk];
    if (pick >= 0) printf("\nHedef: tum kosularda ortalama regret <= %.3f%%  ->  en kucuk uygun K = %d\n", target, pick);
    else printf("\nHedef: tum kosularda ortalama regret <= %.3f%%  ->  en kucuk uygun K = yok (daha buyuk K deneyin)\n", target);
    printf("Not: ufuk (%d iterasyon) sonlu; ufuktan sonraki iyilesmeler bilinmez, regret alt sinirdir.\n", hz.empty() ? 0 : hz.rbegin()->first);
    return 0;
}

#endif
