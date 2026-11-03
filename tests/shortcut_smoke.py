"""Check launcher wiring without triggering an interactive UAC request."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
launcher = (root / 'launch.vbs').read_text(encoding='utf-8-sig')
assert 'launcher.ShellExecute pythonw' in launcher
assert '"runas"' in launcher
assert (root / 'start.pyw').is_file()
assert (root / 'GenshinImpactVT.lnk').is_file()
print('launcher wiring checked; UAC and elevated startup require manual verification')
