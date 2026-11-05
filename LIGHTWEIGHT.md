# 轻量字幕实现说明

默认复用 B站已经生成的 AI/CC 字幕，不在本机运行语音或图像识别模型。

提供“打开官方纯播放器 / 返回完整 B站网页”两个入口。使用 B站公开文档的 `https://player.bilibili.com/player.html` 参数（https://player.bilibili.com/），选择当前 bvid/cid/p；切换下一集时清掉旧 cid，因为官方规定 cid 优先于 p。没有改变清晰度权限或绕过播放器限制。纯播放器功能已验证字幕和切集；不同视频、平台限制和长期内存仍需实测。

## 数据路线

1. 用户在软件 WebView2 中正常访问和登录 B站。
2. 开启轻量字幕功能后，使用 WebView2 的 `WebResourceResponseReceived` / `GetContentAsync` 读取播放器正常收到的 `/x/player/wbi/v2` 或 `/x/player/v2` 字幕字段。
3. 只保留登录需求标记和字幕轨信息，丢弃接口中的其他账号及播放器字段。按当前分 P 的 CID 匹配响应。
4. 优先选择中文轨，只读取该响应已经提供的 HTTPS `*.hdslb.com/bfs/subtitle/` 或 `/bfs/ai_subtitle/` 地址。后台一次性下载有大小、超时和重定向域名限制；不携带 Cookie。
5. 将 `from/to/content` 解析成内存时间轴，按 `video.currentTime` 二分查找。快进、回退后直接查当前时间；换分 P 清掉旧时间轴。页面跟踪参数变化不重复下载。

没有调用平台生成服务、构造 WBI 签名、导出浏览器凭证、绕过登录/付费限制或使用原软件实现。接口是网页内部行为而非稳定公开 SDK，格式变化可能需要维护。没有字幕时提示，不能承诺所有视频可用。

## 资源边界

- 轻量包通过 `packaging/GenshinImpactVT-light.spec` 明确排除 RapidOCR、ONNX Runtime、NumPy、OpenCV、Pillow、OCR 模型等；基础依赖仍是 `requirements.txt`。
- 关闭字幕功能不执行页面定时脚本，不订阅字幕网络响应。开启后仅在等候响应/下载期间运行额外的网络轮询；完成后网络定时器和下载线程退出。
- 播放中查询时间间隔 300 ms，暂停时 700 ms；已载入平台字幕时避免截图。字幕内存缓存随页面或分 P 更换清理，不写入磁盘。v1.1 的透明字幕在文字、视频尺寸、滚动或全屏事件变化时读取视频矩形，不增加持续采样或动画。
- 浏览器完整网页及视频解码仍会消耗 CPU/GPU/内存。不能以“没有 AI 模型”等同于软件总占用很小；性能记录应分别统计主进程、WebView2 进程树、播放状态和采样条件。

## 构建与验证

```powershell
python -m PyInstaller --noconfirm --distpath .build/light-dist --workpath .build/light-work packaging/GenshinImpactVT-light.spec
python -B -m unittest discover -s tests -v
python -B tests/bilibili_native_smoke.py
```

最后一个测试明确使用软件现有浏览器会话访问提供的视频，应用配置和测试结果在 `.test-bilibili-light/` 隔离；不导出 Cookie、账号标识或完整字幕。已登录字幕可用性与匿名测试应分别报告。

## 视频内字幕层

`subtitle_overlay.py` 使用 [WebView2 ExecuteScriptAsync](https://learn.microsoft.com/microsoft-edge/webview2/how-to/javascript) 在当前视频矩形内放置透明、鼠标穿透的文字层。Shadow DOM 隔离网页样式，字幕通过 `textContent` 写入；容器全屏时移入全屏容器。原生 `<video>` 全屏使用单独的文本轨道并转义文字，读取器排除这条显示轨，避免重复识别。

尺寸变化由 ResizeObserver、窗口 resize/scroll 和 fullscreenchange 事件触发，没有常驻重绘循环；空字幕移除显示节点、取消待绘制帧并断开视频尺寸观察。仅支持当前顶层文档中的视频，未实现跨域 iframe 内的叠层；当前 B站完整页与官方纯播放器均在该范围内。

`tests/subtitle_overlay_smoke.py` 使用本地视频和隔离 profile 验证透明渲染、纯文本、布局跟随、小窗、两种全屏、隐藏和清空。全屏测试使用 WebView2 的 [CallDevToolsProtocolMethodAsync](https://learn.microsoft.com/dotnet/api/microsoft.web.webview2.core.corewebview2.calldevtoolsprotocolmethodasync) 给本地页面测试调用提供手势；产品不开放调试端口，也不用该调用处理字幕。


## v1.3.1 自动恢复

被动响应可能早于用户开启识别，也可能在切分 P 时丢失。现在按当前 URL 的 BVID 和 p 主动补读：在 WebView2 页面内正常访问 `/x/web-interface/view` 获取对应 CID，优先复用播放器已经发出的、BVID/aid 和 CID 匹配的 `/x/player/wbi/v2` 请求；缺失或失效时使用携带 aid、CID 的普通 `/x/player/v2`，再读取允许的 HTTPS CDN 字幕。仅回放现成请求，不生成或修改签名。接口在当前会话中请求，不导出 Cookie、生成签名或调用字幕生成服务；仍受正常登录和平台权限约束。这些是网页内部接口，不是稳定公开 SDK。

页面异步请求使用 AbortController 和 18 秒整体期限，原生侧异步读取结果，22 秒后放弃卡住任务。每个视频最多四次恢复尝试，失败间隔为 2、5、12 秒；成功或次数耗尽后停止恢复计时器。手动重试重新计数，不刷新网页。每个响应最多 4 MiB，字幕解析最多 30,000 行；过滤非允许的字幕地址，仅读取一次时间轴。关闭识别/换页会中止旧恢复任务，不上传字幕和音频。

BVID、CID、分 P 与当前 URL 对齐；返回身份不一致时拒绝。启用前错过响应、请求偶发失败、旧分 P 延迟回包都有测试。字幕内容和临时响应只存在内存。WebView2 执行脚本与 JSON 返回方式参考 [Microsoft 官方说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/javascript)。
