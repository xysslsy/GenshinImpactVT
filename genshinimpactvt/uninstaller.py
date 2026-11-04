"""Portable uninstall: explicit owned files only, optional shared user-data purge.

The standalone helper uses only Python's standard library and Windows APIs.
It never recursively deletes a program directory, source tree or another version.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time

MARKER = '.genshinimpactvt-install.json'
PRODUCT = 'GenshinImpactVT'
EXECUTABLE = PRODUCT+'.exe'
HELPER = 'Uninstall.exe'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def plain_path(path):
    """Reject symlinks/junctions in the target AND all existing ancestors."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('路径包含链接或目录联接，已停止卸载。')
    return path


def load_install(root):
    root = plain_path(root)
    if root == Path(root.anchor) or any((root/name).exists() for name in ('.git', '.venv', 'main.py')):
        raise ValueError('这是源码或系统目录，不能作为便携软件卸载。')
    marker = plain_path(root/MARKER)
    if marker.stat().st_size > 4_000_000:
        raise ValueError('卸载清单大小不正确。')
    manifest = json.loads(marker.read_text(encoding='utf-8'))
    if manifest.get('product') != PRODUCT or manifest.get('schema') != 1:
        raise ValueError('不是 GenshinImpactVT 安装清单。')
    files = manifest.get('files')
    if not isinstance(files, dict) or not 2 <= len(files) <= 20000:
        raise ValueError('程序文件清单无效。')
    if EXECUTABLE not in files or HELPER not in files:
        raise ValueError('清单缺少主程序或卸载程序。')
    for name, sha in files.items():
        relative = PurePosixPath(name)
        if (not name or '\\' in name or ':' in name or relative.is_absolute()
                or any(part in ('', '.', '..') for part in name.split('/')) or name == MARKER
                or not isinstance(sha, str) or len(sha) != 64
                or any(c not in '0123456789abcdef' for c in sha)):
            raise ValueError('清单中有不安全的文件路径或校验值。')
        plain_path(root.joinpath(*relative.parts))
    return root, manifest


def remove_owned_files(root, retry_seconds=12):
    """Return changed/unlisted leftovers without deleting them."""
    root, manifest = load_install(root)
    changed, errors, parents = [], [], set()
    deadline = time.monotonic()+retry_seconds
    for name, expected in manifest['files'].items():
        path = plain_path(root/name)
        if not path.exists():
            continue
        if not path.is_file() or digest(path) != expected:
            changed.append(name)
            continue
        while True:
            try:
                plain_path(path)
                path.unlink()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    errors.append(name)
                    break
                time.sleep(.25)
        parents.update(p for p in path.parents if p != root and root in p.parents)
    if errors:
        raise OSError('文件仍被占用，请退出该版本后重试：'+', '.join(errors[:4]))
    (root/MARKER).unlink()
    for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        try:
            plain_path(parent).rmdir()
        except OSError:
            pass  # Never remove unlisted files or a nonempty directory.
    try:
        root.rmdir()
    except OSError:
        pass
    return changed


def user_data_dir():
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x1C, None, 0, buffer) != 0:
        raise OSError('无法定位个人资料目录。')
    return Path(buffer.value)/'MaBaoNext'


def purge_user_data():
    target = plain_path(user_data_dir())
    if target.name != 'MaBaoNext' or target == Path(target.anchor):
        raise ValueError('个人资料目录无效。')
    if target.exists():
        for path in target.rglob('*'):
            plain_path(path)
        shutil.rmtree(target)


def remove_shortcuts(root):
    """Windows shell resolves link targets; remove only links to this EXE."""
    expected = str(Path(root)/EXECUTABLE).replace("'", "''")
    script = r"""
$ErrorActionPreference='Stop'
$expected='__TARGET__'
$desktop=[Environment]::GetFolderPath('Desktop')
$shell=New-Object -ComObject WScript.Shell
Get-ChildItem -LiteralPath $desktop -Filter '*.lnk' -File | ForEach-Object {
    $link=$shell.CreateShortcut($_.FullName)
    if ($link.TargetPath -eq $expected -and $_.DirectoryName -eq $desktop) {
        Remove-Item -LiteralPath $_.FullName -Force
    }
}
""".replace('__TARGET__', expected)
    # EncodedCommand avoids shell metacharacters in an installation path.
    import base64
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)
    if result.returncode:
        raise OSError('程序已移除，但桌面快捷方式未能自动清理，可手动删除该版本的快捷方式。')


