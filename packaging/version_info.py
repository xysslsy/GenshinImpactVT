"""Generate Windows resource metadata from the application's version module."""
from pathlib import Path
import runpy


def write_version_info(root):
    root=Path(root);v=runpy.run_path(str(root/'genshinimpactvt'/'version.py'))
    target=root/'.build'/'version-info.txt';target.parent.mkdir(parents=True,exist_ok=True)
    fields={'FileDescription':v['APP_TITLE'],'FileVersion':v['__version__'],
            'ProductName':v['APP_NAME'],'ProductVersion':v['DISPLAY_VERSION'],
            'InternalName':v['APP_NAME'],'OriginalFilename':v['APP_NAME']+'.exe'}
    strings=',\n'.join('StringStruct('+repr(key)+', '+repr(value)+')' for key,value in fields.items())
    content=f'''VSVersionInfo(
ffi=FixedFileInfo(filevers={v['WINDOWS_VERSION']!r},prodvers={v['WINDOWS_VERSION']!r},
mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),
kids=[StringFileInfo([StringTable('040904B0',[{strings}])]),
VarFileInfo([VarStruct('Translation',[1033,1200])])])
'''
    target.write_text(content,encoding='utf-8');return str(target)
