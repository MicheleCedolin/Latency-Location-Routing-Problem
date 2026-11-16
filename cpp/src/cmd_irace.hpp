// llrp_tools -- irace support: parameter space (single source of truth), file generation, config -> llrp_fast flags, random sampling (dry run)
#ifndef LLRP_TOOLS_IRACE_HPP
#define LLRP_TOOLS_IRACE_HPP
#include "cmd_core.hpp"

namespace ir {

struct IParam {
    string name, sw, type;          // type: c (categorical), i (integer), r (real)
    string vals;                    // categorical values, comma separated
    double lo, hi;                  // numeric range
    int digits;                     // decimals written for real parameters
    bool lg;                        // log scale
    string cond, cond_vals;         // active only if parameter `cond` is in `cond_vals` (comma separated)
    string dflt;                    // value of the default configuration (full pool, SO)
};

static const char *OPNAMES[14] = {"relocate", "oropt2", "oropt3", "swap11", "swap21", "swap22", "swap31", "swap32", "2opt", "2optstar", "swapstar", "dexch", "rdepot", "ds"};

static IParam pc(const string &n, const string &sw, const string &vals, const string &d, const string &cond = "", const string &cv = "") {
    IParam p; p.name = n; p.sw = sw; p.type = "c"; p.vals = vals; p.lo = p.hi = 0; p.digits = 0; p.lg = false; p.cond = cond; p.cond_vals = cv; p.dflt = d; return p;
}
static IParam pi(const string &n, const string &sw, int lo, int hi, const string &d, const string &cond = "", const string &cv = "") {
    IParam p; p.name = n; p.sw = sw; p.type = "i"; p.lo = lo; p.hi = hi; p.digits = 0; p.lg = false; p.cond = cond; p.cond_vals = cv; p.dflt = d; return p;
}
static IParam pr(const string &n, const string &sw, double lo, double hi, bool lg, const string &d, const string &cond = "", const string &cv = "") {
    IParam p; p.name = n; p.sw = sw; p.type = "r"; p.lo = lo; p.hi = hi; p.digits = 2; p.lg = lg; p.cond = cond; p.cond_vals = cv; p.dflt = d; return p;
}

// The tunable space.  Operators = 14 binary parameters (pool membership); the rest are the GRASP / SO / ILS constants that llrp_fast exposes as flags.
static vector<IParam> space() {
    vector<IParam> v;
    for (int i = 0; i < 14; i++) v.push_back(pc(string("op_") + OPNAMES[i], string("--op-") + OPNAMES[i] + " ", "0,1", "1"));
    v.push_back(pc("so", "--so-on ", "0,1", "1"));
    v.push_back(pi("rcl", "--rcl ", 2, 12, "5"));
    v.push_back(pi("it_div", "--it-div ", 2, 12, "5"));
    v.push_back(pi("it_int", "--it-int ", 1, 8, "3"));
    v.push_back(pc("sel", "--select ", "best,first", "best"));
    v.push_back(pc("ord", "--order ", "random,fixed", "random"));
    v.push_back(pc("ils_on", "--ils-on ", "0,1", "0"));
    v.push_back(pi("ils_k", "--ils ", 5, 60, "NA", "ils_on", "1"));
    v.push_back(pi("so_win_up", "--so-win-up ", 2, 10, "4", "so", "1"));
    v.push_back(pi("so_win_down", "--so-win-down ", 2, 10, "4", "so", "1"));
    v.push_back(pr("so_f1", "--so-f1 ", 1.10, 2.00, false, "1.50", "so", "1"));
    v.push_back(pr("so_f2", "--so-f2 ", 2.00, 4.00, false, "2.50", "so", "1"));
    v.push_back(pr("beta0", "--beta0-scale ", 0.10, 10.00, true, "1.00", "so", "1"));
    return v;
}

static string domain_str(const IParam &p) {
    if (p.type == "c") { vector<string> v = split(p.vals, ','); return "(" + join(v, ", ") + ")"; }
    if (p.type == "i") return fmt("(%d, %d)", (int)p.lo, (int)p.hi);
    return fmt("(%.*f, %.*f)", p.digits, p.lo, p.digits, p.hi);
}
static string cond_str(const IParam &p) {
    if (p.cond.empty()) return "";
    return " | " + p.cond + " %in% c(" + p.cond_vals + ")";
}

// value of a configuration: map name -> string ("NA" when inactive)
typedef map<string, string> Cfg;

static bool active(const IParam &p, const Cfg &c) {
    if (p.cond.empty()) return true;
    Cfg::const_iterator it = c.find(p.cond);
    if (it == c.end()) return false;
    vector<string> v = split(p.cond_vals, ',');
    return std::find(v.begin(), v.end(), it->second) != v.end();
}

static Cfg default_cfg(const vector<IParam> &S) {
    Cfg c;
    for (size_t i = 0; i < S.size(); i++) c[S[i].name] = S[i].dflt;
    if (c["ils_on"] != "1") c["ils_k"] = "NA";
    return c;
}
static void deactivate(const vector<IParam> &S, Cfg &c) {
    for (size_t i = 0; i < S.size(); i++) if (!active(S[i], c)) c[S[i].name] = "NA";
}

// configuration -> llrp_fast flags
static string to_flags(const Cfg &c0, const vector<IParam> &S) {
    Cfg c = c0;
    deactivate(S, c);
    vector<string> ops;
    for (int i = 0; i < 14; i++) {
        Cfg::const_iterator it = c.find(string("op_") + OPNAMES[i]);
        if (it != c.end() && it->second == "1") ops.push_back(OPNAMES[i]);
    }
    if (ops.empty()) die("configuration has an empty operator pool");
    string f = "--ops " + join(ops, ",");
    if (c["so"] == "1") f += " --so";
    const char *plain[][2] = {{"rcl", "--rcl"}, {"it_div", "--it-div"}, {"it_int", "--it-int"}, {"sel", "--select"}, {"ord", "--order"},
                              {"so_win_up", "--so-win-up"}, {"so_win_down", "--so-win-down"}, {"so_f1", "--so-f1"}, {"so_f2", "--so-f2"}, {"beta0", "--beta0-scale"}};
    for (size_t i = 0; i < sizeof(plain) / sizeof(plain[0]); i++) {
        Cfg::const_iterator it = c.find(plain[i][0]);
        if (it != c.end() && it->second != "NA" && !it->second.empty()) f += string(" ") + plain[i][1] + " " + it->second;
    }
    if (c["ils_on"] == "1" && c.count("ils_k") && c["ils_k"] != "NA") f += " --ils " + c["ils_k"];
    return f;
}

static string row_line(const vector<IParam> &S, const Cfg &c) {
    string o;
    for (size_t i = 0; i < S.size(); i++) { Cfg::const_iterator it = c.find(S[i].name); o += (i ? " " : "") + (it == c.end() ? string("NA") : it->second); }
    return o;
}

}  // namespace ir

