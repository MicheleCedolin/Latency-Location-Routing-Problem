// llrp_tools -- operator ablation analysis (leave-one-out, add-one-in, counters, cost-benefit, equal-iteration / equal-CPU quality)
#ifndef LLRP_TOOLS_ABLATION_HPP
#define LLRP_TOOLS_ABLATION_HPP
#include "cmd_core.hpp"

namespace abl {

typedef pair<string, int> Key;
struct TP { int iter; double cpu, best; };
struct OpsAgg { double v[8]; OpsAgg() { for (int i = 0; i < 8; i++) v[i] = 0; } };   // Calls, Evaluations, Applied, GainLat, GainObj, Cpu, BestApplied, BestGain

struct Cfg {
    string tag, kind, op, opslist;
    int n_runs = 0;
    map<Key, double> feas, cpu, iters;
    map<string, double> bks;
    vector<vector<string> > ops;
    map<Key, vector<TP> > trace;
    vector<string> insts;
};

static void load_cfg(Cfg &c, const vector<string> &bases) {
    set<string> ins;
    for (size_t b = 0; b < bases.size(); b++) {
        const string dir = bases[b] + "/" + c.tag;
        Tbl T = load_tbl(dir, "run");
        if (T.rows.empty()) continue;
        const int cI = T.col("Instance"), cS = T.col("Seed"), cF = T.col("Feasible"), cL = T.col("Total Latency"), cB = T.col("Reference BKS"), cC = T.col("CPU Time"), cIt = T.col("Iterations");
        for (size_t i = 0; i < T.rows.size(); i++) {
            const vector<string> &r = T.rows[i];
            const Key k(r[cI], atoi(r[cS].c_str()));
            c.n_runs++;
            c.cpu[k] = to_num(r[cC]); c.iters[k] = to_num(r[cIt]); c.bks[r[cI]] = to_num(r[cB]);
            ins.insert(r[cI]);
            if (to_bool(r[cF])) { const double bk = to_num(r[cB]); c.feas[k] = 100.0 * (to_num(r[cL]) - bk) / bk; }
        }
        Tbl O = load_tbl(dir, "ops");
        const int oI = O.col("Instance"), oS = O.col("Seed"), oO = O.col("Operator");
        for (size_t i = 0; i < O.rows.size(); i++) {
            vector<string> r;
            r.push_back(O.rows[i][oI]); r.push_back(O.rows[i][oS]); r.push_back(O.rows[i][oO]);
            for (int q = 0; q < 8; q++) r.push_back(O.rows[i][O.col(OPCOLS[q])]);
            c.ops.push_back(r);
        }
        Tbl X = load_tbl(dir, "trace");
        if (!X.rows.empty()) {
            const int tI = X.col("Instance"), tS = X.col("Seed"), tIt = X.col("Iteration"), tC = X.col("CPU Seconds"), tB = X.col("Best Latency");
            for (size_t i = 0; i < X.rows.size(); i++) {
                TP p; p.iter = atoi(X.rows[i][tIt].c_str()); p.cpu = to_num(X.rows[i][tC]); p.best = to_num(X.rows[i][tB]);
                c.trace[Key(X.rows[i][tI], atoi(X.rows[i][tS].c_str()))].push_back(p);
            }
        }
    }
    for (map<Key, vector<TP> >::iterator it = c.trace.begin(); it != c.trace.end(); ++it)
        std::sort(it->second.begin(), it->second.end(), [](const TP &a, const TP &b) { return a.iter < b.iter; });
    c.insts.assign(ins.begin(), ins.end());
    std::sort(c.insts.begin(), c.insts.end(), nat_less);
}

static vector<double> inst_means_vals(const Cfg &c, const vector<string> &insts) {
    vector<double> out;
    for (size_t q = 0; q < insts.size(); q++) {
        vector<double> g;
        for (map<Key, double>::const_iterator it = c.feas.begin(); it != c.feas.end(); ++it) if (it->first.first == insts[q]) g.push_back(it->second);
        if (!g.empty()) out.push_back(mean_of(g));
    }
    return out;
}
static double overall(const Cfg &c, const vector<string> &insts) { return mean_of(inst_means_vals(c, insts)); }
static double cpu_mean(const Cfg &c) { vector<double> v; for (map<Key, double>::const_iterator it = c.cpu.begin(); it != c.cpu.end(); ++it) v.push_back(it->second); return mean_of(v); }
static double iters_mean(const Cfg &c) { vector<double> v; for (map<Key, double>::const_iterator it = c.iters.begin(); it != c.iters.end(); ++it) v.push_back(it->second); return mean_of(v); }

static double best_at_iter(const vector<TP> &tr, int it) {
    double v = INFINITY;
    for (size_t i = 0; i < tr.size(); i++) { if (tr[i].iter <= it) v = tr[i].best; else break; }
    return v;
}
static double best_at_cpu(const vector<TP> &tr, double t) {
    double v = INFINITY;
    for (size_t i = 0; i < tr.size(); i++) { if (tr[i].cpu <= t) v = tr[i].best; else break; }
    return v;
}

struct Row { string op; double md, lo, hi; int win, tie, los; double p, padj, dcpu; };

static void paired(const Cfg &a, const Cfg &b, const set<string> &insts, vector<double> &d, map<string, vector<double> > &per) {
    for (map<Key, double>::const_iterator it = a.feas.begin(); it != a.feas.end(); ++it) {
        map<Key, double>::const_iterator jt = b.feas.find(it->first);
        if (jt == b.feas.end() || !insts.count(it->first.first)) continue;
        const double x = it->second - jt->second;
        d.push_back(x); per[it->first.first].push_back(x);
    }
}

}  // namespace abl

