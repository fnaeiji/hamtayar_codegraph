import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from . import graph, store
from .cgc import CGCAdapter
from .config import RUNTIME, setting

class Jobs:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.lock=threading.RLock()
        self.cancelled={}
    def recover(self):
        for p in store.all_projects():
            if p['status'] in ('queued','indexing','validating_graph'):
                store.update(p['id'],status='interrupted',error='Application stopped before publication')
    def submit(self,pid):
        with self.lock:
            p=store.get(pid)
            if p['status'] in ('queued','indexing','validating_graph'):
                raise ValueError('This project already has a running job')
            event=threading.Event();self.cancelled[pid]=event
            job=uuid4().hex
            store.update(pid,status='queued',job=job,logs=[],error=None,started_at=store.now())
            self.pool.submit(self.run,pid,job,event)
    def cancel(self,pid):
        with self.lock:
            if pid not in self.cancelled:
                raise ValueError('No running job')
            self.cancelled[pid].set()
    def run(self,pid,job,event):
        def log(line):
            with store.LOCK:
                p=store.get(pid)
                store.update(pid,logs=(p.get('logs',[])+[line])[-1000:])
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
            graph.query('RETURN 1 AS ok',True)
            store.update(pid,status='indexing')
            workspace=RUNTIME/'workspaces'/pid/'source'
            CGCAdapter().index(workspace,job,event,log)
            if event.is_set():
                raise ValueError('Cancelled')
            store.update(pid,status='validating_graph')
            counts=graph.publish(pid,job,workspace)
            if event.is_set():
                raise ValueError('Cancelled')
            store.update(pid,status='ready',active_index=job,counts=counts,finished_at=store.now())
        except Exception as e:
            # Keep driver messages/credentials out of API errors.
            error=str(e) if isinstance(e,ValueError) else f'{type(e).__name__}: connection or processing failed; check local configuration'
            store.update(pid,status='cancelled' if event.is_set() else 'failed',error=error,finished_at=store.now())
        finally:
            with self.lock:
                self.cancelled.pop(pid,None)

jobs=Jobs()