// ---------------------------------------------------------------------------------------------------------------- irace-gen
static const char *TARGET_RUNNER_SH =
"#!/bin/bash\n"
"# irace target-runner for llrp_fast (generated by `llrp_tools irace-gen`).\n"
"#   irace calls:  target-runner <config-id> <instance-id> <seed> <instance-file> <--switch value> ...\n"
"#   prints ONE number: cost = 100*(latency - BKS)/BKS  [% gap to the reference BKS, lower = better];\n"
"#   infeasible result / empty operator pool -> PENALTY.\n"
"# Budget of every run (override with environment variables):\n"
"#   IRACE_MODE=time : CPU-time limit  = max(TMIN, TC * n / 100) seconds  (equal-CPU comparison; a cheap pool can run more iterations)\n"
"#   IRACE_MODE=iter : fixed number of GRASP iterations ITERS             (equal-iteration comparison; favours the largest pool)\n"
"HERE=$(cd \"$(dirname \"$0\")\" && pwd)\n"
"ROOT=$(cd \"$HERE/..\" && pwd)\n"
"BIN=${BIN:-$ROOT/bin/llrp_fast}\n"
"MODE=${IRACE_MODE:-@MODE@}; TC=${TC:-@TC@}; TMIN=${TMIN:-@TMIN@}; ITERS=${ITERS:-@ITERS@}; PENALTY=${PENALTY:-1000}\n"
"CID=$1; IID=$2; SEED=$3; INST=$4; shift 4\n"
"ops=(); extra=(); so=0; ils_on=0; ils_k=20\n"
"while [ $# -ge 2 ]; do\n"
"  case \"$1\" in\n"
"    --op-*)   [ \"$2\" = \"1\" ] && ops+=(\"${1#--op-}\");;\n"
"    --so-on)  so=$2;;\n"
"    --ils-on) ils_on=$2;;\n"
"    --ils)    ils_k=$2;;\n"
"    *)        extra+=(\"$1\" \"$2\");;\n"
"  esac\n"
"  shift 2\n"
"done\n"
"[ \"$ils_on\" = 1 ] && extra+=(--ils \"$ils_k\")\n"
"if [ ${#ops[@]} -eq 0 ]; then echo \"$PENALTY\"; exit 0; fi\n"
"OPS=$(IFS=,; echo \"${ops[*]}\")\n"
"FLAGS=(--ops \"$OPS\")\n"
"[ \"$so\" = 1 ] && FLAGS+=(--so)\n"
"read -r n bks < <(awk '$1==\"n\"{n=$2} $1==\"bks\"{b=$2} /^depots/{print n, b; exit}' \"$INST\")\n"
"[ -n \"$n\" ] && [ -n \"$bks\" ] || { echo \"target-runner: cannot read n/bks from $INST\" >&2; exit 1; }\n"
"if [ \"$MODE\" = iter ]; then BUD=(--max-iter \"$ITERS\")\n"
"else TL=$(awk -v tc=\"$TC\" -v n=\"$n\" -v tm=\"$TMIN\" 'BEGIN{t=tc*n/100; if(t<tm)t=tm; printf \"%.3f\", t}'); BUD=(--time \"$TL\" --max-iter 100000); fi\n"
"out=$(\"$BIN\" --instance \"$INST\" --seed \"$SEED\" \"${FLAGS[@]}\" \"${extra[@]}\" \"${BUD[@]}\" --quiet 2>/dev/null) || { echo \"target-runner: llrp_fast failed (config $CID, $INST)\" >&2; exit 1; }\n"
"cost=$(echo \"$out\" | awk -v b=\"$bks\" -v pen=\"$PENALTY\" '$1==\"final_cost\"{c=$2} $1==\"feasible\"{f=$2} END{ if (f==1 && b>0) printf \"%.6f\", 100*(c-b)/b; else printf \"%s\", pen }')\n"
"if [ -n \"${TRLOG:-}\" ]; then echo \"$CID $IID $SEED $INST $cost $(echo \"$out\" | awk '$1==\"cpu_s\"{c=$2} $1==\"iterations\"{i=$2} END{print c, i}')\" >> \"$TRLOG\"; fi\n"
"echo \"$cost\"\n";

