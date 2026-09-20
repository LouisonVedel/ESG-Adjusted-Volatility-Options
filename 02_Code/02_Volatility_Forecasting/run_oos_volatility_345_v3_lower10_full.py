import pandas as pd, numpy as np, warnings, sys, time, json, traceback
from pathlib import Path
from arch import arch_model
import statsmodels.api as sm
warnings.filterwarnings('ignore')

ROOT=Path(r'C:\ThesisRebuild')
RET=ROOT/'05_Returns'/'returns_log_pct_345_wide.csv'
ESG=ROOT/'00_Master'/'esg_annual_404_2010_2019.csv'
ALIGN=ROOT/'00_Master'/'oos_alignment_345.csv'
OUT=ROOT/'03_Volatility_OOS_LOWER10_FULL'
BLOCKS=OUT/'blocks'; LOGS=OUT/'logs'; FINAL=OUT/'final'
for p in (OUT,BLOCKS,LOGS,FINAL): p.mkdir(exist_ok=True)
PROGRESS=OUT/'progress_v3_resume.json'; ERRORS=LOGS/'errors.csv'; RUNLOG=LOGS/'oos_run.log'
REFIT=21; BLOCK_SIZE=10; END_DATE='2019-06-28'
COLS=['ticker','RIC','Date','model','forecast_vol','forecast_var_pct2','esg_spec','refit_date']

def log(msg):
    s=f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(s,flush=True)
    with open(RUNLOG,'a',encoding='utf-8') as f: f.write(s+'\n')

def save_progress(done, total, current=None, block=None, started=None):
    data={'total':total,'completed':sorted(done),'completed_count':len(done),'current':current,'block':block,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'started_at':started}
    tmp=PROGRESS.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(data,indent=2),encoding='utf-8'); tmp.replace(PROGRESS)
    except PermissionError:
        fallback=PROGRESS.with_name(PROGRESS.stem+'_fallback.json')
        fallback.write_text(json.dumps(data,indent=2),encoding='utf-8')

def load_progress():
    completed=set()
    for p in (PROGRESS, PROGRESS.with_name(PROGRESS.stem+'_fallback.json')):
        if p.exists():
            try: completed.update(json.loads(p.read_text(encoding='utf-8')).get('completed',[]))
            except Exception: pass
    return completed

def fit_base(y,family):
    vol='EGARCH' if family=='EGARCH' else 'GARCH'; o=1 if family=='GJR' else 0
    if family!='EGARCH':
        f=arch_model(y,mean='Constant',vol=vol,p=1,o=o,q=1,dist='normal',rescale=False).fit(disp='off',options={'maxiter':1000})
        if getattr(f,'convergence_flag',0)!=0: raise RuntimeError(f'non-converged {family}: {f.convergence_flag}')
        return f
    starts=((0,-0.1,0.1,0.95),(0,0,0.05,0.98),(0,0.01,0.1,0.99),(0,0,0.2,0.9),(0,0.1,-0.05,0.99))
    candidates=[]
    for start in starts:
        try:
            f=arch_model(y,mean='Constant',vol='EGARCH',p=1,o=0,q=1,dist='normal',rescale=False).fit(starting_values=np.array(start,float),disp='off',options={'maxiter':2000})
            pp=f.params
            sane=(getattr(f,'convergence_flag',0)==0 and np.isfinite(f.loglikelihood)
                  and abs(float(pp.get('alpha[1]',np.nan)))<=2
                  and -10<=float(pp.get('omega',np.nan))<=10
                  and 0<float(pp.get('beta[1]',np.nan))<1.05)
            if sane: candidates.append(f)
        except Exception:
            pass
    if not candidates: raise RuntimeError('non-converged EGARCH: no admissible multi-start solution')
    return max(candidates,key=lambda f: float(f.loglikelihood))

def one_var(f,family):
    if family!='EGARCH': return float(f.forecast(horizon=1,reindex=False).variance.values[-1,0])
    p=f.params; sig=float(f.conditional_volatility.iloc[-1]); z=float(f.resid.iloc[-1])/max(sig,1e-12)
    lv=float(p['omega'])+float(p['beta[1]'])*np.log(max(sig*sig,1e-12))
    lv+=float(p['alpha[1]'])*(abs(z)-np.sqrt(2/np.pi))
    if 'gamma[1]' in p.index: lv+=float(p['gamma[1]'])*z
    return float(np.exp(np.clip(lv,-20,20)))

