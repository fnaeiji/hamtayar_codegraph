"""RAR metadata/stream reader; external tools never choose output paths."""
import os
from pathlib import Path
from threading import RLock
import rarfile
from .config import setting

LOCK = RLock()
MISSING_DECODER = ('RAR decompression requires UnRAR or 7-Zip. Install one, then configure '
                   'RAR_UNRAR_TOOL or RAR_7ZIP_TOOL in Settings (for example C:/Program Files/7-Zip/7z.exe).')

def configure():
    # rarfile 4.5 is pinned: its tool settings live at module scope.
    program_files = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
    unrar = setting('RAR_UNRAR_TOOL')
    sevenzip = setting('RAR_7ZIP_TOOL')
    if not unrar and (program_files/'WinRAR'/'UnRAR.exe').is_file():
        unrar = str(program_files/'WinRAR'/'UnRAR.exe')
    if not sevenzip and (program_files/'7-Zip'/'7z.exe').is_file():
        sevenzip = str(program_files/'7-Zip'/'7z.exe')
    rarfile.UNRAR_TOOL = unrar or 'unrar'
    rarfile.SEVENZIP_TOOL = sevenzip or '7z'
    rarfile.SEVENZIP2_TOOL = '7zz'
    try:
        tool = rarfile.tool_setup(unar=False, bsdtar=False, force=True)
        return {'available': True, 'tool': str(tool.get_cmdline('check_cmd', None)[0])}
    except rarfile.RarCannotExec:
        # Stored entries can still be read in pure Python. Compressed entries
        # receive the actionable error below rather than a server error.
        return {'available': False, 'error': MISSING_DECODER}

def diagnostics():
    with LOCK:
        return configure()

def read_rar(path, target, consume):
    with LOCK:
        decoder = configure()
        try:
            with rarfile.RarFile(path, errors='strict') as archive:
                if archive.needs_password():
                    raise ValueError('Password-protected RAR archives are not supported')
                entries = archive.infolist()
                if len(archive.volumelist()) != 1:
                    raise ValueError('Multi-volume RAR archives are not supported; upload a single complete archive')
                # Preflight links, encryption, volumes and path/size metadata
                # before any decompressor is allowed to read an entry.
                for entry in entries:
                    if (entry.is_symlink() or getattr(entry, 'file_redir', None) or
                            (not entry.is_dir() and not entry.is_file())):
                        raise ValueError('Links and special RAR entries are not supported')
                    if entry.needs_password():
                        raise ValueError('Password-protected RAR archives are not supported')
                    if entry.volume or entry.flags & (rarfile.RAR_FILE_SPLIT_BEFORE | rarfile.RAR_FILE_SPLIT_AFTER):
                        raise ValueError('Multi-volume RAR archives are not supported; upload a single complete archive')
                    if not entry.is_dir() and entry.compress_type != rarfile.RAR_M0 and not decoder['available']:
                        raise ValueError(MISSING_DECODER)
                return consume(entries, lambda e: archive.open(e), target)
        except (rarfile.PasswordRequired, rarfile.RarWrongPassword) as exc:
            raise ValueError('Password-protected RAR archives are not supported') from exc
        except (rarfile.NeedFirstVolume, rarfile.NoRarEntry) as exc:
            raise ValueError('Incomplete or multi-volume RAR archive; upload a single complete archive') from exc
        except rarfile.RarCannotExec as exc:
            raise ValueError(MISSING_DECODER) from exc
        except rarfile.Error as exc:
            raise ValueError('Invalid, corrupted or unsupported RAR archive') from exc
