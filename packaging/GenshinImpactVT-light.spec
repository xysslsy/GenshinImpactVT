# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy
from PyInstaller.utils.hooks import collect_all

root=Path(SPECPATH).parent
version_file=runpy.run_path(str(root/'packaging'/'version_info.py'))['write_version_info'](root)
flavor=root/'.build'/'light-flavor';flavor.mkdir(parents=True,exist_ok=True)
(flavor/'lightweight.flag').write_text('Bilibili timed captions; no local inference\n',encoding='utf-8')
datas=[(str(root/'fixture.html'),'.'),(str(root/'genshinimpactvt'/'caption_recovery.js'),'genshinimpactvt'),(str(root/'assets'),'assets'),
       (str(root/'.deps'/'webview2'),'.deps/webview2'),(str(flavor/'lightweight.flag'),'assets')]
binaries,hiddenimports=[],[]
for package in ('pythonnet','clr_loader'):
    data,binary,hidden=collect_all(package)
    datas+=data;binaries+=binary;hiddenimports+=hidden
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
           hiddenimports=hiddenimports,hookspath=[],hooksconfig={},runtime_hooks=[],
           excludes=['rapidocr','onnxruntime','numpy','cv2','PIL','shapely','omegaconf',
                     'torch','paddle','openvino','tensorrt','matplotlib','tkinter'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='GenshinImpactVT',debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False,
        uac_admin=True,icon=[str(root/'assets'/'app.ico')],version=version_file)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='GenshinImpactVT')