def build_esg(x):
    x=x.copy(); x['Date']=pd.to_datetime(x['Date']); x['year']=x.Date.dt.year+1
    return x.sort_values('Date').drop_duplicates('year',keep='last')

def prepare_esg(esg):
    out={}
    for ticker,g in esg.groupby('ticker',sort=False): out[ticker]=build_esg(g).set_index('year')
    return out

def run_ticker(ticker,ric,start,end,returns,esg_map):
    y=returns[ric].dropna(); y.index=pd.to_datetime(y.index)
    dates=y.index[(y.index>=pd.Timestamp(start))&(y.index<=pd.Timestamp(end))]
    mp=esg_map.get(ticker,pd.DataFrame())
    rows=[]; fits={}; s2={}; last_refit=None; since=REFIT
    fit_failures=0; refits=0
    for d in dates:
        hist=y.loc[y.index<d]
        if len(hist)<252: continue
        if last_refit is None or since>=REFIT:
            new={}
            for k in ('GARCH','GJR','EGARCH'):
                try: new[k]=fit_base(hist,k)
                except Exception as ex:
                    fit_failures+=1; log(f'FIT_FAIL ticker={ticker} date={d.date()} family={k} error={repr(ex)}')
            if new:
                fits=new; s2={}; refits+=1
                for key,fit in fits.items():
                    hv=np.asarray(fit.conditional_volatility)**2
                    tr=pd.DataFrame({'logvar':np.log(np.maximum(hv,1e-12))},index=hist.index)
                    tr['lag_logvar']=tr.logvar.shift(1)
                    if not mp.empty:
                        for c,src in [('E','Environmental Pillar Score'),('S','Social Pillar Score'),('G','Governance Pillar Score')]:
                            tr[c]=tr.index.year.map(mp[src].to_dict())
                    tr=tr.dropna(); regs={}
                    for cv in ('all','E','S','G'):
                        use=['E','S','G'] if cv=='all' else [cv]
                        if not all(c in tr for c in use): continue
                        z=tr[use].astype(float); means=z.mean(); std=z.std(ddof=0).replace(0,1); z=(z-means)/std
                        X=sm.add_constant(pd.concat([tr['lag_logvar'],z],axis=1),has_constant='add')
                        if len(X)>=100: regs[cv]=(sm.OLS(tr.logvar,X).fit(cov_type='HAC',cov_kwds={'maxlags':5}),means,std,X.columns)
                    s2[key]=regs
                last_refit=d; since=0
            else: since+=1
        else: since+=1
        if not fits: continue
        for key,label in (('GARCH','GARCH'),('GJR','GJR-GARCH'),('EGARCH','EGARCH')):
            if key not in fits: continue
            try: base=one_var(fits[key],key)
            except Exception: base=np.nan
            if np.isfinite(base): rows.append([ticker,ric,d,label,np.sqrt(max(base,0)*252)/100,base,None,last_refit])
            for cv,suffix in (('all',''),('E','(E)'),('S','(S)'),('G','(G)')):
                info=s2.get(key,{}).get(cv)
                if not info: continue
                res,means,std,cols=info; use=['E','S','G'] if cv=='all' else [cv]
                row={'lag_logvar':np.log(max(float(fits[key].conditional_volatility.iloc[-1]**2),1e-12))}; good=True
                for c in use:
                    src={'E':'Environmental Pillar Score','S':'Social Pillar Score','G':'Governance Pillar Score'}[c]
                    val=mp[src].get(d.year,np.nan) if not mp.empty else np.nan
                    if pd.isna(val): good=False; break
                    row[c]=(float(val)-means[c])/std[c]
                if not good: continue
                Xf=sm.add_constant(pd.DataFrame([row]),has_constant='add')[cols]
                lv=float(np.asarray(Xf)@np.asarray(res.params)); var=float(np.exp(np.clip(lv,-10,5)))
                fam='ESG-GARCH' if label=='GARCH' else ('ESG-GJR-GARCH' if label=='GJR-GARCH' else 'ESG-EGARCH')
                rows.append([ticker,ric,d,fam+suffix,np.sqrt(var*252)/100,var,cv,last_refit])
    return rows,fit_failures,refits

