# GenshinImpactVT

当前版本 **v2.0.1**（内部版本 2.0.1），Windows 攻略视频桌面工作台。使用 Python 3.12、PySide6、pythonnet、WinForms WebView2 和 WebView2 Evergreen Runtime。

## 下载和启动

从 [v2.0.1 发布页](https://github.com/xysslsy/GenshinImpactVT/releases/tag/v2.0.1) 下载，或[直接下载 Windows x64 ZIP](https://github.com/xysslsy/GenshinImpactVT/releases/download/v2.0.1/GenshinImpactVT-v2.0.1-windows-x64.zip)。全部解压后，双击 `GenshinImpactVT/GenshinImpactVT.exe`，确认 Windows 管理员权限。不要单独移动 EXE，保留 `_internal`。

本机当前入口为桌面 **GenshinImpactVT v2.0.1**；程序在 `D:\AINixiang\GenshinImpactVT\releases\v2.0.1\GenshinImpactVT\GenshinImpactVT.exe`。更新前先完全退出旧版。[文件位置](LOCATIONS.md) · [发行记录](RELEASES.md) · [测试记录](TESTING.md)。

需要 Windows 10/11 x64、.NET Framework 4.8，以及 [WebView2 Evergreen Runtime](https://developer.microsoft.com/microsoft-edge/webview2/#download)。普通用户无须安装 Python。

## 边玩边看

1. 在地址栏打开 B站攻略，按需在网页内正常登录。
2. 点 **小窗观看**，缩成左下角窗口；开启 **窗口置顶**。游戏使用窗口化或无边框窗口。
3. **F9** 唤出或隐藏控制条。控制条的关闭按钮只隐藏它；**F11** 恢复完整界面。
4. **F2** 更透明、**F3** 更不透明、**F4** 恢复完全不透明。每次调整 10%，范围 20%～100%，视频画面也一起透明。设置页有滑块，系统托盘菜单也有恢复不透明入口。

## 字幕与方向提醒

默认每次启动、打开新视频或切分 P 都启用 **自动：校验当前视频的 B站中文字幕**，无需先去设置切模式。每轮失败时最多串行尝试 **3 次**，成功核对后立即停止，不反复覆盖已正确载入的内容。要持续使用手动模式，可取消字幕页的 **启动及新视频自动启用自动模式**。状态显示“已核对 BV… · P… · 中文 · N 条字幕”，可以直接核对当前视频。

v2.0 将字幕绑定到页面文档、主视频元素、实际播放媒体 CID、媒体源和本次请求代次。自动模式只接受这一条校验链路的结果；迟到回包、错视频响应或未核对的网页文字都不能覆盖当前字幕。没有通过核对时会等待/提示，不以旧字幕填充。

可点 **重新自动读取字幕（不刷新视频）**，即使当前识别被关闭或处于手动模式，也会启用自动模式并开始新一轮最多三次尝试，保持播放位置。登录失效、平台未提供中文字幕、网络失败会分别提示；它不调用平台字幕生成服务，也不绕过访问限制。

勾选 **在视频内显示透明字幕**，文字会叠在视频底部。点击 **显示方向浮窗**，拖到游戏小地图附近。默认保持 5 秒，可调为 1～30 秒，并修改颜色、强度和大小。v2.0 改为八向圆周边缘高亮带：北方亮上弧、东北亮右上弧，中心及未提示区域保持透明；不再显示方位光球，也没有完整圆形边框。

播放时约每 100 ms 查询状态，方向按字幕句子 ID 触发；短句跨过一次查询也会补捉，连续相同方向可再次点亮。支持“正北、东北角、北偏东”等表达。同一句内多个顺序方向按文字比例近似推进，仍受平台字幕时间及文字准确性影响。

网页文字读取和画面 OCR 保留为手动模式，自动模式不在它们之间偷偷切换。源码可选安装 OCR 依赖；本发行包无需本地模型即可完成此次修复。可用 **打开官方纯播放器** 减少网页侧栏，或 **返回完整 B站网页**。

## 默认快捷键

| 动作 | 默认键 |
| --- | --- |
| 暂停 / 播放 | 鼠标侧键上键（XBUTTON2） |
| 快退 / 快进 5 秒 | 5 / 6；侧键下键也可快退 |
| 上一集 / 下一集 | 7 / 8 |
| 显示 / 隐藏控制条 | F9 |
| 切换极简模式 | 0 |
| 显示 / 隐藏主窗口 | 9 |
| 最大化 / 还原 | F10 |
| 恢复正常界面 | F11 |
| 显示 / 隐藏方向浮窗 | F8 |
| 更透明 / 更不透明 / 完全不透明 | F2 / F3 / F4 |

全部动作可在 **设置 → 自定义快捷键 → 编辑快捷键** 修改，包括两枚鼠标侧键。留空禁用，重复键拒绝，编辑期间暂停动作。升级时旧配置优先；若新增默认键与旧自定义键冲突，新动作留空，原设置保留。

普通监听不拦截原按键，打字也可能触发。系统全局模式会占用所设键，退出释放注册。真实游戏输入仍取决于权限和驱动；程序启动沿用管理员权限请求。

## 本地资料与卸载

收藏、历史、设置和网页登录资料共用 `%LOCALAPPDATA%\MaBaoNext`；历史包含访问过的 URL。个人资料与发行目录分开，更新不主动清除。不要将此目录上传。

卸载入口为 **设置 → 软件管理 → 卸载此版本…** 或程序目录的 **Uninstall.exe**。默认保留个人资料；清除选项会影响所有版本共用的资料。按文件清单移除本版本，保留额外或修改过的文件，详见随包 README。

## 源码运行和构建

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_webview2.py
.\.venv\Scripts\python.exe main.py
```

可选 OCR：`pip install -r requirements-ocr.txt`；开发/打包依赖：`pip install -r requirements-dev.txt`。WebView2 SDK 从官方 NuGet 下载并校验。源码入口 `launch.vbs` 无命令行窗口并请求管理员权限。

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -B tests/v2_caption_chaos_smoke.py
.\.venv\Scripts\python.exe -B tests/v2_opacity_smoke.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath .build/dist --workpath .build/work packaging/GenshinImpactVT-light.spec
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath .build/uninstall-dist --workpath .build/uninstall-work packaging/GenshinImpactVT-uninstall.spec
.\.venv\Scripts\python.exe packaging/prepare_portable.py --dist .build/dist/GenshinImpactVT --helper .build/uninstall-dist/Uninstall.exe --output releases/v2.0.1
```

完整便携包组装不覆盖已有版本。测试的合成场景、真实 B站、源码运行与发行 EXE 静态检查分别记录，详见 [TESTING.md](TESTING.md)。[架构与资源边界](LIGHTWEIGHT.md) · [Git 工作流](GIT_WORKFLOW.md) · [版本变更](CHANGELOG.md)。
