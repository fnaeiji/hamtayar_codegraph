import hashlib
import stat
import zipfile
from pathlib import Path, PureWindowsPath
from .config import MAX_EXPANDED, MAX_FILES, MAX_FILE

EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', 'vendor', 'dist', 'build', '__pycache__', '.vs', 'bin', 'obj', 'packages'}
BINARY_SUFFIXES = {'.dll', '.exe', '.pdb', '.so', '.dylib', '.class', '.jar', '.pyc', '.png', '.jpg', '.jpeg', '.gif', '.mp4', '.mp3', '.zip', '.rar', '.7z', '.pdf', '.woff', '.woff2', '.ttf', '.db', '.sqlite3'}

def exclusion_reason(parts, size):
    if any(p.casefold() in EXCLUDED for p in parts):
        return 'excluded dependency/build directory'
    if Path(parts[-1]).suffix.lower() in BINARY_SUFFIXES:
        return 'binary or nested archive extension'
    if size > MAX_FILE:
        return f'file exceeds MAX_SOURCE_FILE_MB: {size:,} bytes > {MAX_FILE:,} bytes; skipped without extraction'
    return None
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
        raise ValueError(f'Archive has {len(entries):,} entries; MAX_ARCHIVE_FILES allows {MAX_FILES:,}. Remove dependencies/build output or adjust this setting and restart.')
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
        if size < 0:
            raise ValueError(f'Invalid declared size for {name}')
        reason = exclusion_reason(parts, size)
        if not item.is_dir() and reason is None:
            declared += size
            if declared > MAX_EXPANDED:
                raise ValueError(f'Selected source exceeds MAX_EXPANDED_MB at {name}: {declared:,} bytes selected, limit {MAX_EXPANDED:,} bytes. Increase MAX_EXPANDED_MB in .env and restart, or reduce the source selection.')
        dest = target.joinpath(*parts)
        if not dest.resolve().is_relative_to(target.resolve()):
            raise ValueError('Unsafe destination')
        plan.append((item, name, dest, reason))
    # All path and declared-size checks finish before any member is opened.
    files, actual = [], 0
    for number, (item, name, dest, reason) in enumerate(plan, 1):
        if cancelled is not None and cancelled.is_set():
            raise ValueError('Cancelled')
        if progress:
            progress(number, len(plan))
        if item.is_dir():
            continue
        if reason:
            files.append({'path':name,'excluded':True,'size':item.file_size,'reason':reason})
            continue
        with opener(item) as stream:
            data = stream.read(min(MAX_FILE, MAX_EXPANDED-actual) + 1)
        actual += len(data)
        if len(data) > MAX_FILE or actual > MAX_EXPANDED:
            raise ValueError(f'Actual decompressed bytes exceed limits while reading {name}: file={len(data):,}/{MAX_FILE:,}, total={actual:,}/{MAX_EXPANDED:,}. Archive content may not match its headers.')
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
        raise ValueError(f'No readable source files remain after filtering. {len(files)} files excluded; check dependency paths, binary types and MAX_SOURCE_FILE_MB ({MAX_FILE:,} bytes).')
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
