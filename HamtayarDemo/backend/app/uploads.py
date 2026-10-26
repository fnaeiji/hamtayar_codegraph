"""Streaming archive transport, separate from background archive processing."""
import hashlib
import shutil
from pathlib import Path
from uuid import uuid4
import anyio
from fastapi import HTTPException, Request
from . import store
from .config import MAX_UPLOAD, RUNTIME

async def receive(request: Request, filename: str):
    if Path(filename).suffix.lower() not in ('.zip', '.rar'):
        raise HTTPException(415, 'Select a ZIP or RAR archive')
    length = request.headers.get('content-length')
    if length is not None:
        try:
            size = int(length)
        except ValueError:
            raise HTTPException(400, 'Invalid Content-Length')
        if size < 0:
            raise HTTPException(400, 'Invalid Content-Length')
        if size > MAX_UPLOAD:
            raise HTTPException(413, f'Archive exceeds upload limit ({MAX_UPLOAD // 1024**2} MB)')
    pid = uuid4().hex
    workspace = RUNTIME/'workspaces'/pid
    workspace.mkdir(parents=True)
    digest, size = hashlib.sha256(), 0
    try:
        async with await anyio.open_file(workspace/'upload.archive', 'wb') as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, f'Archive exceeds upload limit ({MAX_UPLOAD // 1024**2} MB)')
                digest.update(chunk)
                await out.write(chunk)
        if not size:
            raise HTTPException(400, 'Archive is empty')
        project = {'id':pid,'name':Path(filename).stem[:100],'status':'archive_queued',
                   'source_type':'archive','source_version':digest.hexdigest(),
                   'upload_bytes':size,'created_at':store.now(),'files':[],'logs':[],
                   'active_index':None}
        store.save(project)
        return project
    except BaseException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise

def public_project(project):
    # Never send the full manifest and full logs on each polling request.
    files = project.get('files', [])
    return {**project,'files':files[:500],'files_total':len(files),
            'accepted_files':sum(not f['excluded'] for f in files),
            'manifest_truncated':len(files)>500,'logs':project.get('logs',[])[-200:]}