static string replace_all(string s, const string &a, const string &b) {
    size_t p = 0;
    while ((p = s.find(a, p)) != string::npos) { s.replace(p, a.size(), b); p += b.size(); }
    return s;
}

static int cmd_irace_gen(int argc, char **argv) {
    using namespace ir;
    Args A(argc, argv, 2);
    if (!A.has("--train")) die("usage: llrp_tools irace-gen --train selection/train.txt [--out irace] [--budget 3000] [--parallel 30] [--mode time|iter] [--tc 30] [--tmin 5] [--iters 150] [--seed 1] [--first-test 5] [--inst-root inst] [--timing data/timing_probe_20it.tsv]\n"
                               "  train.txt: lines 'family/name' (from `llrp_tools select`); instances are looked up in ../inst/<family>/<name>.inst relative to the irace directory");
    const string od = A.get("--out", "irace");
    mkdir_p(od);
    const string mode = A.get("--mode", "time");
    if (mode != "time" && mode != "iter") die("--mode time|iter");
    const vector<IParam> S = space();
    // parameters.txt
    string P = "# irace parameter file for llrp_fast (generated by `llrp_tools irace-gen`; edit ranges here)\n"
               "# name         switch (label, concatenated with the value)   type  domain            [| condition]\n";
    for (size_t i = 0; i < S.size(); i++) {
        const IParam &p = S[i];
        string t = p.type;
        if (p.lg) t += ",log";
        P += fmt("%-13s \"%s\"%*s %-6s %-18s%s\n", p.name.c_str(), p.sw.c_str(), (int)(26 - p.sw.size()), "", t.c_str(), domain_str(p).c_str(), cond_str(p).c_str());
    }
    write_all(od + "/parameters.txt", P);
    // instances
    std::ifstream tf(A.get("--train").c_str());
    if (!tf) die("cannot read " + A.get("--train"));
    string line, L;
    int nt = 0;
    vector<string> train_names;
    while (std::getline(tf, line)) { line = trim(line); if (line.empty() || line[0] == '#') continue; L += line + ".inst\n"; nt++; train_names.push_back(line); }
    write_all(od + "/instances_train.txt", L);
    // configurations.txt (initial configurations: full pool + SO, Zou pool + ds + SO, full pool classic)
    {
        vector<string> names;
        for (size_t i = 0; i < S.size(); i++) names.push_back(S[i].name);
        string C = join(names, " ") + "\n";
        Cfg full3 = default_cfg(S);
        C += row_line(S, full3) + "\n";
        Cfg zou = default_cfg(S);
        const char *zops[] = {"relocate", "swap11", "2opt", "oropt2", "swap21", "swap22", "swapstar", "dexch", "ds"};      // Zou pool (8) + depot swap
        for (int i = 0; i < 14; i++) zou[string("op_") + OPNAMES[i]] = "0";
        for (size_t i = 0; i < sizeof(zops) / sizeof(zops[0]); i++) zou[string("op_") + zops[i]] = "1";
        C += row_line(S, zou) + "\n";
        Cfg cl = default_cfg(S);
        cl["so"] = "0"; cl["op_ds"] = "0"; deactivate(S, cl);
        C += row_line(S, cl) + "\n";
        write_all(od + "/configurations.txt", C);
    }
    // scenario.txt
    const string tc = A.get("--tc", "30"), tmin = A.get("--tmin", "5"), iters = A.get("--iters", "150");
    string Sc = "## irace scenario for llrp_fast (generated by `llrp_tools irace-gen`).  Run from this directory:  ../run_irace.sh\n"
                "targetRunner = \"./target-runner\"\n"
                "parameterFile = \"./parameters.txt\"\n"
                "trainInstancesDir = \"../inst\"\n"
                "trainInstancesFile = \"./instances_train.txt\"\n"
                "configurationsFile = \"./configurations.txt\"\n"
                "maxExperiments = " + A.get("--budget", "3000") + "\n"
                "parallel = " + A.get("--parallel", "30") + "\n"
                "firstTest = " + A.get("--first-test", "5") + "\n"
                "seed = " + A.get("--seed", "1") + "\n"
                "logFile = \"./irace.Rdata\"\n"
                "## test instances are NOT given to irace: the tuned configuration is applied to all instances with ../run_config.sh (FAMILY=all|test)\n";
    write_all(od + "/scenario.txt", Sc);
    // target-runner
    string T = TARGET_RUNNER_SH;
    T = replace_all(T, "@MODE@", mode); T = replace_all(T, "@TC@", tc); T = replace_all(T, "@TMIN@", tmin); T = replace_all(T, "@ITERS@", iters);
    write_all(od + "/target-runner", T);
    chmod((od + "/target-runner").c_str(), 0755);
    printf("irace files written: %s/{parameters.txt, scenario.txt, instances_train.txt, configurations.txt, target-runner}\n", od.c_str());
    printf("  training instances: %d | parameters: %zu (14 binary operator switches + %zu GRASP/SO/ILS constants) | budget: %s experiments | mode: %s", nt, S.size(), S.size() - 14, A.get("--budget", "3000").c_str(), mode.c_str());
    if (mode == "time") printf(" (CPU siniri = max(%s, %s*n/100) s)\n", tmin.c_str(), tc.c_str()); else printf(" (%s iterasyon)\n", iters.c_str());
    // ---- expected cost of the irace run (every experiment = one (configuration, instance) run) ----
    {
        const string root = A.get("--inst-root", "inst");
        const double budget = A.num("--budget", 3000), par = std::max(1.0, A.num("--parallel", 30));
        map<string, double> t20;                                              // CPU seconds of 20 GRASP iterations, full pool + SO (upper bound for tuned pools)
        if (mode == "iter") {
            std::ifstream tt(A.get("--timing", "data/timing_probe_20it.tsv").c_str());
            string l2;
            while (tt && std::getline(tt, l2)) { vector<string> f = split(l2, '\t'); if (f.size() >= 3) t20[f[1]] = atof(f[2].c_str()); }
        }
        double sum = 0, mn = INFINITY, mx = 0;
        int ok = 0;
        for (size_t i = 0; i < train_names.size(); i++) {
            std::ifstream chk((root + "/" + train_names[i] + ".inst").c_str());
            if (!chk) continue;
            chk.close();
            const Instance I = read_instance(root + "/" + train_names[i] + ".inst");
            double t;
            if (mode == "time") t = std::max(atof(tmin.c_str()), atof(tc.c_str()) * I.n / 100.0);
            else {
                const string base = train_names[i].substr(train_names[i].find('/') + 1);
                if (!t20.count(base)) continue;
                t = t20[base] / 20.0 * atof(iters.c_str());
            }
            sum += t; mn = std::min(mn, t); mx = std::max(mx, t); ok++;
        }
        if (ok == 0) printf("  time estimate: not possible (--inst-root %s%s not found)\n", root.c_str(), mode == "iter" ? " / --timing" : "");
        else {
            const double mean = sum / ok, cpu_h = budget * mean / 3600.0;
            printf("  time estimate: mean %.1f s per experiment (min %.1f, max %.1f; %d training instances) -> total %.1f CPU-hours\n", mean, mn, mx, ok, cpu_h);
            printf("    -> with %d parallel processes ~%.0f min wall time (~%.0f min assuming 85%% efficiency); the final test (firstTest) and irace overhead are not included\n", (int)par, cpu_h * 60.0 / par, cpu_h * 60.0 / (par * 0.85));
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------------------------------------------- irace-flags
static vector<string> tokens_of(const string &s) {
    vector<string> t;
    std::istringstream is(s);
    string x;
    while (is >> x) t.push_back(x);
    return t;
}
static int cmd_irace_flags(int argc, char **argv) {
    using namespace ir;
    Args A(argc, argv, 2);
    const vector<IParam> S = space();
    Cfg c;
    map<string, string> by_sw;
    for (size_t i = 0; i < S.size(); i++) { string sw = S[i].sw; while (!sw.empty() && sw[sw.size() - 1] == ' ') sw.erase(sw.size() - 1); by_sw[sw] = S[i].name; }
    const int row = (int)A.inum("--row", 1);
    auto from_tokens = [&](const vector<string> &t, size_t start) {
        for (size_t i = start; i + 1 < t.size(); i += 2) {
            map<string, string>::iterator it = by_sw.find(t[i]);
            if (it == by_sw.end()) die("unknown irace switch '" + t[i] + "' (parameters.txt and llrp_tools must be from the same kit)");
            c[it->second] = t[i + 1];
        }
    };
    if (A.has("--args")) from_tokens(tokens_of(A.get("--args")), 0);
    else if (A.has("--from-log")) {
        // irace prints "# Best configurations as commandline (first number is the configuration ID; ...)" followed by "<id> --switch value ..." lines
        std::ifstream f(A.get("--from-log").c_str());
        if (!f) die("cannot read " + A.get("--from-log"));
        string line;
        vector<vector<string> > block, last;
        bool in = false;
        while (std::getline(f, line)) {
            string low = line;
            for (size_t i = 0; i < low.size(); i++) low[i] = (char)tolower((unsigned char)low[i]);
            if (low.find("as commandline") != string::npos) { in = true; block.clear(); continue; }
            if (in) {
                if (trim(line).empty() || line[0] == '#') { if (!block.empty()) last = block; in = false; continue; }
                block.push_back(tokens_of(line));
            }
        }
        if (in && !block.empty()) last = block;
        if (last.empty()) die("no 'Best configurations as commandline' block found in the irace output (use --table or --args)");
        if (row < 1 || row > (int)last.size()) die("--row out of range (block has " + std::to_string(last.size()) + " configurations)");
        fprintf(stderr, "irace-flags: configuration id %s (row %d / %zu)\n", last[row - 1][0].c_str(), row, last.size());
        from_tokens(last[row - 1], 1);
    } else if (A.has("--table")) {
        // a table with a header of parameter names; rows may start with an extra ID column (irace's own printout); NA for inactive parameters
        std::ifstream f(A.get("--table").c_str());
        if (!f) die("cannot read " + A.get("--table"));
        string line;
        std::getline(f, line);
        vector<string> h = tokens_of(line);
        int k = 0;
        while (std::getline(f, line)) {
            vector<string> t = tokens_of(line);
            if (t.empty()) continue;
            if (++k != row) continue;
            size_t off = t.size() > h.size() ? t.size() - h.size() : 0;
            for (size_t i = 0; i < h.size() && i + off < t.size(); i++) if (!h[i].empty() && h[i][0] != '.') c[h[i]] = t[i + off];
        }
        if (c.empty()) die("table row not found");
    } else die("usage: llrp_tools irace-flags (--from-log irace_stdout.txt | --table FILE | --args \"--op-relocate 1 --so-on 1 ...\") [--row 1] [--out flags.txt]");
    const string flags = to_flags(c, S);
    if (A.has("--out")) write_all(A.get("--out"), flags + "\n");
    printf("%s\n", flags.c_str());
    return 0;
}

// ---------------------------------------------------------------------------------------------------------------- irace-sample
static int cmd_irace_sample(int argc, char **argv) {
    using namespace ir;
    Args A(argc, argv, 2);
    const int N = A.pos.empty() ? 5 : atoi(A.pos[0].c_str());
    SplitMix rng((unsigned long long)A.inum("--seed", 1));
    const vector<IParam> S = space();
    auto u01 = [&]() -> double { return (rng.next() >> 11) * (1.0 / 9007199254740992.0); };
    for (int n = 0; n < N; n++) {
        Cfg c;
        for (size_t i = 0; i < S.size(); i++) {
            const IParam &p = S[i];
            if (!active(p, c)) { c[p.name] = "NA"; continue; }
            if (p.type == "c") { vector<string> v = split(p.vals, ','); c[p.name] = v[rng.next() % v.size()]; }
            else if (p.type == "i") c[p.name] = std::to_string((long long)p.lo + (long long)(rng.next() % (unsigned long long)(p.hi - p.lo + 1)));
            else {
                double x = p.lg ? std::exp(std::log(p.lo) + u01() * (std::log(p.hi) - std::log(p.lo))) : p.lo + u01() * (p.hi - p.lo);
                c[p.name] = fmt("%.*f", p.digits, x);
            }
        }
        // irace-style argument list (only active parameters, in file order)
        string s;
        for (size_t i = 0; i < S.size(); i++) if (c[S[i].name] != "NA") s += (s.empty() ? "" : " ") + S[i].sw.substr(0, S[i].sw.size() - 1) + " " + c[S[i].name];
        printf("%s\n", s.c_str());
    }
    return 0;
}

#endif