static int cmd_ablation(int argc, char **argv) {
    using namespace abl;
    Args A(argc, argv, 2);
    if (A.pos.empty()) die("usage: llrp_tools ablation DIR [DIR2 ...] [--ref FULL] [--base BASE] [--train a,b,c|FILE] [--out DIR]\n"
                           "  DIR = run_ablation.sh output of one family (plan.tsv + <TAG>/run.csv ...); several DIRs are pooled (instances are disjoint)");
    const vector<string> bases = A.pos;
    const string ref = A.get("--ref", "FULL"), basetag = A.get("--base", "BASE");
    const string outdir = A.get("--out", bases[0]);
    // plan
    struct Plan { string tag, kind, op, ops; };
    vector<Plan> plan;
    const string pf = bases[0] + "/plan.tsv";
    if (file_exists(pf)) {
        std::ifstream f(pf.c_str());
        string line;
        while (std::getline(f, line)) {
            vector<string> p = split(line, '\t');
            if (p.size() >= 4 && p[0] != "tag") { Plan x; x.tag = p[0]; x.kind = p[1]; x.op = p[2]; x.ops = p[3]; plan.push_back(x); }
        }
    } else {
        vector<string> ds = list_dir(bases[0]);
        std::sort(ds.begin(), ds.end(), nat_less);
        for (size_t i = 0; i < ds.size(); i++) if (dir_exists(bases[0] + "/" + ds[i])) {
            Plan x; x.tag = ds[i];
            x.kind = ds[i] == ref ? "full" : ds[i] == basetag ? "base" : starts_with(ds[i], "LOO_") ? "loo" : starts_with(ds[i], "ADD_") ? "add" : "other";
            size_t u = ds[i].find('_');
            x.op = u == string::npos ? ds[i] : ds[i].substr(u + 1);
            plan.push_back(x);
        }
    }
    vector<Cfg> cfgs;
    for (size_t i = 0; i < plan.size(); i++) {
        Cfg c; c.tag = plan[i].tag;
        load_cfg(c, bases);
        if (c.n_runs) { c.kind = plan[i].kind; c.op = plan[i].op; c.opslist = plan[i].ops; cfgs.push_back(c); }
    }
    int fi = -1, bi = -1;
    for (size_t i = 0; i < cfgs.size(); i++) { if (cfgs[i].tag == ref) fi = (int)i; if (cfgs[i].tag == basetag) bi = (int)i; }
    if (fi < 0) die("reference configuration (" + ref + ") not found / empty in " + bases[0]);
    const Cfg &F = cfgs[fi];
    const vector<string> insts = F.insts;
    const set<string> iset(insts.begin(), insts.end());
    {
        vector<double> per;
        for (size_t q = 0; q < insts.size(); q++) { int c = 0; for (map<Key, double>::const_iterator it = F.cpu.begin(); it != F.cpu.end(); ++it) c += it->first.first == insts[q]; per.push_back(c); }
        printf("reference: %s | instances: %zu | seeds/instance: ~%.0f | configurations: %zu | directories: %zu\n", ref.c_str(), insts.size(), mean_of(per), cfgs.size(), bases.size());
    }
    printf("\n== 1) CONFIGURATION SUMMARY ==\n%-16s %5s %5s %9s %9s %9s %7s\n", "tag", "runs", "feas", "gap_mean%", "gap_med%", "cpu_mean_s", "iter");
    struct Summ { string tag; int runs, feas; double gmean, gmed, cpu, iter; };
    vector<Summ> summ;
    for (size_t i = 0; i < cfgs.size(); i++) {
        const Cfg &c = cfgs[i];
        vector<double> g;
        for (map<Key, double>::const_iterator it = c.feas.begin(); it != c.feas.end(); ++it) g.push_back(it->second);
        Summ s = {c.tag, c.n_runs, (int)g.size(), overall(c, insts), median_of(g), cpu_mean(c), iters_mean(c)};
        summ.push_back(s);
        printf("%-16s %5d %5d %9.4f %9.4f %9.2f %7.0f\n", s.tag.c_str(), s.runs, s.feas, s.gmean, s.gmed, s.cpu, s.iter);
    }

    // generic table: rows for all configurations of `kind`;  delta = gap(a) - gap(b) where (a,b) = (a_of(c), b_of(c))
    auto table = [&](const string &kind, const string &title, const string &note, bool ref_is_a, const Cfg *fixed, const set<string> &ins, bool quiet) -> vector<Row> {
        if (!quiet) printf("\n== %s ==\n%s\n%-9s %9s %8s %8s %6s %6s %6s %11s %9s %7s\n", title.c_str(), note.c_str(), "operator", "Delta_gap%", "CI95_lo", "CI95_hi", "win", "tie", "loss", "p(Wilcoxon)", "p(Holm)", "dCPU%");
        vector<Row> rows;
        for (size_t i = 0; i < cfgs.size(); i++) {
            const Cfg &c = cfgs[i];
            if (c.kind != kind) continue;
            const Cfg &a = ref_is_a ? c : *fixed, &b = ref_is_a ? *fixed : c;
            vector<double> d;
            map<string, vector<double> > per;
            paired(a, b, ins, d, per);
            if (d.empty()) continue;
            Row r;
            r.op = c.op;
            r.p = wilcoxon_p(d);
            r.md = mean_of(d);
            const double se = d.size() > 1 ? sd_of(d) / std::sqrt((double)d.size()) : NaN;
            r.lo = r.md - 1.96 * se; r.hi = r.md + 1.96 * se;
            r.win = r.los = 0;
            int ninst = 0;
            for (map<string, vector<double> >::iterator it = per.begin(); it != per.end(); ++it) {
                const double m = mean_of(it->second);
                ninst++;
                if (m > 1e-9) r.win++; else if (m < -1e-9) r.los++;
            }
            r.tie = ninst - r.win - r.los;
            r.dcpu = 100.0 * (cpu_mean(c) / cpu_mean(*fixed) - 1.0);
            r.padj = 0;
            rows.push_back(r);
        }
        if (rows.empty()) { if (!quiet) printf("(no data)\n"); return rows; }
        vector<double> ps;
        for (size_t i = 0; i < rows.size(); i++) ps.push_back(rows[i].p);
        vector<double> adj = holm_adjust(ps);
        for (size_t i = 0; i < rows.size(); i++) rows[i].padj = adj[i];
        std::stable_sort(rows.begin(), rows.end(), [](const Row &x, const Row &y) { return x.md > y.md; });
        if (!quiet)
            for (size_t i = 0; i < rows.size(); i++) {
                const Row &r = rows[i];
                printf("%-9s %+9.4f %+8.4f %+8.4f %6d %6d %6d %11.4g %9.4g %+7.1f %s\n", r.op.c_str(), r.md, nz(r.lo), nz(r.hi), r.win, r.tie, r.los, r.p, r.padj, r.dcpu, r.padj < 0.05 ? "*" : "");
            }
        return rows;
    };

    vector<Row> loo = table("loo", "2) LEAVE-ONE-OUT (remove one operator from FULL)",
                            "Delta = gap(FULL - op) - gap(FULL); >0 : removing the operator makes results worse => the operator is USEFUL.  win/tie/loss = number of instances (in favour of / equal / against the operator).  dCPU = CPU change when removed (relative to FULL)",
                            true, &F, iset, false);
    vector<Row> add;
    if (bi >= 0) {
        const Cfg &B = cfgs[bi];
        // ADD: delta = gap(BASE) - gap(BASE + op)  -> a = BASE (fixed), b = c ; dCPU relative to BASE
        add = table("add", "3) ADD-ONE-IN (add one operator to the base pool)  base=" + (B.opslist.empty() ? basetag : B.opslist),
                    "Delta = gap(BASE) - gap(BASE + op); >0 : operator eklenince iyilesiyor => operator FAYDALI.  dCPU = eklenince CPU degisimi (BASE'e gore)", false, &B, iset, false);
        const double gb = overall(B, insts), gf = overall(F, insts);
        printf("\nBase pool gap=%.4f%%  ->  FULL gap=%.4f%%  (total gain %.4f points; CPU x%.2f)\n", gb, gf, gb - gf, cpu_mean(F) / cpu_mean(B));
    }

    // ---- 4) operator counters in FULL
    printf("\n== 4) OPERATOR COUNTERS IN THE FULL RUNS (sum over all seeds and instances) ==\n");
    map<string, OpsAgg> agg;
    vector<string> aorder;
    for (size_t i = 0; i < F.ops.size(); i++) {
        const string &o = F.ops[i][2];
        if (!agg.count(o)) aorder.push_back(o);
        OpsAgg &a = agg[o];
        for (int q = 0; q < 8; q++) { const double x = to_num(F.ops[i][3 + q]); a.v[q] += isnan_(x) ? 0.0 : x; }
    }
    double tg = 0, tc = 0, tb = 0;
    for (map<string, OpsAgg>::iterator it = agg.begin(); it != agg.end(); ++it) { tg += it->second.v[3]; tc += it->second.v[5]; tb += it->second.v[7]; }
    printf("%-9s %10s %12s %10s %7s %8s %8s %12s %9s\n", "operator", "calls", "evaluations", "applied", "hit%", "gain%", "cpu%", "gain/cpu-s", "bestIt%");
    vector<string> sorted_ops = aorder;
    std::stable_sort(sorted_ops.begin(), sorted_ops.end(), [&](const string &x, const string &y) { return agg[x].v[3] > agg[y].v[3]; });
    struct OpRow { string op; double calls, evals, applied, hit, gshare, cshare, gpc, bshare; };
    vector<OpRow> opsrows;
    for (size_t i = 0; i < sorted_ops.size(); i++) {
        const OpsAgg &a = agg[sorted_ops[i]];
        OpRow r = {sorted_ops[i], a.v[0], a.v[1], a.v[2], a.v[0] ? 100 * a.v[2] / a.v[0] : 0.0, tg ? 100 * a.v[3] / tg : 0.0, tc ? 100 * a.v[5] / tc : 0.0, a.v[5] ? a.v[3] / a.v[5] : 0.0, tb ? 100 * a.v[7] / tb : 0.0};
        opsrows.push_back(r);
        printf("%-9s %10.0f %12.3g %10.0f %7.2f %8.2f %8.2f %12.1f %9.2f\n", r.op.c_str(), r.calls, r.evals, r.applied, r.hit, r.gshare, r.cshare, r.gpc, r.bshare);
    }
    printf("(gain = total latency reduction of the applied moves; with SO the net gain can differ from the LOO delta because of penalty/oscillation; bestIt = the operator's share of the gain in the GRASP iteration that produced the final best solution)\n");

    // ---- 6) cost-benefit
    double tot_cpu = 0;
    for (map<Key, double>::const_iterator it = F.cpu.begin(); it != F.cpu.end(); ++it) tot_cpu += it->second;
    map<string, double> op_cpu;
    double attributed_s = 0;
    for (map<string, OpsAgg>::iterator it = agg.begin(); it != agg.end(); ++it) { op_cpu[it->first] = it->second.v[5]; attributed_s += it->second.v[5]; }
    const double attributed = tot_cpu ? attributed_s / tot_cpu : NaN;
    map<string, const Row *> loo_by, add_by;
    for (size_t i = 0; i < loo.size(); i++) loo_by[loo[i].op] = &loo[i];
    for (size_t i = 0; i < add.size(); i++) add_by[add[i].op] = &add[i];
    printf("\n== 6) OPERATOR COST-BENEFIT SUMMARY (relative to FULL) ==\n");
    printf("CPU%% = CPU spent in the operator's own calls (scan + move application + table preparation) / total run CPU.  Total attributed to operators: %.1f%%;\n", 100 * attributed);
    printf("the remaining %.1f%% = construction (ECWA), perturbation, loop and bookkeeping (not attributed to an operator).\n", 100 * (1 - attributed));
    printf("%-9s %7s %9s %10s %9s %10s %9s  %s\n", "operator", "CPU%", "dCPU%LOO", "dGap_LOO", "p_Holm", "dGap_ADD", "p_Holm", "decision");
    struct CB { string op; double share, dcpu, dl, pl, da, pa; string verdict; };
    vector<CB> cb;
    auto nf = [](double x, const char *f, int w) -> string { return isnan_(x) ? fmt("%*s", w, "-") : fmt(f, x); };
    for (size_t i = 0; i < opsrows.size(); i++) {
        const string &o = opsrows[i].op;
        const Row *l = loo_by.count(o) ? loo_by[o] : 0, *a_ = add_by.count(o) ? add_by[o] : 0;
        const double share = tot_cpu ? 100 * op_cpu[o] / tot_cpu : NaN;
        string v;
        if (!l) v = "(no LOO)";
        else if (l->padj < 0.05 && l->md > 0) v = "NEEDED (removal significantly worsens results)";
        else if (l->padj < 0.05 && l->md < 0) v = "REMOVE (removal significantly improves results)";
        else if (share >= 5.0) v = "CANDIDATE: REMOVE (CPU share >= 5 %, no proven benefit)";
        else v = "OPTIONAL (cheap; benefit not proven)";
        if (a_ && a_->padj < 0.05 && a_->md > 0) v += " | tabana eklenince anlamli fayda";
        CB r = {o, share, l ? l->dcpu : NaN, l ? l->md : NaN, l ? l->padj : NaN, a_ ? a_->md : NaN, a_ ? a_->padj : NaN, v};
        cb.push_back(r);
        printf("%-9s %7.2f %s %s %s %s %s  %s\n", o.c_str(), share, nf(r.dcpu, "%+9.1f", 9).c_str(), nf(r.dl, "%+10.4f", 10).c_str(), nf(r.pl, "%9.3g", 9).c_str(), nf(r.da, "%+10.4f", 10).c_str(), nf(r.pa, "%9.3g", 9).c_str(), v.c_str());
    }
    printf("Decision rule (a modelling choice, adjustable): p(Holm) < 0.05 and Delta > 0 => NEEDED; p(Holm) < 0.05 and Delta < 0 => REMOVE; if not significant: CPU%% >= 5 => CANDIDATE: REMOVE, otherwise OPTIONAL.\n");
    printf("A non-significant result does not mean 'no benefit': power (number of instances/seeds) and substitution between operators (LOO) shape the outcome; read it together with ADD.\n");
    for (size_t i = 0; i < cb.size(); i++)
        if (cb[i].op == "ds") printf("ds (depot swap): CPU%% = %.2f; LOO dGap = %+.4f (p_Holm %.3g); ADD dGap = %+.4f (p_Holm %.3g).\n", cb[i].share, cb[i].dl, cb[i].pl, cb[i].da, cb[i].pa);

    // ---- 6b) train / test split
    if (A.has("--train")) {
        set<string> train;
        const string spec = A.get("--train");
        if (file_exists(spec)) train = load_name_set(spec);
        else { vector<string> p = split(spec, ','); for (size_t i = 0; i < p.size(); i++) if (!p[i].empty()) train.insert(p[i]); }
        set<string> tr, te;
        for (size_t i = 0; i < insts.size(); i++) (train.count(insts[i]) ? tr : te).insert(insts[i]);
        printf("\n== 6b) TRAIN / TEST SPLIT (irace principle: design decisions and final evaluation must not use the same instances) ==\n");
        printf("train (%zu): %s\ntest  (%zu): %s\n", tr.size(), join(vector<string>(tr.begin(), tr.end()), ", ").c_str(), te.size(), join(vector<string>(te.begin(), te.end()), ", ").c_str());
        if (tr.size() < 2 || te.size() < 2) printf("(at least 2 instances per set are required)\n");
        else {
            vector<Row> Ltr = table("loo", "", "", true, &F, tr, true), Lte = table("loo", "", "", true, &F, te, true);
            map<string, const Row *> mte;
            for (size_t i = 0; i < Lte.size(); i++) mte[Lte[i].op] = &Lte[i];
            printf("%-9s %12s %9s %12s %9s %s\n", "operator", "dGap_train", "p_Holm", "dGap_test", "p_Holm", "sign");
            for (size_t i = 0; i < Ltr.size(); i++) {
                if (!mte.count(Ltr[i].op)) continue;
                const Row &t = *mte[Ltr[i].op];
                printf("%-9s %+12.4f %9.3g %+12.4f %9.3g %s\n", Ltr[i].op.c_str(), Ltr[i].md, Ltr[i].padj, t.md, t.padj, Ltr[i].md * t.md > 0 ? "ayni" : "FARKLI");
            }
        }
    }

    // ---- 5a) equal iterations
    int horizon = 0;
    for (map<Key, double>::const_iterator it = F.iters.begin(); it != F.iters.end(); ++it) horizon = std::max(horizon, (int)it->second);
    vector<int> cps;
    { const int cand[] = {25, 50, 100, 200, 300, 500, 1000}; for (int i = 0; i < 7; i++) if (cand[i] < horizon) cps.push_back(cand[i]); cps.push_back(horizon); }
    printf("\n== 5a) EQUAL ITERATIONS: mean gap%% (best-so-far solution, anytime trace) ==   [horizon=%d]\n%-16s", horizon, "tag");
    for (size_t i = 0; i < cps.size(); i++) printf("%9s", fmt("it<=%d", cps[i]).c_str());
    printf("\n");
    for (size_t ci = 0; ci < cfgs.size(); ci++) {
        const Cfg &c = cfgs[ci];
        printf("%-16s", c.tag.c_str());
        for (size_t qi = 0; qi < cps.size(); qi++) {
            vector<double> vals;
            for (size_t q = 0; q < insts.size(); q++) {
                vector<double> g;
                const map<string, double>::const_iterator bk = c.bks.find(insts[q]);
                if (bk == c.bks.end() || !(bk->second > 0)) continue;
                for (map<Key, vector<TP> >::const_iterator it = c.trace.begin(); it != c.trace.end(); ++it) {
                    if (it->first.first != insts[q]) continue;
                    const double b = best_at_iter(it->second, cps[qi] - 1);
                    if (b < INFINITY) g.push_back(100 * (b - bk->second) / bk->second);
                }
                if (!g.empty()) vals.push_back(mean_of(g));
            }
            printf("%9.3f", mean_of(vals));
        }
        printf("\n");
    }
    // ---- 5b) equal CPU
    const double fr[] = {0.1, 0.25, 0.5, 1.0};
    printf("\n== 5b) EQUAL CPU BUDGET: mean gap%% (budget = fraction of FULL's mean CPU time per instance) ==\n%-16s", "tag");
    for (int i = 0; i < 4; i++) printf("%9s", fmt("%g*T_F", fr[i]).c_str());
    printf("\n");
    map<string, double> TF;
    for (size_t q = 0; q < insts.size(); q++) {
        vector<double> v;
        for (map<Key, double>::const_iterator it = F.cpu.begin(); it != F.cpu.end(); ++it) if (it->first.first == insts[q]) v.push_back(it->second);
        TF[insts[q]] = mean_of(v);
    }
    for (size_t ci = 0; ci < cfgs.size(); ci++) {
        const Cfg &c = cfgs[ci];
        printf("%-16s", c.tag.c_str());
        for (int fi2 = 0; fi2 < 4; fi2++) {
            vector<double> vals;
            for (size_t q = 0; q < insts.size(); q++) {
                vector<double> g;
                const map<string, double>::const_iterator bk = c.bks.find(insts[q]);
                if (bk == c.bks.end() || !(bk->second > 0)) continue;
                for (map<Key, vector<TP> >::const_iterator it = c.trace.begin(); it != c.trace.end(); ++it) {
                    if (it->first.first != insts[q]) continue;
                    const double b = best_at_cpu(it->second, fr[fi2] * TF[insts[q]]);
                    if (b < INFINITY) g.push_back(100 * (b - bk->second) / bk->second);
                }
                if (!g.empty()) vals.push_back(mean_of(g));
            }
            if (vals.empty()) printf("%9s", "-"); else printf("%9.3f", mean_of(vals));
        }
        printf("\n");
    }
    printf("(5b: if a configuration has not produced a solution within the budget, that instance is dropped from its mean; with short budgets this can bias the comparison)\n");

    // ---- CSV files
    mkdir_p(outdir);
    {
        FILE *f = fopen((outdir + "/ablation_summary.csv").c_str(), "w");
        if (!f) die("cannot write into " + outdir);
        fprintf(f, "tag,runs,feasible,gap_mean_pct,gap_median_pct,cpu_mean_s,iter_mean\n");
        for (size_t i = 0; i < summ.size(); i++) fprintf(f, "%s,%d,%d,%.8g,%.8g,%.8g,%.8g\n", summ[i].tag.c_str(), summ[i].runs, summ[i].feas, summ[i].gmean, summ[i].gmed, summ[i].cpu, summ[i].iter);
        fclose(f);
        const char *names[2] = {"ablation_loo.csv", "ablation_add.csv"};
        const vector<Row> *rs[2] = {&loo, &add};
        for (int k = 0; k < 2; k++) {
            f = fopen((outdir + "/" + names[k]).c_str(), "w");
            fprintf(f, "operator,delta_gap_pct,ci95_lo,ci95_hi,inst_win,inst_tie,inst_loss,p_wilcoxon,p_holm,dcpu_pct\n");
            for (size_t i = 0; i < rs[k]->size(); i++) {
                const Row &r = (*rs[k])[i];
                fprintf(f, "%s,%.8g,%.8g,%.8g,%d,%d,%d,%.8g,%.8g,%.8g\n", r.op.c_str(), r.md, r.lo, r.hi, r.win, r.tie, r.los, r.p, r.padj, r.dcpu);
            }
            fclose(f);
        }
        f = fopen((outdir + "/ablation_operator_counters_full.csv").c_str(), "w");
        fprintf(f, "operator,calls,evaluations,applied,hit_pct,gain_share_pct,cpu_share_pct,gain_per_cpu_s,best_iter_gain_share_pct\n");
        for (size_t i = 0; i < opsrows.size(); i++) {
            const OpRow &r = opsrows[i];
            fprintf(f, "%s,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g\n", r.op.c_str(), r.calls, r.evals, r.applied, r.hit, r.gshare, r.cshare, r.gpc, r.bshare);
        }
        fclose(f);
        f = fopen((outdir + "/ablation_cost_benefit.csv").c_str(), "w");
        fprintf(f, "operator,cpu_share_pct,dcpu_loo_pct,dgap_loo,p_holm_loo,dgap_add,p_holm_add,verdict\n");
        for (size_t i = 0; i < cb.size(); i++)
            fprintf(f, "%s,%.8g,%.8g,%.8g,%.8g,%.8g,%.8g,\"%s\"\n", cb[i].op.c_str(), cb[i].share, cb[i].dcpu, cb[i].dl, cb[i].pl, cb[i].da, cb[i].pa, cb[i].verdict.c_str());
        fclose(f);
    }
    printf("\nCSV files written: ablation_summary.csv ablation_loo.csv ablation_add.csv ablation_operator_counters_full.csv ablation_cost_benefit.csv  (%s)\n", outdir.c_str());
    return 0;
}

#endif
