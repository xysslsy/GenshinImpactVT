# GenshinImpactVT 使用说明

GenshinImpactVT 是一个用来看攻略视频的 Windows 小窗口。你可以打开哔哩哔哩视频，让窗口保持在游戏画面上方，一边看攻略一边玩。

本项目为独立开发的非官方工具，与《原神》及其运营方没有官方关联。

## 下载与安装

适用于 **Windows 10 / 11 64 位**。这是免安装版本，不需要安装 Python。

1. 打开 [下载页面（v0.1.0 预发布版）](https://github.com/xysslsy/GenshinImpactVT/releases/tag/v0.1.0)，在页面的 **Assets** 下点击 `GenshinImpactVT-windows-x64.zip`。也可以[直接下载压缩包](https://github.com/xysslsy/GenshinImpactVT/releases/download/v0.1.0/GenshinImpactVT-windows-x64.zip)。
2. 下载完成后，右键压缩包，选择 **全部解压缩**，并选择一个容易找到的文件夹。
3. 打开解压得到的 `GenshinImpactVT` 文件夹，双击 **GenshinImpactVT.exe**。如果 Windows 弹出管理员权限确认，选择 **是**；这有助于快捷键在同样以管理员权限运行的游戏中工作。
4. 在软件顶部地址栏粘贴哔哩哔哩视频链接，按回车即可观看。

请保留程序旁边的 `_internal` 文件夹，不要直接在压缩包里运行，也不要单独移动 exe。需要桌面快捷方式时，可以右键 exe，选择 **发送到 → 桌面快捷方式**。

软件还需要 Microsoft Edge WebView2 Evergreen Runtime 和 .NET Framework 4.8。如果提示缺少 WebView2，请到 [微软官网](https://developer.microsoft.com/microsoft-edge/webview2/)下载安装 Evergreen Runtime；缺少 .NET Framework 时，请从 [微软官网](https://dotnet.microsoft.com/download/dotnet-framework/net48)下载安装。

## 游戏时怎么用

- 勾选软件底部的 **窗口置顶**，调整窗口大小和位置，然后切回游戏。建议游戏使用“无边框窗口”模式。
- 鼠标侧键上键：播放或暂停；下键：快退 5 秒。你可以在设置中关闭侧键或切换侧键监听方式。
- 键盘 `7`：上一集；`8`：下一集。设置中可关闭。普通监听不拦截按键；可选的“系统全局热键”可能让其他程序暂时无法输入这两个数字，切回普通监听或退出软件后会释放。
- 想让画面更简洁，点击 **精简窗口**；需要恢复时，用悬浮控制窗中的 **显示 / 隐藏工具栏** 按钮。
- 点击 **显示方向浮窗**，把东南西北文字拖到需要的位置。高亮颜色可以在设置里更改。

## 目前的限制

方向提示目前只能尝试读取网页提供的字幕文本，无法直接听声音，也无法识别画面里的硬字幕。没有可读取字幕时，它不会自动显示方向。部分视频的分集结构、鼠标驱动或游戏输入方式可能导致快捷操作不生效。

游戏中若按键失效，请检查是否在 UAC 窗口中选择了“是”，以及设置中对应功能是否开启。软件和游戏的实际权限、游戏显示模式和其他程序的按键占用都可能影响使用。

## 数据与卸载

收藏、历史、设置和浏览器资料保存在当前 Windows 用户的 `%LOCALAPPDATA%\MaBaoNext` 文件夹，不在压缩包内。这个旧目录名用于兼容之前的版本，改名后仍可读取原有资料。删除解压后的程序文件夹即可移除程序；如也想删除收藏、历史和登录状态，请自行确认后删除该数据文件夹。

程序图标来自你提供的图片。若 Windows 仍显示旧快捷方式图标，可以删除旧快捷方式，再对新 exe 右键创建快捷方式。

## 从源码运行

需要 Windows x64、Python 3.12 x64、.NET Framework 4.8 和 WebView2 Evergreen Runtime。在仓库目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_webview2.py
.\.venv\Scripts\python.exe main.py
```

SDK 安装脚本从 NuGet 官方源下载 Microsoft WebView2 SDK 并核对 SHA-256。`launch.vbs` 会通过 Windows UAC 请求管理员权限。

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

参考项目：[MaBao 官方仓库](https://gitee.com/LanRenZhiNeng/mabao)。本项目独立开发，不包含其闭源实现、模型或账号服务。
