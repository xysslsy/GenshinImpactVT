# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

root = Path(SPECPATH).parent
version_file=runpy.run_path(str(root/'packaging'/'version_info.py'))['write_version_info'](root)
datas = [(str(root/'fixture.html'),'.'), (str(root/'assets'),'assets'),
         (str(root/'.deps'/'webview2'),'.deps/webview2')]
binaries,hiddenimports = [],[]
for package in ('pythonnet','clr_loader'):
    data,binary,hidden = collect_all(package)
    datas += data; binaries += binary; hiddenimports += hidden
datas += collect_data_files('rapidocr')
for package in ('rapidocr','onnxruntime','numpy','opencv-python-headless','Pillow'):
    datas += copy_metadata(package)
hiddenimports += ['rapidocr','rapidocr.inference_engine.onnxruntime','onnxruntime',
                  'multiprocessing','multiprocessing.popen_spawn_win32']
a = Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
             hiddenimports=hiddenimports,hookspath=[],hooksconfig={},runtime_hooks=[],
             excludes=['tkinter','matplotlib','torch','paddle','openvino','tensorrt'],noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='GenshinImpactVT',debug=False,
          bootloader_ignore_signals=False,strip=False,upx=False,console=False,
          uac_admin=True,icon=[str(root/'assets'/'app.ico')],version=version_file)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='GenshinImpactVT')
