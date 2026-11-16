#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,datetime,json,math,platform,re,statistics,sys
from pathlib import Path
from llrp_framework.core import read_dat, trace_consider, feasible, objective_components, used_depots, reset_objective_evals, get_effort_counters, start_incumbent_trace, stop_incumbent_trace
from llrp_framework.params import REGISTERED, P20_PARAMS, reference_kp
from llrp_framework.heuristics import SOLVERS, EXCLUDED_HEURISTICS, configure_search
from llrp_framework.neighborhoods import PRESETS, NEIGHBORHOODS
from llrp_framework.construction import set_rcl_policy
from llrp_framework.reporting import solution_record, routes_compact
from llrp_framework.runinfo import run_identity, budget_outcome
from llrp_framework import depot_layer, depot_impact, route_pool


def parse_seeds(s):
    if '-' in s and ',' not in s:
        a,b=s.split('-',1); return list(range(int(a),int(b)+1))
    return [int(x) for x in s.split(',')]


def parse_checkpoints(s):
    vals=sorted({float(x) for x in re.split(r'[,;:\s]+',str(s).strip()) if x})
    if any(x<=0 for x in vals):
        raise ValueError('checkpoints must be positive seconds')
    return vals


def _cp_label(x):
    return str(int(x)) if abs(x-round(x))<1e-9 else str(x).replace('.','p')


def _gap(z,ref):
    return (100.0*(float(z)-ref)/ref) if z is not None and math.isfinite(float(z)) else None


def reference_status(z,ref,tol):
    """One-sided comparison with the literature value: hit = not worse than ref+tol, beats = better than ref-tol."""
    if z is None or not math.isfinite(float(z)):
        return dict(gap_pct=None,hit=False,beats=False)
    z=float(z)
    return dict(gap_pct=100.0*(z-ref)/ref,hit=z<=ref+tol,beats=z<ref-tol)


def _first_target_time(events, ref, gap_pct, tol=0.0):
    threshold=ref*(1.0+gap_pct/100.0)+tol
    for e in events:
        if float(e['objective']) <= threshold:
            return float(e['time_s'])
    return None


def write_aggregate(rows,path):
    keys=[]
    for r in rows:
        k=(r['instance'],r['heuristic'],r['local_search'],r['neighborhoods'],r['budget_mode'])
        if k not in keys: keys.append(k)
    out=[]
    for k in keys:
        rr=[r for r in rows if (r['instance'],r['heuristic'],r['local_search'],r['neighborhoods'],r['budget_mode'])==k]
        vals=[float(r['objective']) for r in rr if r['objective'] is not None and math.isfinite(float(r['objective']))]
        times=[float(r['runtime_wall_s']) for r in rr]
        out.append(dict(instance=k[0],heuristic=k[1],local_search=k[2],neighborhoods=k[3],budget_mode=k[4],
                        runs=len(rr),best=min(vals) if vals else None,mean=statistics.mean(vals) if vals else None,
                        stdev=statistics.stdev(vals) if len(vals)>1 else 0.0,worst=max(vals) if vals else None,
                        reference_best=rr[0]['reference_best'],reference_hits=sum(bool(r['reference_hit']) for r in rr),beats_reference=sum(bool(r['beats_reference']) for r in rr),
                        hit_rate=sum(bool(r['reference_hit']) for r in rr)/len(rr),
                        mean_runtime_s=statistics.mean(times),
                        mean_time_to_best_s=statistics.mean(float(r['time_to_best_s']) for r in rr if r['time_to_best_s'] is not None) if any(r['time_to_best_s'] is not None for r in rr) else None,mean_trials=statistics.mean(float(r['trials']) for r in rr),
                        mean_ls_moves=statistics.mean(float(r['ls_moves']) for r in rr),
                        mean_objective_evals=statistics.mean(float(r.get('objective_evals',0)) for r in rr)))
    if out:
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)


