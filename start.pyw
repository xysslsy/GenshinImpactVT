"""No-console entry point with a visible startup error."""
import ctypes
import runpy
import traceback
from pathlib import Path

try:
    runpy.run_path(str(Path(__file__).resolve().with_name('main.py')), run_name='__main__')
except Exception:
    message = traceback.format_exc()
    ctypes.windll.user32.MessageBoxW(None, message[-3000:], 'GenshinImpactVT startup error', 0x10)
