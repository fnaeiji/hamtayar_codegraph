import os
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.environ.get('HAMTAYAR_RUNTIME', ROOT / 'runtime')).resolve()
RUNTIME.mkdir(parents=True, exist_ok=True)
# Never mutate CGC's global file. Local environment wins over inherited defaults.
values = {**dotenv_values(Path.home() / '.codegraphcontext' / '.env'), **dotenv_values(ROOT / '.env'), **os.environ}
def setting(key, default=''):
    return str(values.get(key) or default)
CGC = setting('CGC_EXECUTABLE', str(ROOT.parent / 'CodeGraphContext' / '.venv' / ('Scripts/cgc.exe' if os.name == 'nt' else 'bin/cgc')))
MAX_UPLOAD = int(setting('MAX_UPLOAD_MB', '1024')) * 1024**2
MAX_EXPANDED = int(setting('MAX_EXPANDED_MB', '8192')) * 1024**2
MAX_FILES = int(setting('MAX_ARCHIVE_FILES', '250000'))
MAX_FILE = int(setting('MAX_SOURCE_FILE_MB', '25')) * 1024**2
