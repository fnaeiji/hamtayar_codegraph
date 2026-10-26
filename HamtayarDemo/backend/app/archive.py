import hashlib
import stat
import zipfile
from pathlib import Path, PureWindowsPath
from .config import MAX_EXPANDED, MAX_FILES, MAX_FILE

EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', 'vendor', 'dist', 'build', '__pycache__'}
LANGUAGES = {'.py':'python','.ts':'typescript','.tsx':'tsx','.js':'javascript','.java':'java','.cs':'c_sharp','.go':'go','.rs':'rust','.cpp':'cpp','.c':'c','.php':'php','.rb':'ruby'}

def detect_format(path):
    with path.open('rb') as stream:
        magic = stream.read(8)
    if magic.startswith((b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')):
        return 'rar'
    if zipfile.is_zipfile(path):
        return 'zip'
    raise ValueError('Invalid or unsupported archive; upload a ZIP or RAR file')

def _consume(entries, opener, target, cancelled=None, progress=None):
    if len(entries) > MAX_FILES:
        raise ValueError('Archive contains too many entries')
    plan, seen, declared = [], set(), 0
    for item in entries:
        if cancelled is not None and cancelled.is_set():
            raise ValueError('Cancelled')
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
        size = item.file_size
        declared += size
        if size < 0 or declared > MAX_EXPANDED or size > MAX_FILE:
            raise ValueError('Archive extraction limit exceeded')
        dest = target.joinpath(*parts)
        if not dest.resolve().is_relative_to(target.resolve()):
            raise ValueError('Unsafe destination')
        plan.append((item, name, parts, dest))
    # All path and declared-size checks finish before any member is opened.
    files, actual = [], 0
    for number, (item, name, parts, dest) in enumerate(plan, 1):
        if cancelled is not None and cancelled.is_set():
            raise ValueError('Cancelled')
        if progress:
            progress(number, len(plan))
        if item.is_dir():
            continue
        if any(p in EXCLUDED for p in parts):
            files.append({'path':name,'excluded':True,'reason':'excluded directory'})
            continue
        with opener(item) as stream:
            data = stream.read(min(MAX_FILE, MAX_EXPANDED-actual) + 1)
        actual += len(data)
        if len(data) > MAX_FILE or actual > MAX_EXPANDED:
            raise ValueError('Archive extraction limit exceeded')
        if len(data) != item.file_size:
            raise ValueError('Archive entry size does not match its header')
        if b'\0' in data:
            files.append({'path':name,'excluded':True,'reason':'binary file'})
            continue
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            files.append({'path':name,'excluded':True,'reason':'non UTF-8'})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        files.append({'path':name,'excluded':False,'size':len(data),'language':LANGUAGES.get(dest.suffix),'hash':hashlib.sha256(data).hexdigest()})
    if not any(not f['excluded'] for f in files):
        raise ValueError('No readable source files found')
    return files

def unpack(path: Path, target: Path, cancelled=None, progress=None):
    kind = detect_format(path)
    target.mkdir(parents=True, exist_ok=False)
    if kind == 'rar':
        from .rar_support import read_rar
        return read_rar(path, target, lambda entries, opener, dest: _consume(entries, opener, dest, cancelled, progress))
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        for item in entries:
            if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                raise ValueError('Links and encrypted entries are not supported')
        return _consume(entries, lambda e: archive.open(e), target, cancelled, progress)

def source(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Source path is outside this version or missing')
    if p.stat().st_size > MAX_FILE:
        raise ValueError('Source file exceeds limit')
    return p.read_text(encoding='utf-8')
