"""Normalize existing local release snapshots without rewriting old binaries."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HISTORY=(
    ('v0.0','MaBaoNext-便携版.zip','早期开发快照'),
    ('v0.1','GenshinImpactVT-windows-x64.zip','独立浏览器初版，对应公开 v0.1.0'),
    ('v0.2','GenshinImpactVT-OCR-windows-x64.zip','画面 OCR 测试版'),
    ('v0.3','GenshinImpactVT-Light-windows-x64.zip','B站轻量字幕版'),
    ('v0.4','GenshinImpactVT-Ambient-windows-x64.zip','方向氛围光版'),
    ('v1','GenshinImpactVT-v1-windows-x64.zip','实时底部字幕与完整轻量工作台'),
)


def digest(path):
    checksum=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):checksum.update(block)
    return checksum.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--catalog',type=Path);args=parser.parse_args()
    workspace=args.workspace.resolve();release_root=workspace/'releases';release_root.mkdir(exist_ok=True)
    rows=[]
    for version,original,description in HISTORY:
        source=workspace/original
        if not source.is_file():raise FileNotFoundError(source)
        checksum=digest(source);folder=release_root/version;folder.mkdir(exist_ok=True)
        name=f'GenshinImpactVT-{version}-windows-x64.zip';target=folder/name
        if target.exists():
            if digest(target)!=checksum:raise FileExistsError(f'Existing release differs: {target}')
        else:shutil.copy2(source,target)
        if digest(target)!=checksum:raise RuntimeError('Archive copy checksum failed')
        row={'version':version,'file':f'{version}/{name}','original_name':original,
             'description':description,'size_bytes':source.stat().st_size,'sha256':checksum}
        rows.append(row)
        (folder/'README.md').write_text(f'# GenshinImpactVT {version}\n\n{description}。\n\n'
            f'文件：`{name}`\n\nSHA-256：`{checksum}`\n\n'
            '历史包统一外部编号，保留原始包内容。当前推荐使用 v1。\n',encoding='utf-8')
    (release_root/'manifest.json').write_text(json.dumps({'latest':'v1','releases':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    catalog='# 本地发行快照\n\n当前版本 **v1**（内部 1.0.0）。发行包按版本号存放在工作区的 `releases/`。\n\n'
    catalog+='| 版本 | 内容 | 文件 | SHA-256 |\n| --- | --- | --- | --- |\n'
    for row in rows:catalog+=f"| {row['version']} | {row['description']} | `{row['file']}` | `{row['sha256']}` |\n"
    catalog+='\n历史包只规范外部文件名，内部原始二进制、README 及其版本信息保留，以便回退。\n'
    catalog+='\nGitHub 现有 `v0.1.0` 标签对应短号 v0.1，继续保留。v0.2～v0.4 是已有分发快照的编号，未虚构对应源码标签。本次源码按模块整理成真实的新提交，最终标记 v1。\n'
    if args.catalog:args.catalog.write_text(catalog,encoding='utf-8')
    (release_root/'README.md').write_text(catalog,encoding='utf-8')
    print(json.dumps({'latest':'v1','count':len(rows),'root':str(release_root)},ensure_ascii=True))


if __name__=='__main__':main()
