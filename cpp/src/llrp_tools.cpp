// llrp_tools -- analysis and orchestration tools of the llrp_fast kit (pure C++11, no external libraries, no Python)
//   build:  g++ -O2 -std=c++11 -o bin/llrp_tools src/llrp_tools.cpp
#include "cmd_core.hpp"
#include "cmd_ablation.hpp"
#include "cmd_xlsx.hpp"
#include "cmd_irace.hpp"

static int usage() {
    printf(
"llrp_tools COMMAND [options]\n"
"\n"
"instance sets\n"
"  manifest INSTROOT [--out manifest.tsv] [--bins 60,130]   INSTROOT/<family>/*.inst -> manifest (n,m,Q,Nv,Ng,BKS,tightness,size,flag)\n"
"  select MANIFEST [--k 2] [--seed 1] [--out-dir selection]  family x size stratified, deterministic train/test selection (for irace)\n"
"\n"
"result analysis (directory = output of run_config.sh)\n"
"  merge DIR                                  DIR/runs/*.KIND.csv -> DIR/KIND.csv\n"
"  check-csv DIR                              headers / column counts of the merged CSV files\n"
"  summarize DIR|run.csv [--csv f] [--manifest M] [--train train.txt]   per-instance summary (+ family / size / train-test summaries)\n"
"  compare DIR_A DIR_B [--tol 1e-9]           paired comparison (instance, seed); Wilcoxon, bootstrap CI\n"
"  ablation DIR [DIR2 ...] [--ref FULL] [--base BASE] [--train a,b|FILE] [--out DIR]   operator ablation (LOO / ADD / counters / cost-benefit)\n"
"  calibrate DIR [--K 25,50,...] [--target 0.05]   stall-threshold calibration (from the traces of long runs)\n"
"  verify INSTANCE.inst PREFIX [PREFIX ...]   independent verification (distances/arrivals/latency/load/partition are recomputed from the routes)\n"
"  workbook DIR [-o out.xlsx] [--no-iter] [--manifest M]   Excel file (Final_Summary, Rank_Summaries, ... Operator_Stats, Anytime_Trace)\n"
"\n"
"irace\n"
"  irace-gen --train selection/train.txt [--out irace] [--budget N] [--parallel P] [--mode time|iter] [--tc 30] [--tmin 5] [--iters 150]\n"
"  irace-flags (--from-log irace_stdout.txt | --table FILE | --args \"...\") [--row 1] [--out flags.txt]   irace result -> llrp_fast flags\n"
"  irace-sample N [--seed 1]                  random configurations from the parameter space (target-runner dry run)\n"
"\n"
"utilities\n"
"  selftest                                   self-test of the statistics functions (Wilcoxon, Holm, natural sorting, percentiles)\n"
"  wilcoxon x1 x2 ...                         two-sided Wilcoxon p-value for the given paired differences (also reads stdin)\n");
    return 1;
}

