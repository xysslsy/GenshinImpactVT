# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH).parent
a = Analysis([str(root/'uninstall.py')], pathex=[str(root)], binaries=[], datas=[],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PySide6','pythonnet','clr_loader','psutil','numpy','cv2','onnxruntime'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='Uninstall',debug=False,
          bootloader_ignore_signals=False,strip=False,upx=False,console=False,
          uac_admin=True,icon=[str(root/'assets/app.ico')])
