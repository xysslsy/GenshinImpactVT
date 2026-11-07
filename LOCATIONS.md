# GenshinImpactVT 文件位置

当前版本 **v2.0.2**，桌面快捷方式为 **GenshinImpactVT v2.0.2**。

- 程序：`D:\AINixiang\GenshinImpactVT\releases\v2.0.2\GenshinImpactVT\GenshinImpactVT.exe`
- 压缩包：`D:\AINixiang\GenshinImpactVT\releases\v2.0.2\GenshinImpactVT-v2.0.2-windows-x64.zip`
- 随包说明：`D:\AINixiang\GenshinImpactVT\releases\v2.0.2\README.md`
- 源码与 Git 仓库：`D:\AINixiang\GenshinImpactVT`

v2.0.2 移除会返回无关内容的旧字幕接口回退，优先读取真实播放器响应。

v2.0.2 默认在启动及新视频启用自动字幕；每轮失败最多串行尝试三次，成功即停止。手动“重新自动读取”也会切回自动并启用识别，不刷新视频。可在字幕页取消默认跟随以长期使用手动模式。

沿用 v2.0 的字幕归属校验及方向弧带；自动模式核对当前页面、播放实例及实际媒体 CID，不用旧结果补空白。方向显示改为圆周边缘的弧带，北方亮上弧，东北亮右上弧，中心透明。

F2 更透明，F3 更不透明，F4 恢复不透明；F9 显示/隐藏控制条，F11 恢复正常界面。所有键都可在设置中修改。若旧自定义键冲突，会保留旧键并将冲突的新动作留空。

本机发行目录仅保留 v2.0.2。旧版在核对云端备份后移入回收站，可恢复；[GitHub 历史发行](https://github.com/xysslsy/GenshinImpactVT/releases) 继续保留。收藏、历史、配置和登录资料仍在 `%LOCALAPPDATA%\MaBaoNext`。

[八向弧带预览](D:/AINixiang/GenshinImpactVT/docs/v2-rim-preview.png) · [v2.0.2 下载](https://github.com/xysslsy/GenshinImpactVT/releases/tag/v2.0.2) · [详细使用说明](https://github.com/xysslsy/GenshinImpactVT#readme)