// ---- selftest: known values (hand-derived or from the literature), independent of any instance data ----
static int g_fail = 0;
static void expect_near(const char *what, double got, double want, double tol) {
    const bool ok = std::fabs(got - want) <= tol;
    printf("  %-58s %s  (got %.10g, want %.10g)\n", what, ok ? "ok  " : "FAIL", got, want);
    if (!ok) g_fail++;
}
static int cmd_selftest() {
    printf("selftest\n");
    { // 1..10 all positive: exact two-sided p = 2/2^10
        vector<double> d; for (int i = 1; i <= 10; i++) d.push_back(i);
        expect_near("wilcoxon 1..10 (all +): p = 2/1024", wilcoxon_p(d), 2.0 / 1024.0, 1e-15);
    }
    { // symmetric: 1..4 with signs +,-,-,+  -> W+ = 5, W- = 5 -> p = 1
        double a[] = {1, -2, -3, 4};
        expect_near("wilcoxon symmetric signs: p = 1", wilcoxon_p(vector<double>(a, a + 4)), 1.0, 1e-15);
    }
    { // n = 5, W- = 1 (one negative with rank 1): P(W<=1) = 2/32  -> p = 4/32
        double a[] = {-1, 2, 3, 4, 5};
        expect_near("wilcoxon n=5, W-=1: p = 0.125", wilcoxon_p(vector<double>(a, a + 5)), 0.125, 1e-15);
    }
    { // zeros are dropped; neff counts the non-zero ones
        double a[] = {0, 0, 1, 2, 3, 4, 5, 6};
        int ne = 0; const double p = wilcoxon_p(vector<double>(a, a + 8), &ne);
        expect_near("wilcoxon zeros dropped: neff = 6", ne, 6, 0);
        expect_near("wilcoxon 1..6 (all +): p = 2/64", p, 2.0 / 64.0, 1e-15);
    }
    { // tied |d| (n = 6 <= 13): exact sign-flip distribution of average ranks; ranks = 1.5,1.5,3.5,3.5,5.5,5.5 (all +) -> only the all-positive flip has W+ = 21
        double a[] = {1, -1, 2, -2, 3, -3};
        // W+ = 1.5+3.5+5.5 = 10.5 = W- -> p = 1
        expect_near("wilcoxon tied, balanced: p = 1", wilcoxon_p(vector<double>(a, a + 6)), 1.0, 1e-15);
        double b[] = {1, 1, 2, 2, 3, 3};
        expect_near("wilcoxon tied, all +: p = 2/64", wilcoxon_p(vector<double>(b, b + 6)), 2.0 / 64.0, 1e-15);
    }
    { // Holm: p = (0.01, 0.04, 0.03, 0.5) -> adj = (0.04, 0.09, 0.09, 0.5)
        double a[] = {0.01, 0.04, 0.03, 0.5};
        vector<double> h = holm_adjust(vector<double>(a, a + 4));
        expect_near("holm[0]", h[0], 0.04, 1e-15);
        expect_near("holm[1]", h[1], 0.09, 1e-15);
        expect_near("holm[2]", h[2], 0.09, 1e-15);
        expect_near("holm[3]", h[3], 0.5, 1e-15);
    }
    { // rank-biserial: all positive -> +1; all negative -> -1
        double a[] = {1, 2, 3}, b[] = {-1, -2, -3};
        expect_near("rank-biserial all +", rank_biserial(vector<double>(a, a + 3)), 1.0, 1e-15);
        expect_near("rank-biserial all -", rank_biserial(vector<double>(b, b + 3)), -1.0, 1e-15);
    }
    { // percentiles (numpy default = linear interpolation)
        double a[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
        vector<double> v(a, a + 10);
        expect_near("pct 50 of 1..10 = 5.5", pct_of(v, 50), 5.5, 1e-15);
        expect_near("pct 90 of 1..10 = 9.1", pct_of(v, 90), 9.1, 1e-12);
        expect_near("median of 1..10 = 5.5", median_of(v), 5.5, 1e-15);
        expect_near("sd of 1..10 = 3.0276503541", sd_of(v), 3.0276503541, 1e-9);
    }
    { // bootstrap CI is deterministic and contains the mean of a small sample
        double a[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
        vector<double> v(a, a + 10); double lo, hi, lo2, hi2;
        bootstrap_ci_mean(v, 2000, 0, lo, hi); bootstrap_ci_mean(v, 2000, 0, lo2, hi2);
        expect_near("bootstrap deterministic (lo)", lo, lo2, 0);
        expect_near("bootstrap deterministic (hi)", hi, hi2, 0);
        expect_near("bootstrap CI contains the mean (1 = yes)", (lo < 5.5 && 5.5 < hi) ? 1 : 0, 1, 0);
    }
    { // natural ordering: Ch50-5 < Ch100-5 ; Mi134-8 > Mi45-8 ; 20-5-1 < 100-10-2
        expect_near("nat_less(Ch50-5, Ch100-5)", nat_less("Ch50-5", "Ch100-5") ? 1 : 0, 1, 0);
        expect_near("nat_less(Mi134-8, Mi45-8)", nat_less("Mi134-8", "Mi45-8") ? 1 : 0, 0, 0);
        expect_near("nat_less(20-5-1, 100-10-2)", nat_less("20-5-1", "100-10-2") ? 1 : 0, 1, 0);
    }
    printf("%s (%d failed)\n", g_fail ? "FAILED" : "OK", g_fail);
    return g_fail ? 1 : 0;
}
static int cmd_wilcoxon(int argc, char **argv) {
    vector<double> d;
    for (int i = 2; i < argc; i++) d.push_back(atof(argv[i]));
    if (d.empty()) { double x; while (scanf("%lf", &x) == 1) d.push_back(x); }
    int ne = 0; const double p = wilcoxon_p(d, &ne);
    printf("%.17g %d\n", p, ne);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) return usage();
    const string cmd = argv[1];
    if (cmd == "manifest") return cmd_manifest(argc, argv);
    if (cmd == "select") return cmd_select(argc, argv);
    if (cmd == "merge") return cmd_merge(argc, argv);
    if (cmd == "check-csv") return cmd_check_csv(argc, argv);
    if (cmd == "summarize") return cmd_summarize(argc, argv);
    if (cmd == "compare") return cmd_compare(argc, argv);
    if (cmd == "ablation") return cmd_ablation(argc, argv);
    if (cmd == "calibrate") return cmd_calibrate(argc, argv);
    if (cmd == "verify") return cmd_verify(argc, argv);
    if (cmd == "workbook") return cmd_workbook(argc, argv);
    if (cmd == "irace-gen") return cmd_irace_gen(argc, argv);
    if (cmd == "irace-flags") return cmd_irace_flags(argc, argv);
    if (cmd == "irace-sample") return cmd_irace_sample(argc, argv);
    if (cmd == "selftest") return cmd_selftest();
    if (cmd == "wilcoxon") return cmd_wilcoxon(argc, argv);
    if (cmd == "-h" || cmd == "--help" || cmd == "help") { usage(); return 0; }
    fprintf(stderr, "llrp_tools: unknown command '%s'\n\n", cmd.c_str());
    return usage();
}
