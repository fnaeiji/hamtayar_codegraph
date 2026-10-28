import threading
import time
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from . import archive, graph, store
import shutil
import zipfile
from .cgc import CGCAdapter
from .config import RUNTIME, setting, MAX_EXPANDED, MAX_FILES, MAX_FILE

class Jobs:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.lock=threading.RLock()
        self.cancelled={}
    def recover(self):
        for p in store.all_projects():
            if p['status'] in ('archive_queued','extracting','queued','indexing','validating_graph'):
                store.update(p['id'],status='interrupted',error='Application stopped before publication')
    def submit(self,pid,publish_only=False):
        with self.lock:
            p=store.get(pid)
            if p['status'] in ('archive_queued','extracting','queued','indexing','validating_graph'):
                raise ValueError('This project already has a running job')
            if not p.get('files') or p['status']=='extraction_failed':
                raise ValueError('Wait for successful archive extraction before indexing')
            report_job=None
            if publish_only:
                report_job=p.get('completed_cgc_job') or p.get('job')
                self.completed_report(pid,report_job)
            event=threading.Event();self.cancelled[pid]=event
            job=uuid4().hex
            store.update(pid,status='queued',job=job,completed_cgc_job=report_job,logs=[],error=None,started_at=store.now())
            self.pool.submit(self.run,pid,job,event,report_job)
    def extract(self, pid):
        with self.lock:
            if pid in self.cancelled:
                raise ValueError('Archive processing is already running')
            store.update(pid, status='archive_queued', error=None)
            event = threading.Event()
            self.cancelled[pid] = event
            self.pool.submit(self.extract_archive, pid, event)
    def extract_archive(self, pid, event):
        workspace = RUNTIME/'workspaces'/pid
        try:
            if event.is_set():
                raise ValueError('Cancelled')
            shutil.rmtree(workspace/'source', ignore_errors=True)
            kind = archive.detect_format(workspace/'upload.archive')
            store.update(pid, status='extracting', source_type=kind, processed_files=0,
                         logs=['Archive received. Validating and extracting in background.', f'Limits: selected expanded bytes={MAX_EXPANDED:,}; per-source-file bytes={MAX_FILE:,}; archive entries={MAX_FILES:,}'])
            def progress(done, total):
                if done % 100 == 0 or done == total:
                    store.update(pid, processed_files=done, archive_entries=total)
            files = archive.unpack(workspace/'upload.archive', workspace/'source', event, progress)
            if event.is_set():
                raise ValueError('Cancelled')
            store.update(pid, status='ready_to_index', files=files, error=None,
                         logs=['Archive extraction completed. Ready to index.'])
        except Exception as exc:
            shutil.rmtree(workspace/'source', ignore_errors=True)
            if isinstance(exc, (ValueError, zipfile.BadZipFile)):
                message = str(exc)
            elif isinstance(exc, OSError):
                message = 'Cannot extract archive. Check free disk space and filesystem permissions.'
            else:
                message = f'{type(exc).__name__}: archive processing failed'
            store.update(pid, status='cancelled' if event.is_set() else 'extraction_failed', error=message, logs=store.get(pid).get('logs',[])+['Extraction failed: '+message])
        finally:
            with self.lock:
                self.cancelled.pop(pid, None)
    def cancel(self,pid):
        with self.lock:
            if pid not in self.cancelled:
                raise ValueError('No running job')
            self.cancelled[pid].set()
    def completed_report(self,pid,job):
        path=RUNTIME/'cgc'/str(job)/'report.json'
        if not job or not path.is_file(): raise ValueError('No completed CGC report available; start indexing first')
        report=json.loads(path.read_text(encoding='utf-8'))
        if report.get('outcome')!='completed' or not report.get('selected') or report.get('unparsed') or (report.get('summary') or {}).get('failed_files'):
            raise ValueError('CGC analysis did not complete successfully; run indexing before publication')
        root=(RUNTIME/'workspaces'/pid/'source').resolve()
        from pathlib import Path
        if any(not Path(p).resolve().is_relative_to(root) for p in report['selected']):
            raise ValueError('CGC report does not belong to this project')
        return report
    def run(self,pid,job,event,report_job=None):
        buffer=[]; buffer_lock=threading.RLock(); last_flush=time.monotonic()
        def flush():
            nonlocal last_flush
            with buffer_lock:
                if buffer:
                    with store.LOCK:
                        p=store.get(pid)
                        store.update(pid,logs=(p.get('logs',[])+buffer)[-1000:])
                    buffer.clear()
                last_flush=time.monotonic()
        def log(line):
            with buffer_lock:
                buffer.append(f'[{store.now()}] {line}')
                if len(buffer)>=50 or time.monotonic()-last_flush>=2:
                    flush()
        try:
            if event.is_set():
                raise ValueError('Cancelled')
            # Fail before running CGC unless an explicit isolated staging DB is ready.
            from urllib.parse import urlparse
            a=urlparse(setting('NEO4J_URI','bolt://127.0.0.1:7687'))
            b=urlparse(setting('STAGING_NEO4J_URI','bolt://127.0.0.1:7689'))
            host=lambda h:'loopback' if h in ('localhost','127.0.0.1','::1') else h
            if (host(a.hostname),a.port or 7687)==(host(b.hostname),b.port or 7687):
                raise ValueError('Staging must use a separate Neo4j instance, not the destination')
            for name, staging in [('staging', True), ('destination', False)]:
                log(f'Checking Neo4j {name} connection...')
                graph.query('RETURN 1 AS ok',staging)
                log(f'Neo4j {name}: connection OK')
            workspace=RUNTIME/'workspaces'/pid/'source'
            if report_job:
                log('Reusing completed CGC analysis; no parsing or re-indexing.')
                report=self.completed_report(pid,report_job)
            else:
                store.update(pid,status='indexing')
                report=CGCAdapter().index(workspace,job,event,log)
            store.update(pid,completed_cgc_job=report_job or job)
            if event.is_set():
                raise ValueError('Cancelled')
            store.update(pid,status='validating_graph')
            log('CGC completed. Validating and publishing selected graph to destination...')
            counts=graph.publish(pid,job,workspace,selected_paths=report['selected'],cancelled=event,log=log)
            if event.is_set():
                raise ValueError('Cancelled')
            store.update(pid,status='ready',active_index=job,counts=counts,index_coverage={'selected_files':len(report['selected']),'skipped_files':len(report['skipped'])},finished_at=store.now())
        except Exception as e:
            # Keep driver messages/credentials out of API errors.
            error=str(e) if isinstance(e,ValueError) else f'{type(e).__name__}: connection or processing failed; check local configuration'
            log('Indexing failed: '+error)
            store.update(pid,status='cancelled' if event.is_set() else 'failed',error=error,finished_at=store.now())
        finally:
            flush()
            with self.lock:
                self.cancelled.pop(pid,None)

jobs=Jobs()
