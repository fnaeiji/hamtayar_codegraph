"""CGC child-process bridge. Only stdlib imports until the isolated profile is set.

Uses the inspected CGC indexing API, bypassing CLI's file-count-only success guard.
All runtime instrumentation is local to this subprocess; upstream files are untouched.
"""
import asyncio
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

class Monitor:
    def __init__(self, report):
        self.report=report; self.lock=threading.RLock(); self.active={}; self.counts={}; self.slow=[]
        self.started=time.monotonic(); self.stop=threading.Event(); self.on_update=None
    def wrap(self, name, function, path_arg=None):
        def wrapped(*args, **kwargs):
            path=''
            if path_arg is not None:
                item=args[path_arg]
                path=str(item.get('path','')) if isinstance(item,dict) else str(item)
            token=object(); started=time.monotonic()
            with self.lock: self.active[token]=(name,path,started)
            try: return function(*args,**kwargs)
            finally:
                elapsed=time.monotonic()-started
                with self.lock:
                    self.active.pop(token,None); self.counts[name]=self.counts.get(name,0)+1
                    self.slow=sorted(self.slow+[{'stage':name,'path':path,'seconds':round(elapsed,2)}],key=lambda x:x['seconds'],reverse=True)[:20]
        return wrapped
    def snapshot(self):
        with self.lock:
            return {'elapsed_seconds':round(time.monotonic()-self.started,1),'completed_operations':dict(self.counts),
                    'active':[{'stage':n,'path':p,'seconds':round(time.monotonic()-t,1)} for n,p,t in self.active.values()], 'slowest':list(self.slow)}
    def heartbeat(self):
        while not self.stop.wait(10):
            status=self.snapshot()
            if self.on_update: self.on_update()
            status.pop('slowest',None)
            print('[Hamtayar progress] '+json.dumps(status,ensure_ascii=True),flush=True)

def main():
    root=Path(sys.argv[1]).resolve(); policy=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    report_path=Path(sys.argv[3]); report={'outcome':'running','selected':[],'skipped':[]}
    Path.home=classmethod(lambda cls:Path(os.environ['HAMTAYAR_CGC_PROFILE']))
    # This file runs in CGC's interpreter; index_policy stays dependency-free here.
    import fnmatch
    def excluded(relative,size):
        for pattern in policy['patterns']:
            candidate=relative if '/' in pattern else Path(relative).name
            if fnmatch.fnmatchcase(candidate.casefold(),pattern.casefold()): return 'INDEX_EXCLUDE_GLOBS: '+pattern
        if policy['max_bytes'] and size>policy['max_bytes']: return 'INDEX_MAX_FILE_MB'
        return None
    heartbeat=None
    monitor=Monitor(report)
    def save():
        report['performance']=monitor.snapshot()
        with monitor.lock:
            temp=report_path.with_suffix('.tmp'); temp.write_text(json.dumps(report,ensure_ascii=True),encoding='utf-8');temp.replace(report_path)
    monitor.on_update=save
    try:
        from codegraphcontext.tools.indexing import discovery, pipeline
        from codegraphcontext.tools.indexing.persistence.writer import GraphWriter
        from codegraphcontext.tools.graph_builder import GraphBuilder
        from codegraphcontext.cli.cli_helpers import _initialize_services, _run_index_with_progress
        original=discovery.discover_files_to_index
        def discover(*args,**kwargs):
            files,ignore_root=original(*args,**kwargs); chosen=[]; skipped=[]
            for file in files:
                relative=file.resolve().relative_to(root).as_posix();size=file.stat().st_size
                reason=excluded(relative,size)
                if reason: skipped.append({'path':relative,'size':size,'reason':reason})
                else: chosen.append(file)
            report['selected']=[f.resolve().as_posix() for f in chosen];report['skipped']=skipped;save()
            print(f'[Hamtayar scope] {len(chosen)} CGC files selected; {len(skipped)} excluded from analysis. See indexing report.',flush=True)
            if not chosen: raise ValueError('No files remain in the indexing scope')
            return chosen,ignore_root
        discovery.discover_files_to_index=discover
        pipeline.discover_files_to_index=discover
        pipeline.pre_scan_for_imports=monitor.wrap('pre_scan',pipeline.pre_scan_for_imports)
        pipeline.build_function_call_groups=monitor.wrap('resolve_calls',pipeline.build_function_call_groups)
        original_parse=GraphBuilder.parse_file
        def checked_parse(*args,**kwargs):
            result=original_parse(*args,**kwargs)
            if result.get('unsupported') or result.get('parse_failed'):
                # CGC can count unavailable parsers as successful minimal-file handling.
                with monitor.lock:
                    report.setdefault('unparsed',[]).append({'path':str(args[2]),'reason':'parser unavailable or parse failed'})
            return result
        GraphBuilder.parse_file=monitor.wrap('parse',checked_parse,2)
        # Observe every writer stage, including post-processing, without logging query data.
        for name in dir(GraphWriter):
            if name=='add_file_to_graph' or name.startswith('write_') or name=='repair_missing_contains_links':
                function=getattr(GraphWriter,name)
                if callable(function): setattr(GraphWriter,name,monitor.wrap(name,function,1 if name=='add_file_to_graph' else None))
        logging.basicConfig(level=logging.WARNING,format='%(levelname)s %(message)s')
        logging.getLogger('codegraphcontext').setLevel(logging.INFO)
        print('[Hamtayar] CGC '+importlib.metadata.version('codegraphcontext')+'; full selected-scope pass (not missing-files-only resume).',flush=True)
        heartbeat=threading.Thread(target=monitor.heartbeat,daemon=True);heartbeat.start()
        db=None
        try:
            db,builder,finder,context=_initialize_services(cwd=root)
            if not all((db,builder,finder)): raise RuntimeError('CGC initialization failed')
            asyncio.run(_run_index_with_progress(builder,root,cgcignore_path=context.cgcignore_path,disable_progress=True))
            summary=getattr(builder,'last_index_summary',None)
            report['summary']=summary
            if not isinstance(summary,dict) or not summary:
                raise RuntimeError('CGC did not provide a completion summary; unsupported CGC version or incomplete indexing')
            if report.get('unparsed') or summary.get('failed_files',0): raise RuntimeError('Some CGC files failed; graph will not be published. Inspect CGC logs.')
            report['outcome']='completed'
        finally:
            if db: db.close_driver()
    except Exception as exc:
        # Deliberately omit exception strings (may contain credentials or query text).
        report['outcome']='failed'; report['error_type']=type(exc).__name__
        report['hint']='Check parser availability, CGC API compatibility and preceding logs; incomplete output is not published.'
        print(f'[Hamtayar] Index pipeline failed ({type(exc).__name__}); see preceding sanitized logs and report.',flush=True)
        raise SystemExit(1)
    finally:
        monitor.stop.set()
        if heartbeat: heartbeat.join()
        save()
        print('[Hamtayar timing] '+json.dumps(report['performance'],ensure_ascii=True),flush=True)

if __name__=='__main__': main()