def write_config(out,a,root,ident):
    """Record everything needed to reproduce this run next to its results.

    config_id / fingerprint / hashes: see llrp_framework/runinfo.py. The launcher compares the stored
    fingerprint with the one the current code would produce before it skips a finished run."""
    vfile=root/'VERSION'
    cfg=dict(problem='LLRP',code_version=vfile.read_text().strip() if vfile.exists() else 'unknown',
             python=platform.python_version(),platform=platform.platform(),host=platform.node(),
             started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
             config_id=ident['config_id'],fingerprint=ident['fingerprint'],source_sha256=ident['source_sha256'],
             python_family=ident['python_family'],solver_stack=ident.get('solver_stack',{}),instance_sha256=ident['instance_sha256'],reference_sha256=ident['reference_sha256'],
             formulation=dict(depots=f'at most p open depots (p from reference/LLRP_reference.csv unless --p is given); depot capacity: {a.depot_capacity}',
                              fleet='at most K routes (K from reference/LLRP_reference.csv unless --K is given); vehicle capacity Q enforced',
                              note='K and p are binding (K_binding, p_binding in the reports)',
                              objective='latency: sum over customers of the arrival time; the vehicle leaves the depot at time 0 and does not return; no opening or vehicle cost; real-valued Euclidean distances'),
             argv=sys.argv[1:],args={k:(str(v) if isinstance(v,Path) else v) for k,v in vars(a).items()})
    (out/'config.json').write_text(json.dumps(cfg,indent=1,sort_keys=True))