def wait_for_app(pid, root):
    if not pid:
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 5:
            raise OSError('无法等待当前程序退出，请关闭软件后单独运行卸载程序。')
        return  # Application already exited.
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise OSError('无法确认正在退出的程序。')
        if Path(buffer.value) != Path(root)/EXECUTABLE:
            raise ValueError('等待退出的进程不是这个版本，已停止卸载。')
        if kernel.WaitForSingleObject(handle, 30000) != 0:
            raise OSError('软件尚未退出，请关闭后再运行卸载程序。')
    finally:
        kernel.CloseHandle(handle)


def running_apps():
    """Read-only process paths; no injection, hooks or process termination."""
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    pids = (wintypes.DWORD*32768)();used=wintypes.DWORD()
    if not psapi.EnumProcesses(pids,ctypes.sizeof(pids),ctypes.byref(used)):
        raise OSError('无法检查软件是否已退出。')
    paths = []
    for pid in pids[:used.value//ctypes.sizeof(wintypes.DWORD)]:
        handle = kernel.OpenProcess(0x1000,False,pid)
        if not handle:continue
        try:
            buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
            if kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):
                path=Path(buffer.value)
                if path.name.lower()==EXECUTABLE.lower():paths.append(path)
        finally:
            kernel.CloseHandle(handle)
    return paths


def message(text, flags=0x40):
    return ctypes.windll.user32.MessageBoxW(None, text, PRODUCT+' · 卸载', flags | 0x10000)


def queue_temp_cleanup(directory):
    """Only our copied helper/job; Windows removes the running helper on reboot."""
    directory = plain_path(directory)
    if directory.parent != Path(tempfile.gettempdir()).absolute() or not directory.name.startswith('GenshinImpactVT-uninstall-'):
        return
    move = ctypes.windll.kernel32.MoveFileExW
    move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    for name in ('Uninstall.exe', 'job.json'):
        move(str(directory/name), None, 4)
    move(str(directory), None, 4)


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-app', action='store_true')
    parser.add_argument('--purge-user-data', action='store_true')
    parser.add_argument('--wait-pid', type=int, default=0)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    try:
        if not getattr(sys, 'frozen', False):
            raise ValueError('卸载只用于便携版，不能删除开发源码。')
        if args.worker:
            job_file = plain_path(args.worker)
            if job_file.name != 'job.json' or job_file.parent != Path(sys.executable).parent:
                raise ValueError('卸载任务位置不正确。')
            job = json.loads(job_file.read_text(encoding='utf-8'))
            root, _ = load_install(job['root'])
            if digest(root/MARKER) != job['manifest_sha256']:
                raise ValueError('程序清单发生变化，请重新发起卸载。')
            wait_for_app(job['pid'], root)
            active = running_apps()
            if root/EXECUTABLE in active or (job['purge'] and active):
                raise OSError('软件仍在运行。卸载此版本请先退出它；清除共用资料请先退出所有版本。')
            changed = remove_owned_files(root)
            if job['purge']:
                purge_user_data()
            remove_shortcuts(root)
            detail = '个人资料已删除。' if job['purge'] else '收藏、设置和登录资料已保留。'
            if root.exists():
                detail += '\n目录中有额外或被修改的文件，已为你保留。'
            message('此版本已卸载。\n'+detail)
            queue_temp_cleanup(job_file.parent)
            return 0
        root, _ = load_install(Path(sys.executable).parent)
        purge = args.purge_user_data
        if not args.from_app:
            if message('卸载当前版本？\n\n'+str(root)+'\n\n其他版本和开发源码会保留。', 0x4 | 0x100 | 0x20) != 6:
                return 0
            choice = message('是否同时删除所有版本共用的收藏、历史、设置和登录资料？\n\n选“否”保留个人资料；选“取消”放弃卸载。', 0x3 | 0x100 | 0x20)
            if choice == 2:
                return 0
            purge = choice == 6
        directory = Path(tempfile.mkdtemp(prefix='GenshinImpactVT-uninstall-'))
        helper = directory/HELPER
        shutil.copy2(sys.executable, helper)
        job_file = directory/'job.json'
        job_file.write_text(json.dumps({'root':str(root),'manifest_sha256':digest(root/MARKER),
                                        'pid':args.wait_pid,'purge':purge}), encoding='utf-8')
        subprocess.Popen([str(helper),'--worker',str(job_file)],cwd=directory,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return 0
    except Exception as exc:
        message('卸载未完成：\n'+str(exc), 0x10)
        return 1
