import json
import sqlite3
import threading
from datetime import datetime, timezone
from .config import RUNTIME

LOCK = threading.RLock()
def now():
    return datetime.now(timezone.utc).isoformat()
def connect():
    c = sqlite3.connect(RUNTIME / 'metadata.sqlite3', timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    return c
def all_projects():
    with LOCK, connect() as c:
        return [json.loads(r[0]) for r in c.execute('SELECT data FROM projects ORDER BY rowid DESC')]
def get(pid):
    with LOCK, connect() as c:
        row = c.execute('SELECT data FROM projects WHERE id=?', (pid,)).fetchone()
        if not row:
            raise KeyError('Project not found')
        return json.loads(row[0])
def save(p):
    with LOCK, connect() as c:
        c.execute('INSERT INTO projects VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (p['id'], json.dumps(p)))
def update(pid, **fields):
    with LOCK:
        p = get(pid)
        p.update(fields)
        save(p)
        return p
