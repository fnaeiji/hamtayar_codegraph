"""Explicit, inspectable indexing scope, independent of archive extraction."""
import fnmatch
import math
from pathlib import PurePosixPath
from .config import setting

def settings():
    try:
        size = float(setting('INDEX_MAX_FILE_MB', '2'))
        workers = int(setting('INDEX_PARALLEL_WORKERS', '2'))
        timeout = int(setting('INDEX_TIMEOUT_SECONDS', '7200'))
    except ValueError:
        raise ValueError('Index limits must be numeric') from None
    if not math.isfinite(size) or not 0 <= size <= 25 or not 1 <= workers <= 8 or not 60 <= timeout <= 86400:
        raise ValueError('Index limits: file MB 0..25 (0 disables this filter), workers 1..8, timeout 60..86400 seconds')
    return {'max_bytes':int(size*1024**2), 'workers':workers, 'timeout':timeout,
            'patterns':[p.strip() for p in setting('INDEX_EXCLUDE_GLOBS','*.min.js,*.min.css,*.map').split(',') if p.strip() and p.strip()!='-']}

def exclusion(path, size, policy):
    path=path.replace('\\','/')
    for pattern in policy['patterns']:
        candidate = path if '/' in pattern else PurePosixPath(path).name
        if fnmatch.fnmatchcase(candidate.casefold(),pattern.casefold()):
            return 'INDEX_EXCLUDE_GLOBS: '+pattern
    if policy['max_bytes'] and size > policy['max_bytes']:
        return f'INDEX_MAX_FILE_MB: {size:,} bytes exceeds {policy["max_bytes"]:,}'
    return None

def preview(files):
    policy=settings(); skipped=[]; selected=[]
    for f in files:
        if f['excluded']: continue
        row={'path':f['path'],'size':f.get('size',0)}
        reason=exclusion(row['path'],row['size'],policy)
        if reason: skipped.append({**row,'reason':reason})
        else: selected.append(row)
    return {'policy':policy,'eligible_files':len(selected),'skipped_count':len(skipped),
            'skipped':skipped[:100],'largest':sorted(selected,key=lambda f:f['size'],reverse=True)[:20],
            'note':'Preflight candidates; CGC language and ignore rules also apply. Skipped files are not analyzed.'}