def build_parser():
    ap=argparse.ArgumentParser(description='Modular LLRP (latency location-routing) heuristic laboratory: the 17 campaign methods (19 registered) and the adaptive depot layer of the CLRP 6.4.0 kit, ported to the latency objective')
    ap.add_argument('--kit-root',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--instances',default=','.join(P20_PARAMS),help='comma-separated instance IDs (P20, P50, Barreto and Tuzun-Burke instances are registered; see llrp_framework/params.py)')
    ap.add_argument('--seeds',default='1')
    ap.add_argument('--heuristic',choices=sorted(SOLVERS),default='grasp')
    ap.add_argument('--allow-excluded',action='store_true',help='run a heuristic that is excluded from the campaigns (see EXCLUDED_HEURISTICS)')
    ap.add_argument('--local-search',choices=['none','first','vnd','rvnd','best'],default='none')
    ap.add_argument('--neighborhoods',default='light',help='preset light/hgamp or comma-separated names')
    ap.add_argument('--restarts-per-depot-subset',type=int,default=10)
    ap.add_argument('--alpha',type=float,default=0.02,help='legacy value-RCL alpha; ignored in cardinality mode')
    ap.add_argument('--rcl-mode',choices=['cardinality','value'],default='cardinality')
    ap.add_argument('--rcl-max',type=int,default=7)
    ap.add_argument('--time-limit',type=float,default=30)
    ap.add_argument('--checkpoints',default='30,60,90,120',help='comma-separated wall-clock incumbent checkpoints in seconds')
    ap.add_argument('--budget-mode',choices=['fixed_trials','fixed_time'],default='fixed_time')
    ap.add_argument('--depot-mode',choices=['enumerate','sample','pmedian','race'],default='pmedian',help='depot p-subsets of a pass: all in random order | random sample | the --depot-sample subsets with the smallest p-median bound | race: the same arms with the budget allocated by a p-median rank prior corrected by the evidence (see heuristics.DepotRace)')
    ap.add_argument('--race-gamma',type=float,default=2.0,help='race: exponent of the p-median rank prior 1/(rank+1)^gamma (0 = uniform arms)')
    ap.add_argument('--race-explore',type=int,default=8,help='race: every n-th pull goes to the best-ranked arm not pulled yet (0 = never)')
    ap.add_argument('--sp-share',type=float,default=0.0,help='set-partitioning polish: share of the --time-limit (fixed_time only) reserved at the end to recombine the routes of all local optima collected during the search (0 = off). Needs scipy; skipped and reported otherwise')
    ap.add_argument('--sp-theta',type=float,default=0.03,help='route pool: a local optimum contributes its routes when its objective is within this fraction of the best seen so far')
    ap.add_argument('--start-mix',type=float,default=0.0,help='probability that a start solution of a subset-loop method is built by random-priority insertion instead of grasp_construct (0 = previous behaviour, bit-identical)')
    ap.add_argument('--depot-sample',type=int,default=50)
    # CLRP depot layers (halving / MILP) are NOT ported to the LLRP kit: only 'none' is accepted. The --layer-* options are kept so that
    # command lines and config fingerprints of the CLRP kit stay parseable; they have no effect.
    ap.add_argument('--depot-layer',choices=list(depot_layer.LAYERS),default='none',
                    help="none only (the CLRP halving / MILP depot layers are not ported to the LLRP kit)")
    ap.add_argument('--layer-sets',type=int,default=8,help='candidate depot sets at the first rung')
    ap.add_argument('--layer-eta',type=int,default=2,help='elimination factor of the halving')
    ap.add_argument('--layer-probe-frac',type=float,default=0.05,help='share of the time budget for the probe solution')
    ap.add_argument('--layer-beta',type=float,default=-1.0,help='MILP routing proxy scale; < 0 calibrates it on the probe solution')
    ap.add_argument('--layer-milp-time',type=float,default=2.0,help='seconds per MILP solve (k solves for the k best sets)')
    ap.add_argument('--layer-milp-frac',type=float,default=0.10,help='upper bound of the MILP time as a share of the time budget')
    ap.add_argument('--layer-milp-single',action='store_true',help='single-source assignment in the MILP (slower, closer to the LLRP)')
    # 6.3: single-factor depot impact pilot. Keep original LS preset and all
    # heuristic hyperparameters frozen; these flags only change depot events.
    ap.add_argument('--depot-impact',choices=('off','balanced','structural','adaptive'),default='off')
    ap.add_argument('--depot-impact-every',type=int,default=8)
    ap.add_argument('--depot-impact-max-share',type=float,default=0.10)
    ap.add_argument('--depot-impact-event-seconds',type=float,default=1.5)
    ap.add_argument('--depot-impact-min-interval',type=float,default=2.0)
    # 6.4.0 (mode adaptive only; see llrp_framework/depot_adaptive64.py). Fractions are shares of --time-limit.
    ap.add_argument('--depot-impact-first-frac',type=float,default=0.05,help='adaptive: no event before this share of the budget')
    ap.add_argument('--depot-impact-period-frac',type=float,default=0.06,help='adaptive: minimum gap between events (from the end of the previous one)')
    ap.add_argument('--depot-impact-exploit-start',type=float,default=0.30,help='adaptive: from this share on events intensify the best elite depot sets; >=1 disables exploitation')
    ap.add_argument('--depot-impact-exploit-slice',type=float,default=0.04,help='adaptive: length of one exploitation event as a share of the budget')
    ap.add_argument('--depot-impact-cap-exp',type=float,default=3.0,help='adaptive: exploration event cap = event_seconds * max(1,(n/100)**cap_exp); 0 disables the scaling')
    ap.add_argument('--reference-tol',type=float,default=0.01,help='absolute tolerance of a reference hit (the tabulated best-known values are rounded to 2 decimals)')
    ap.add_argument('--K',type=int,default=None,help='override the fleet bound of the instance (default: reference/LLRP_reference.csv)')
    ap.add_argument('--p',type=int,default=None,help='override the open-depot bound of the instance (default: reference/LLRP_reference.csv)')
    ap.add_argument('--depot-capacity',choices=['ignore','enforce'],default='ignore',help='ignore (default, literature): depots uncapacitated; enforce: capacities of the .dat file')
    ap.add_argument('--out-dir',type=Path,default=Path('analysis/llrp_run'))
    ap.add_argument('--list-neighborhoods',action='store_true')
    ap.add_argument('--list-heuristics',action='store_true')
    ap.add_argument('--print-fingerprint',action='store_true',help='print the run fingerprint (used by the launcher to validate a resume) and exit')
    # ILS / VNS
    ap.add_argument('--ils-iters',type=int,default=25); ap.add_argument('--perturb-strength',type=int,default=2)
    ap.add_argument('--vns-kmax',type=int,default=5); ap.add_argument('--vns-iters',type=int,default=50)
    # SA
    ap.add_argument('--sa-iters',type=int,default=4000); ap.add_argument('--sa-t0-factor',type=float,default=0.08)
    ap.add_argument('--sa-cooling',type=float,default=0.995); ap.add_argument('--sa-reheat',type=float,default=0.35)
    # Tabu
    ap.add_argument('--tabu-iters',type=int,default=1200); ap.add_argument('--tabu-tenure',type=int,default=25)
    ap.add_argument('--tabu-candidates',type=int,default=30)
    # GA / memetic GA
    ap.add_argument('--ga-pop',type=int,default=30); ap.add_argument('--ga-generations',type=int,default=200)
    ap.add_argument('--ga-mutation',type=float,default=0.25); ap.add_argument('--ga-elite',type=int,default=2)
    # ALNS
    ap.add_argument('--destroy-mode',choices=['fixed','range','floor'],default=None,help='ALNS / LNS / IG removal size: fixed = round(frac n); range = uniform in [max(4, 0.1 n), 0.4 n] per step; floor = max(7, round(frac n)). Default (not given): floor for ALNS and LNS, fixed for IG')
    ap.add_argument('--alns-iters',type=int,default=2500); ap.add_argument('--alns-destroy-frac',type=float,default=0.20)
    ap.add_argument('--alns-reaction',type=float,default=0.2); ap.add_argument('--alns-cooling',type=float,default=0.997)
    # MSLS / LNS
    ap.add_argument('--msls-starts',type=int,default=100)
    ap.add_argument('--lns-iters',type=int,default=2500); ap.add_argument('--lns-destroy-frac',type=float,default=0.20)
    # BRKGA
    ap.add_argument('--brkga-pop',type=int,default=40); ap.add_argument('--brkga-generations',type=int,default=250)
    ap.add_argument('--brkga-elite-frac',type=float,default=0.20); ap.add_argument('--brkga-mutant-frac',type=float,default=0.10)
    ap.add_argument('--brkga-rho',type=float,default=0.70)
    # ACO
    ap.add_argument('--aco-ants',type=int,default=24); ap.add_argument('--aco-iterations',type=int,default=200)
    ap.add_argument('--aco-alpha',type=float,default=1.0); ap.add_argument('--aco-beta',type=float,default=2.0)
    ap.add_argument('--aco-evap',type=float,default=0.20); ap.add_argument('--aco-q',type=float,default=100.0)
    # Record-to-record travel
    ap.add_argument('--rtr-iters',type=int,default=5000); ap.add_argument('--rtr-threshold-frac',type=float,default=0.02)
    ap.add_argument('--rtr-decay',type=float,default=0.999)
    # Threshold Accepting / Iterated Greedy
    ap.add_argument('--ta-iters',type=int,default=5000); ap.add_argument('--ta-threshold-frac',type=float,default=0.03); ap.add_argument('--ta-decay',type=float,default=0.999)
    ap.add_argument('--ig-iters',type=int,default=2500); ap.add_argument('--ig-destroy-frac',type=float,default=0.15); ap.add_argument('--ig-accept-frac',type=float,default=0.0)
    # Path relinking / Scatter Search
    ap.add_argument('--grasppr-starts',type=int,default=80); ap.add_argument('--grasppr-elite',type=int,default=6); ap.add_argument('--grasppr-steps',type=int,default=20)
    ap.add_argument('--scatter-pool',type=int,default=24); ap.add_argument('--scatter-refset',type=int,default=8); ap.add_argument('--scatter-iters',type=int,default=30); ap.add_argument('--scatter-steps',type=int,default=20)
    # Random-key PSO / Differential Evolution
    ap.add_argument('--pso-particles',type=int,default=28); ap.add_argument('--pso-iters',type=int,default=250); ap.add_argument('--pso-w',type=float,default=0.72); ap.add_argument('--pso-c1',type=float,default=1.45); ap.add_argument('--pso-c2',type=float,default=1.45)
    ap.add_argument('--de-pop',type=int,default=30); ap.add_argument('--de-iters',type=int,default=250); ap.add_argument('--de-f',type=float,default=0.7); ap.add_argument('--de-cr',type=float,default=0.85)
    ap.add_argument('--rkrs-trials',type=int,default=5000,help='fixed-trial cap for the random-key random-search control')
    return ap


def main():
    a=build_parser().parse_args()
    checkpoints=parse_checkpoints(a.checkpoints)
    if a.list_neighborhoods:
        print('PRESETS:',json.dumps(PRESETS,indent=2)); print('ALL:',', '.join(NEIGHBORHOODS)); return
    if a.list_heuristics:
        print('HEURISTICS:', ', '.join(sorted(SOLVERS)))
        print('Pure versions: use --local-search none')
        print('Native Phase-A improvement: --local-search first; Phase-B/ablation: vnd/rvnd/best')
        return
    if a.heuristic in EXCLUDED_HEURISTICS and not a.allow_excluded:
        raise SystemExit(f"ERROR: heuristic '{a.heuristic}' is excluded from the campaigns: {EXCLUDED_HEURISTICS[a.heuristic]} (use --allow-excluded for diagnostics only)")
    if a.depot_impact!='off' and (a.local_search!='first' or a.neighborhoods!='loffler9'):
        raise SystemExit('ERROR: --depot-impact balanced/structural/adaptive currently supports only --local-search first --neighborhoods loffler9')
    set_rcl_policy(a.rcl_mode,a.rcl_max)
    configure_search(a.start_mix,a.race_gamma,a.race_explore)
    if a.sp_share>0:
        if not 0.0<a.sp_share<0.5: raise SystemExit('ERROR: --sp-share must be in (0, 0.5)')
        if a.budget_mode!='fixed_time': raise SystemExit('ERROR: --sp-share needs --budget-mode fixed_time')
        try:
            import scipy.optimize, scipy.sparse   # noqa: F401
        except Exception:
            raise SystemExit('ERROR: --sp-share needs scipy (scipy.optimize.milp); it is not importable here. Refusing to run: the search would lose its time share for nothing.')
    root=a.kit_root.resolve(); refs={k:dict(instance_id=k,reference_best=v['bks'],K=v['K'],p=v['p'],name=v['name']) for k,v in REGISTERED.items()}
    names=[x.strip() for x in a.instances.split(',') if x.strip()]
    for name in names:
        if name not in REGISTERED:
            raise KeyError(f'{name} is not a registered LLRP instance (llrp_framework/params.py: P20, P50, B, T)')
    ident=run_identity(a,root,'llrp_framework','run_llrp.py',
                       {n:root/'data'/REGISTERED[n]['family']/REGISTERED[n]['file'] for n in names},{n:refs[n] for n in names})
    if a.print_fingerprint:
        print(ident['fingerprint']); return
    out=a.out_dir if a.out_dir.is_absolute() else root/a.out_dir; out.mkdir(parents=True,exist_ok=True)
    write_config(out,a,root,ident)
    timed=(a.budget_mode=='fixed_time')
    rows=[]; trace_rows=[]
    extra=dict(destroy_mode=a.destroy_mode,ils_iters=a.ils_iters,perturb_strength=a.perturb_strength,vns_kmax=a.vns_kmax,vns_iters=a.vns_iters,
               sa_iters=a.sa_iters,sa_t0_factor=a.sa_t0_factor,sa_cooling=a.sa_cooling,sa_reheat=a.sa_reheat,
               tabu_iters=a.tabu_iters,tabu_tenure=a.tabu_tenure,tabu_candidates=a.tabu_candidates,
               ga_pop=a.ga_pop,ga_generations=a.ga_generations,ga_mutation=a.ga_mutation,ga_elite=a.ga_elite,
               alns_iters=a.alns_iters,alns_destroy_frac=a.alns_destroy_frac,alns_reaction=a.alns_reaction,alns_cooling=a.alns_cooling,
               msls_starts=a.msls_starts,lns_iters=a.lns_iters,lns_destroy_frac=a.lns_destroy_frac,
               brkga_pop=a.brkga_pop,brkga_generations=a.brkga_generations,brkga_elite_frac=a.brkga_elite_frac,
               brkga_mutant_frac=a.brkga_mutant_frac,brkga_rho=a.brkga_rho,
               aco_ants=a.aco_ants,aco_iterations=a.aco_iterations,aco_alpha=a.aco_alpha,aco_beta=a.aco_beta,
               aco_evap=a.aco_evap,aco_q=a.aco_q,rtr_iters=a.rtr_iters,rtr_threshold_frac=a.rtr_threshold_frac,rtr_decay=a.rtr_decay,
               ta_iters=a.ta_iters,ta_threshold_frac=a.ta_threshold_frac,ta_decay=a.ta_decay,
               ig_iters=a.ig_iters,ig_destroy_frac=a.ig_destroy_frac,ig_accept_frac=a.ig_accept_frac,
               grasppr_starts=a.grasppr_starts,grasppr_elite=a.grasppr_elite,grasppr_steps=a.grasppr_steps,
               scatter_pool=a.scatter_pool,scatter_refset=a.scatter_refset,scatter_iters=a.scatter_iters,scatter_steps=a.scatter_steps,
               pso_particles=a.pso_particles,pso_iters=a.pso_iters,pso_w=a.pso_w,pso_c1=a.pso_c1,pso_c2=a.pso_c2,
               de_pop=a.de_pop,de_iters=a.de_iters,de_f=a.de_f,de_cr=a.de_cr,rkrs_trials=a.rkrs_trials)
    for name in names:
        prm=REGISTERED[name]; inst=read_dat(root/'data'/prm['family']/prm['file'],depot_capacity=a.depot_capacity); ref=float(refs[name]['reference_best'])
        # LLRP: at most K routes and at most p open depots (both bind in the benchmark; the best-known solutions use exactly K and p).
        K,p=reference_kp(name)
        if a.K is not None: K=a.K
        if a.p is not None: p=a.p
        for seed in parse_seeds(a.seeds):
            common=dict(inst=inst,K=K,p=p,seed=seed,restarts=a.restarts_per_depot_subset,alpha=a.alpha,
                        ls_method=a.local_search,ls_preset=a.neighborhoods,time_limit=(a.time_limit if timed else None),
                        depot_mode=a.depot_mode,depot_sample=a.depot_sample,budget_mode=a.budget_mode,**extra)
            # Two explicit budget policies: fixed_time (wall-clock deadline, incumbents after it are discarded) and
            # fixed_trials (no deadline, no time cap on the trace). --time-limit is ignored by fixed_trials.
            depot_impact.configure(a.depot_impact,(a.time_limit if timed else None),seed,
                a.depot_impact_every,a.depot_impact_max_share,
                a.depot_impact_event_seconds,a.depot_impact_min_interval,
                a.depot_impact_first_frac,a.depot_impact_period_frac,a.depot_impact_exploit_start,
                a.depot_impact_exploit_slice,a.depot_impact_cap_exp)
            sp_pool=None; sp_info=dict(sp_status='off',sp_cols=0,sp_s=0.0,sp_improved=False,sp_obj=None)
            if a.sp_share>0 and timed and a.depot_layer=='none':
                sp_pool=route_pool.enable(inst,a.sp_theta); common['time_limit']=a.time_limit*(1.0-a.sp_share)
            reset_objective_evals()
            start_incumbent_trace(checkpoints=checkpoints,max_time=(a.time_limit if timed else float('inf')))
            if a.depot_layer!='none':
                raw_sol,raw_z,trials,moves,secs,passes=depot_layer.run_layer(SOLVERS[a.heuristic],a.heuristic,common,depot_layer.LayerConfig.from_args(a))
                linfo=dict(depot_layer.LAST_INFO)
            else:
                raw_sol,raw_z,trials,moves,secs,passes=SOLVERS[a.heuristic](**common); linfo=None
            if sp_pool is not None:
                _left=a.time_limit-float(secs)-0.25                     # SP gets what the search left unused of the budget (the tracer started with the search)
                _sol2,sp_info=route_pool.recombine(inst,K,p,raw_sol,raw_z,_left,pool=sp_pool)
                if _sol2 is not None:
                    from llrp_framework.core import objective as _obj
                    _z2=_obj(inst,_sol2); trace_consider(_z2,_sol2); raw_sol,raw_z=_sol2,_z2
                secs=float(secs)+sp_info['sp_s']; sp_info['sp_solutions']=sp_pool.solutions; route_pool.disable()
            trace=stop_incumbent_trace(final_z=raw_z,final_sol=raw_sol)
            effort=get_effort_counters()
            cpvals={float(k):v for k,v in trace['checkpoints'].items()}
            trace_best=trace.get('trace_best')
            trace_sol=trace.get('trace_best_solution')
            # Reported fixed-budget result = best feasible incumbent exposed no later than the deadline.
            # What the solver returns after the deadline is a diagnostic only: it is never promoted to
            # the result. Without an in-budget incumbent the run has status no_incumbent_within_budget
            # and no objective (see runinfo.budget_outcome).
            status_code,sol,z,trace_missing=budget_outcome(trace_best,trace_sol,raw_sol,raw_z,a.budget_mode)
            fixed_obj=z
            raw_match=bool(trace.get('raw_final_consistent',False))
            raw_z_out=float(raw_z) if raw_z is not None and math.isfinite(float(raw_z)) else None
            overrun=max(0.0,float(secs)-float(a.time_limit)) if timed else 0.0
            trace_final_consistent=bool((not trace_missing) and trace_best is not None)
            ok=bool(sol and feasible(inst,sol,K,p))
            opening=vehicle=routing=None
            if sol:
                opening,vehicle,routing=objective_components(inst,sol)
            anytime={}
            for cp in checkpoints:
                lab=_cp_label(cp); val=cpvals.get(cp)
                anytime[f'objective_{lab}s']=val
                anytime[f'gap_{lab}s_pct']=_gap(val,ref)
            status=reference_status(z,ref,a.reference_tol)
            rec=solution_record(inst,sol) if sol else None
            events=trace['events']; time_to_best=float(events[-1]['time_s']) if events else None
            tt_bks=_first_target_time(trace['events'],ref,0.0,a.reference_tol)
            tt05=_first_target_time(trace['events'],ref,0.5,0.0)
            tt10=_first_target_time(trace['events'],ref,1.0,0.0)
            for idx,e in enumerate(trace['events'],1):
                trace_rows.append(dict(problem='LLRP',instance=name,seed=seed,heuristic=a.heuristic,
                                       local_search=a.local_search,neighborhoods=a.neighborhoods,event=idx,
                                       time_s=float(e['time_s']),objective=float(e['objective']),gap_pct=_gap(e['objective'],ref)))
            row=dict(problem='LLRP',instance=name,family=prm['family'],seed=seed,heuristic=a.heuristic,
                     local_search=a.local_search,neighborhoods=a.neighborhoods,status=status_code,config_id=ident['config_id'],fingerprint=ident['fingerprint'],
                     budget_mode=a.budget_mode,K=K,p=p,K_binding=True,p_binding=True,depot_capacity=a.depot_capacity,
                     time_limit_s=(a.time_limit if timed else None),rcl_mode=a.rcl_mode,rcl_max=a.rcl_max,alpha=a.alpha,n=inst.n,m=inst.m,Q=inst.Q,distance_rule=inst.distance_rule,
                     routes=(len(sol) if sol else 0),open_depots=(len(used_depots(sol)) if sol else 0),
                     reference_best=ref,objective=z,gap_pct=status['gap_pct'],
                     reference_hit=status['hit'],
                     opening_cost=opening,vehicle_fixed_cost=vehicle,routing_cost=routing,latency=routing,
                     objective_fixed_budget=fixed_obj,trace_best_objective=trace_best,trace_final_consistent=trace_final_consistent,trace_missing=trace_missing,
                    raw_solver_objective=raw_z_out,raw_solver_trace_consistent=raw_match,budget_overrun_s=overrun,
                     tt_bks_s=tt_bks,tt_bks_censored=(tt_bks is None),tt_gap_0_5_s=tt05,tt_gap_0_5_censored=(tt05 is None),tt_gap_1_0_s=tt10,tt_gap_1_0_censored=(tt10 is None),
                     **anytime,
                     runtime_wall_s=secs,trials=trials,passes=passes,ls_moves=moves,objective_evals=effort['objective_evals'],route_evals=effort['route_evals'],
                     construct_calls=effort['construct_calls'],construct_failures=effort['construct_failures'],feasible=ok,
                     depot_impact_mode=a.depot_impact,**depot_impact.stats(),
                     sp_status=sp_info.get('sp_status'),sp_cols=sp_info.get('sp_cols'),sp_s=sp_info.get('sp_s'),sp_improved=sp_info.get('sp_improved'),sp_obj=sp_info.get('sp_obj'),
                     beats_reference=status['beats'],reference_tol=a.reference_tol,time_to_best_s=time_to_best,
                     open_depot_ids=';'.join(map(str,rec['open_depots'])) if rec else '',solution_routes=routes_compact(sol) if sol else '')
            if linfo is not None:
                row.update(depot_layer=a.depot_layer,layer_sets=len(linfo['candidates']),layer_winner=';'.join(map(str,linfo['winner'])),
                           layer_winner_is_all=linfo['winner_is_all'],layer_beta=linfo.get('beta'),layer_probe_objective=linfo.get('probe_objective'),
                           layer_milp_s=linfo.get('milp_s'))
            rows.append(row); print(row,flush=True)
            if sol:
                fn=out/f'{name}_{a.heuristic}_{a.local_search}_{a.neighborhoods}_{a.budget_mode}_seed{seed}.sol.txt'
                with fn.open('w') as f:
                    f.write(f'problem LLRP\nobjective {z:.12f}\nreference {ref:.12f}\n')
                    f.write(f'raw_solver_objective {raw_z_out if raw_z_out is not None else "NA"} raw_solver_runtime_s {float(secs):.12f} budget_overrun_s {float(overrun):.12f}\n')
                    f.write(f'opening {opening:.12f} vehicle {vehicle:.12f} routing {routing:.12f}\n')
                    f.write(f'distance_rule {inst.distance_rule} routes {len(sol)} open_depots {len(used_depots(sol))}\n')
                    f.write('open_depot_ids '+' '.join(map(str,rec['open_depots']))+'  (0-based indices in .dat order; customers are 0-based as well)\n')
                    for k,r in enumerate(rec['routes'],1): f.write(f'route {k} depot {r["depot"]} load {r["load"]:g} cost {r["cost"]:.6f}: '+' '.join(map(str,r['customers']))+'\n')
                cps={}
                for cp in checkpoints:
                    cs=trace.get('checkpoint_solutions',{}).get(cp)
                    cps[_cp_label(cp)]=None if cs is None else dict(time_s=cp,objective=cpvals.get(cp),gap_pct=_gap(cpvals.get(cp),ref),**solution_record(inst,cs))
                payload=dict(problem='LLRP',instance=name,heuristic=a.heuristic,local_search=a.local_search,neighborhoods=a.neighborhoods,seed=seed,
                             status=status_code,config_id=ident['config_id'],fingerprint=ident['fingerprint'],
                             budget_mode=a.budget_mode,time_limit_s=(a.time_limit if timed else None),index_base=0,K=K,p=p,K_binding=True,p_binding=True,depot_capacity=a.depot_capacity,reference_best=ref,reference_tol=a.reference_tol,
                             objective=z,gap_pct=status['gap_pct'],reference_hit=status['hit'],beats_reference=status['beats'],time_to_best_s=time_to_best,distance_rule=inst.distance_rule,objective_components=dict(opening=opening,vehicle=vehicle,routing=routing),
                             **rec,checkpoints=cps)
                if linfo is not None: payload['depot_layer']=linfo
                fn.with_name(fn.name[:-len('.sol.txt')]+'.solution.json').write_text(json.dumps(payload,separators=(',',':')))
    # trajectory.csv always exists (header only when no in-budget incumbent was found), so a missing file means a crashed run.
    with (out/'trajectory.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['problem','instance','seed','heuristic','local_search','neighborhoods','event','time_s','objective','gap_pct'])
        w.writeheader(); w.writerows(trace_rows)
    if rows:
        with (out/'summary.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        write_aggregate(rows,out/'aggregate.csv')
        print(out/'summary.csv'); print(out/'aggregate.csv')

if __name__=='__main__': main()
