# GenshinImpactVT 使用说明

GenshinImpactVT 是一个用来看攻略视频的 Windows 小窗口。你可以打开哔哩哔哩视频，让窗口保持在游戏画面上方，一边看攻略一边玩。

本项目为独立开发的非官方工具，与《原神》及其运营方没有官方关联。

## 怎样打开

1. 找到 `GenshinImpactVT-便携版.zip`，右键选择“全部解压缩”。
2. 打开解压出来的 `GenshinImpactVT` 文件夹，双击 **GenshinImpactVT.exe**。
3. Windows 询问是否允许以管理员身份运行时，选择“是”。这是为了让软件与同样以管理员身份运行的游戏配合使用。
4. 在顶部地址栏粘贴哔哩哔哩视频链接，按回车打开。

请先解压整个文件夹，不要直接在压缩包里双击运行，也不要把 exe 单独移走：它需要旁边的 `_internal` 文件夹。这个包已经包含 Python 和程序依赖，不需要另外安装 Python。

第一次运行需要 Windows 10/11 64 位、Microsoft Edge WebView2 Evergreen Runtime 和 .NET Framework 4.8。大多数 Windows 电脑已有这些组件；如果界面提示缺少 WebView2，可从微软官网下载并安装：https://developer.microsoft.com/microsoft-edge/webview2/

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

## ?????????

?? Windows x64?Python 3.12 x64?.NET Framework 4.8 ? WebView2 Evergreen Runtime?????????

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_webview2.py
.\.venv\Scripts\python.exe main.py
```

SDK ????? NuGet ????? Microsoft WebView2 SDK ??? SHA-256?`launch.vbs` ??? Windows UAC ??????????????????????????

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

?????[MaBao ????](https://gitee.com/LanRenZhiNeng/mabao)???????????????????????????
