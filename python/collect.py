#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,math,statistics
from pathlib import Path


def fnum(x):
    try:
        if x in (None,''): return None
        y=float(x)
        return y if math.isfinite(y) else None
    except Exception:
        return None


def bval(x):
    return str(x).strip().lower() in {'1','true','yes','y'}


def write_csv(path,rows,fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:
        path.write_text('')
        return
    if fields is None:
        fields=[]
        seen=set()
        for r in rows:
            for k in r:
                if k not in seen:
                    fields.append(k); seen.add(k)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def main():
    ap=argparse.ArgumentParser(description='Collect Phase-A V12 anytime/checkpoint experiments. Results are grouped by config_id '
                                           '(code + method + local search + neighbourhoods + budget + every hyper-parameter), never by heuristic name alone.')
    ap.add_argument('root',type=Path)
    ap.add_argument('--out',type=Path,default=None)
    ap.add_argument('--allow-duplicates',action='store_true',help='do not fail when the same (instance, seed, configuration) occurs more than once')
    a=ap.parse_args()
    root=a.root.resolve(); out=(a.out.resolve() if a.out else root/'report.csv')

    rows=[]
    for p in sorted(root.rglob('summary.csv')):
        if p.resolve()==out: continue
        with p.open(newline='') as f:
            rows.extend(csv.DictReader(f))
    write_csv(out,rows)

    # Pooling safety. A configuration is identified by config_id (written by the runner); rows from older
    # kits have none and are grouped under 'legacy'. The same (instance, seed, configuration) must occur once.
    for r in rows:
        r['config_id']=r.get('config_id') or 'legacy'
        r['status']=r.get('status') or 'ok'
    legacy=sum(r['config_id']=='legacy' for r in rows)
    seen={}; dup=[]
    for r in rows:
        k=(r.get('problem'),r.get('instance'),r.get('seed'),r['config_id'],r.get('heuristic'),r.get('local_search'),r.get('neighborhoods'))
        if k in seen: dup.append(r)
        else: seen[k]=r
    write_csv(root/'duplicates.csv',dup)
    registry={}
    for r in rows:
        k=(r['config_id'],r.get('problem'),r.get('heuristic'),r.get('local_search'),r.get('neighborhoods'),r.get('budget_mode'),r.get('time_limit_s'))
        registry[k]=registry.get(k,0)+1
    write_csv(root/'config_registry.csv',[dict(config_id=k[0],problem=k[1],heuristic=k[2],local_search=k[3],neighborhoods=k[4],
                                               budget_mode=k[5],time_limit_s=k[6],runs=v) for k,v in sorted(registry.items(),key=lambda kv:[str(x) for x in kv[0]])])
    by_method={}
    for k in registry:
        by_method.setdefault((k[1],k[2],k[3],k[4]),set()).add(k[0])
    mixed=[m for m,ids in by_method.items() if len(ids)>1]
    stat={}
    for r in rows:
        k=(r.get('problem'),r['config_id'],r.get('heuristic'),r.get('local_search'),r.get('neighborhoods'),r['status'])
        stat[k]=stat.get(k,0)+1
    write_csv(root/'run_status_summary.csv',[dict(problem=k[0],config_id=k[1],heuristic=k[2],local_search=k[3],neighborhoods=k[4],status=k[5],runs=v)
                                             for k,v in sorted(stat.items(),key=lambda kv:[str(x) for x in kv[0]])])

    traj=[]
    for p in sorted(root.rglob('trajectory.csv')):
        with p.open(newline='') as f:
            traj.extend(csv.DictReader(f))
    write_csv(root/'trajectories.csv',traj)

    # Identify checkpoint columns such as objective_30s / gap_30s_pct.
    cps=[]
    if rows:
        for k in rows[0].keys():
            if k.startswith('objective_') and k.endswith('s') and k!='objective_fixed_budget':
                raw=k[len('objective_'):-1]
                try: cp=float(raw.replace('p','.'))
                except Exception: continue
                cps.append((cp,raw))
        cps=sorted(set(cps))

    long=[]
    for r in rows:
        ref=fnum(r.get('reference_best'))
        for cp,lab in cps:
            z=fnum(r.get(f'objective_{lab}s'))
            g=fnum(r.get(f'gap_{lab}s_pct'))
            tol=fnum(r.get('reference_tol'))
            if tol is None: tol=0.01
            hit=(z is not None and ref is not None and z <= ref+tol)
            beats=(z is not None and ref is not None and z < ref-tol)
            long.append({
                'problem':r.get('problem'),'instance':r.get('instance'),'seed':r.get('seed'),
                'config_id':r['config_id'],'status':r['status'],
                'heuristic':r.get('heuristic'),'local_search':r.get('local_search'),'neighborhoods':r.get('neighborhoods'),
                'checkpoint_s':cp,'objective':z,'gap_pct':g,'reference_best':ref,'reference_hit':hit,'beats_reference':beats,
            })
    write_csv(root/'checkpoint_long.csv',long)

    # Aggregate checkpoint performance at problem x heuristic x checkpoint level.
    meth=[]
    gk=lambda r:(r['problem'],r['config_id'],r['heuristic'],r['local_search'],r['neighborhoods'],r['checkpoint_s'])
    keys=sorted({gk(r) for r in long},key=lambda k:[str(x) for x in k])
    for key in keys:
        rr=[r for r in long if gk(r)==key]
        gaps=[r['gap_pct'] for r in rr if r['gap_pct'] is not None]
        objs=[r['objective'] for r in rr if r['objective'] is not None]
        hits=sum(bool(r['reference_hit']) for r in rr); beats=sum(bool(r['beats_reference']) for r in rr)
        meth.append({
            'problem':key[0],'config_id':key[1],'heuristic':key[2],'local_search':key[3],'neighborhoods':key[4],'checkpoint_s':key[5],'runs':len(rr),
            'best_objective':min(objs) if objs else None,
            'mean_gap_pct':statistics.mean(gaps) if gaps else None,
            'median_gap_pct':statistics.median(gaps) if gaps else None,
            'stdev_gap_pct':statistics.stdev(gaps) if len(gaps)>1 else 0.0 if gaps else None,
            'reference_hits':hits,'hit_rate':hits/len(rr) if rr else None,'beats_reference':beats,
        })
    write_csv(root/'anytime_method_summary.csv',meth)

    # Per-instance target-reaching summaries. Times are success-only descriptive
    # statistics; censoring indicators remain available in report.csv for formal
    # survival/time-to-target analysis.
    targets=[('bks','tt_bks_s','tt_bks_censored'),('gap_0_5','tt_gap_0_5_s','tt_gap_0_5_censored'),('gap_1_0','tt_gap_1_0_s','tt_gap_1_0_censored')]
    trows=[]
    ik=lambda r:(r.get('problem'),r.get('instance'),r['config_id'],r.get('heuristic'),r.get('local_search'),r.get('neighborhoods'))
    ikeys=sorted({ik(r) for r in rows},key=lambda k:[str(x) for x in k])
    for k in ikeys:
        rr=[r for r in rows if ik(r)==k]
        rec={'problem':k[0],'instance':k[1],'config_id':k[2],'heuristic':k[3],'local_search':k[4],'neighborhoods':k[5],'runs':len(rr),
             'runs_without_incumbent':sum(r['status']!='ok' for r in rr)}
        for name,tcol,ccol in targets:
            times=[fnum(r.get(tcol)) for r in rr if not bval(r.get(ccol)) and fnum(r.get(tcol)) is not None]
            rec[f'{name}_successes']=len(times)
            rec[f'{name}_success_rate']=len(times)/len(rr) if rr else None
            rec[f'{name}_mean_time_success_s']=statistics.mean(times) if times else None
            rec[f'{name}_median_time_success_s']=statistics.median(times) if times else None
            # Expected running time (COCO-style): total time spent per success, a failed run counting its whole budget.
            # Unlike the success-only mean it cannot make an unreliable configuration look fast.
            budgets=[fnum(r.get('time_limit_s')) for r in rr]
            if times and all(b is not None for b in budgets):
                spent=sum(fnum(r.get(tcol)) if (not bval(r.get(ccol)) and fnum(r.get(tcol)) is not None) else b for r,b in zip(rr,budgets))
                rec[f'{name}_ert_s']=spent/len(times)
            else:
                rec[f'{name}_ert_s']=None
        tb=[fnum(r.get('time_to_best_s')) for r in rr if fnum(r.get('time_to_best_s')) is not None]
        rec['time_to_best_mean_s']=statistics.mean(tb) if tb else None
        rec['time_to_best_median_s']=statistics.median(tb) if tb else None
        trows.append(rec)
    write_csv(root/'time_to_target_summary.csv',trows)

    bad=[r for r in rows if bval(r.get('trace_missing','False')) or not bval(r.get('trace_final_consistent','True'))]
    raw_mismatch=[r for r in rows if not bval(r.get('raw_solver_trace_consistent','True'))]
    write_csv(root/'trace_inconsistencies.csv',bad)
    write_csv(root/'raw_solver_postbudget_mismatches.csv',raw_mismatch)
    print(f'Collected summaries: {len(rows)}')
    print(f'Collected trajectory events: {len(traj)}')
    print(f'Checkpoint rows: {len(long)}')
    print(f'Trace/final inconsistencies: {len(bad)}')
    print(f'Raw solver/post-budget mismatches: {len(raw_mismatch)}')
    noinc=sum(r['status']!='ok' for r in rows)
    print(f'Runs without a reportable incumbent: {noinc}  (see run_status_summary.csv)')
    print(f'Distinct configurations: {len(registry)}  (config_registry.csv)')
    if legacy: print(f'WARNING: {legacy} rows have no config_id (older kit); grouped as legacy')
    if mixed: print(f'WARNING: {len(mixed)} method(s) occur with more than one configuration (different code, budget or parameters); they are kept apart')
    print(f'Duplicate records: {len(dup)}  (duplicates.csv)')
    print(out)
    print(root/'checkpoint_long.csv')
    print(root/'anytime_method_summary.csv')
    print(root/'time_to_target_summary.csv')
    print(root/'trajectories.csv')
    if dup and not a.allow_duplicates:
        print('ERROR: duplicate (instance, seed, configuration) records; remove the stale folder or pass --allow-duplicates')
        raise SystemExit(3)


if __name__=='__main__':
    main()
