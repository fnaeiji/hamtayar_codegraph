import hashlib
import stat
import zipfile
from pathlib import Path, PureWindowsPath
from .config import MAX_EXPANDED, MAX_FILES, MAX_FILE

EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', 'vendor', 'dist', 'build', '__pycache__'}
LANGUAGES = {'.py':'python','.ts':'typescript','.tsx':'tsx','.js':'javascript','.java':'java','.cs':'c_sharp','.go':'go','.rs':'rust','.cpp':'cpp','.c':'c','.php':'php','.rb':'ruby'}
def unpack(archive: Path, target: Path):
    target.mkdir(parents=True, exist_ok=False)
    files, seen, total = [], set(), 0
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > MAX_FILES:
            raise ValueError('Archive contains too many entries')
        for item in z.infolist():
            name = item.filename.replace('\\', '/')
            parts = name.rstrip('/').split('/')
            if (name.startswith('/') or PureWindowsPath(name).drive or
                any(p in ('', '.', '..') or ':' in p or p.endswith((' ', '.')) or
                    p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for p in parts)):
                raise ValueError('Unsafe archive path')
            key = name.rstrip('/').casefold()
            if key in seen:
                raise ValueError('Duplicate or case-conflicting archive entries')
            seen.add(key)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or item.flag_bits & 1:
                raise ValueError('Links and encrypted entries are not supported')
            total += item.file_size
            if total > MAX_EXPANDED or item.file_size > MAX_FILE:
                raise ValueError('Archive extraction limit exceeded')
            if item.is_dir():
                continue
            reason = 'excluded directory' if any(p in EXCLUDED for p in parts) else None
            if reason:
                files.append({'path':name,'excluded':True,'reason':reason})
                continue
            dest = target.joinpath(*parts)
            if not dest.resolve().is_relative_to(target.resolve()):
                raise ValueError('Unsafe destination')
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = z.read(item)  # size already bounded; CRC failures propagate
            if len(data) > MAX_FILE or b'\0' in data:
                files.append({'path':name,'excluded':True,'reason':'binary file'})
                continue
            try:
                data.decode('utf-8')
            except UnicodeDecodeError:
                files.append({'path':name,'excluded':True,'reason':'non UTF-8'})
                continue
            dest.write_bytes(data)
            files.append({'path':name,'excluded':False,'size':len(data),'language':LANGUAGES.get(dest.suffix),'hash':hashlib.sha256(data).hexdigest()})
    if not any(not f['excluded'] for f in files):
        raise ValueError('No readable source files found')
    return files

def source(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Source path is outside this version or missing')
    if p.stat().st_size > MAX_FILE:
        raise ValueError('Source file exceeds limit')
    return p.read_text(encoding='utf-8')
