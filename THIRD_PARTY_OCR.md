# OCR 组件和模型

本功能没有使用原版 MaBao 的代码、模型、账号或云端服务。

| 组件 | 固定版本 / 来源 | 用途和许可 |
| --- | --- | --- |
| RapidOCR | PyPI `rapidocr==3.10.0`；https://github.com/RapidAI/RapidOCR | 图像检测与识别流程，Apache-2.0 |
| ONNX Runtime CPU | `onnxruntime==1.23.2`；https://github.com/microsoft/onnxruntime | CPU 推理，MIT |
| OpenCV headless | `opencv-python-headless==4.11.0.86` | 不加载 Qt 插件的图像解码；保留 wheel 中许可及所附第三方声明 |
| NumPy / Pillow | `numpy==2.2.6` / `Pillow==11.3.0` | 图像和数组支持，保留各包许可 |

采用 RapidOCR 3.10.0 官方 wheel 自带的 PaddleOCR 衍生模型。依赖包中的 `rapidocr-3.10.0.dist-info/licenses/MODEL_LICENSES.md` 分别声明工程和模型的权利来源，模型权利人为 Baidu 和/或 PaddleOCR 相应权利人，所列模型采用 Apache-2.0。完整声明随本项目 `assets/licenses/rapidocr/` 一同提供。

| 文件 | SHA-256 |
| --- | --- |
| PP-OCRv6_det_small.onnx | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| PP-OCRv6_rec_small.onnx | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |

应用启动识别工作进程时校验这两个模型。方向分类模型不参与本功能推理，但上游 wheel 自带的分类模型和声明可随依赖保留。应用只使用本地路径，不自动下载模型；截图和识别文字仅在内存中传递，设置仅保存开关、频率、模式和区域。

便携构建使用 `packaging/GenshinImpactVT.spec`，收集 RapidOCR 配置、模型、包元数据及许可。保持原声明不变；更新模型或依赖时需同步核对来源、哈希及声明。
