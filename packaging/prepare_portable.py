"""Assemble a fresh portable release, including the standalone uninstaller.

Never overwrites an existing release directory and never packages user profiles.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from genshinimpactvt.version import APP_NAME,DISPLAY_VERSION
from genshinimpactvt.uninstaller import MARKER,digest,load_install


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dist',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=args.dist.resolve();helper=args.helper.resolve();output=args.output.absolute()
    if not (source/(APP_NAME+'.exe')).is_file() or not helper.is_file():
        parser.error('Build the application and Uninstall.exe first.')
    forbidden={'settings.ini','library.sqlite3','cookies','browser-profile','ebwebview','.git','.venv'}
    for path in source.rglob('*'):
        if any(part.lower() in forbidden for part in path.relative_to(source).parts):
            parser.error('Private/development data found in build output: '+str(path))
        if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:
            parser.error('Build output contains a symlink/junction.')
    output.mkdir(parents=True,exist_ok=False)
    app=output/APP_NAME
    shutil.copytree(source,app)
    shutil.copy2(helper,app/'Uninstall.exe')
    shutil.copy2(ROOT/'packaging/PORTABLE_README.md',app/'README.md')
    shutil.copy2(ROOT/'LICENSE',app/'LICENSE')
    files={path.relative_to(app).as_posix():digest(path) for path in sorted(app.rglob('*')) if path.is_file()}
    manifest={'schema':1,'product':APP_NAME,'version':DISPLAY_VERSION,'files':files}
    (app/MARKER).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    load_install(app)
    shutil.copy2(app/'README.md',output/'README.md')
    package=output/f'{APP_NAME}-{DISPLAY_VERSION}-windows-x64.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(app.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(output).as_posix())
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
    sha=digest(package)
    record={'version':DISPLAY_VERSION,'file':DISPLAY_VERSION+'/'+package.name,
            'description':'Player-response subtitle provenance; remove unrelated legacy caption fallback',
            'sha256':sha,'size_bytes':package.stat().st_size,'local_available':True,
            'download_url':f'https://github.com/xysslsy/GenshinImpactVT/releases/download/{DISPLAY_VERSION}/{package.name}'}
    (output/'release-record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(sha+'  '+package.name+'\n',encoding='utf-8')
    print(json.dumps(record),flush=True)


if __name__=='__main__':main()