def write_ticker(path,rows):
    pd.DataFrame(rows,columns=COLS).to_csv(path,index=False)

def log_error(ticker,ric,exc):
    exists=ERRORS.exists();
    with open(ERRORS,'a',encoding='utf-8',newline='') as f:
        if not exists: f.write('timestamp,ticker,RIC,error,traceback\n')
        msg=repr(exc).replace('"','""'); tb=traceback.format_exc().replace('"','""').replace('\n',' | ')
        f.write(f'"{time.strftime("%Y-%m-%d %H:%M:%S")}","{ticker}","{ric}","{msg}","{tb}"\n')

def merge_final(align):
    files=sorted(BLOCKS.glob('block_*/*.csv'))
    frames=[]
    for p in files:
        try: frames.append(pd.read_csv(p,parse_dates=['Date','refit_date']))
        except Exception as ex: log(f'MERGE_SKIP file={p} error={repr(ex)}')
    if not frames: return None
    out=pd.concat(frames,ignore_index=True)
    out=out.sort_values(['ticker','Date','model']).drop_duplicates(['ticker','Date','model'],keep='last')
    target=FINAL/'oos_volatility_345_v3.csv'; tmp=FINAL/'oos_volatility_345_v3.tmp.csv'
    out.to_csv(tmp,index=False); tmp.replace(target)
    return out

def main():
    total_t0=time.time(); started=time.strftime('%Y-%m-%d %H:%M:%S')
    rets=pd.read_csv(RET,parse_dates=['Date']).set_index('Date')
    esg=pd.read_csv(ESG); esg_map=prepare_esg(esg)
    align=pd.read_csv(ALIGN).sort_values('oos_start').reset_index(drop=True)
    total=len(align); done=load_progress()
    log(f'ENGINE v3 START total={total} block_size={BLOCK_SIZE} already_completed={len(done)}')
    save_progress(done,total,started=started)
    for block_start in range(0,total,BLOCK_SIZE):
        block_no=block_start//BLOCK_SIZE+1; block_end=min(block_start+BLOCK_SIZE,total)
        block_dir=BLOCKS/f'block_{block_no:03d}'; block_dir.mkdir(exist_ok=True)
        log(f'BLOCK {block_no:03d}/{int(np.ceil(total/BLOCK_SIZE)):03d} tickers={block_start+1}-{block_end}')
        for pos in range(block_start,block_end):
            r=align.iloc[pos]; ticker=str(r.ticker); ric=str(r.RIC)
            if ticker in done:
                log(f'SKIP {pos+1:03d}/{total} {ticker} already_completed'); continue
            target=block_dir/f'{pos+1:03d}_{ticker}.csv'
            t0=time.time(); save_progress(done,total,current=ticker,block=block_no,started=started)
            log(f'START {pos+1:03d}/{total} ticker={ticker} RIC={ric} oos_start={r.oos_start}')
            try:
                rows,fails,refits=run_ticker(ticker,ric,r.oos_start,END_DATE,rets,esg_map)
                write_ticker(target,rows)
                done.add(ticker); save_progress(done,total,started=started)
                log(f'DONE {pos+1:03d}/{total} ticker={ticker} rows={len(rows)} refits={refits} fit_failures={fails} elapsed={time.time()-t0:.1f}s')
            except Exception as ex:
                log_error(ticker,ric,ex); log(f'ERROR {pos+1:03d}/{total} ticker={ticker} error={repr(ex)} elapsed={time.time()-t0:.1f}s')
                save_progress(done,total,current=None,block=block_no,started=started)
        log(f'BLOCK_DONE {block_no:03d} completed={len(done)}/{total} elapsed={time.time()-total_t0:.1f}s')
    log('ALL TICKERS PROCESSED â€” MERGING FINAL OUTPUT')
    out=merge_final(align)
    if out is not None: log(f'FINAL_DONE shape={out.shape} models={out.model.nunique()} file={FINAL/"oos_volatility_345_v3.csv"}')
    save_progress(done,total,current=None,block=None,started=started)
    log(f'ENGINE v3 END completed={len(done)}/{total} total_elapsed={time.time()-total_t0:.1f}s')

if __name__=='__main__':
    main()


