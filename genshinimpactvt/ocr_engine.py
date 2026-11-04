"""Optional OCR in a separate process. No screenshots, audio or text are uploaded."""
import hashlib
import time
from pathlib import Path


def create_engine():
    import rapidocr
    from rapidocr import RapidOCR
    root = Path(rapidocr.__file__).parent
    models = root / 'models'
    # Use wheel-bundled models only: no implicit runtime model downloads.
    det = models / 'PP-OCRv6_det_small.onnx'
    rec = models / 'PP-OCRv6_rec_small.onnx'
    if not det.is_file() or not rec.is_file():
        raise RuntimeError('OCR 模型缺失，请重新安装 requirements-ocr.txt 或使用完整软件包。')
    expected = ('090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f',
                '6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884')
    for path,digest in zip((det,rec),expected):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('OCR 模型校验失败，请重新安装指定版本的依赖。')
    return RapidOCR(params={
        'Det.model_path': str(det), 'Rec.model_path': str(rec),
        'Det.limit_type': 'max', 'Det.limit_side_len': 960,
        'Global.use_cls': False, 'Global.text_score': .72,
        'Global.log_level': 'error',
        'EngineConfig.onnxruntime.intra_op_num_threads': 2,
        'EngineConfig.onnxruntime.inter_op_num_threads': 1,
    })


def recognize(engine, png):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('无法读取字幕画面')
    result = engine(image, use_cls=False)
    lines = []
    if result.txts is not None:
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            if float(score) >= .72:
                lines.append((float(box[:, 1].mean()), float(box[:, 0].mean()), str(text)))
    return ' '.join(item[2] for item in sorted(lines))[:500]


def worker(requests, replies):
    try:
        engine = create_engine()
        replies.put(('ready',))
        previous = None; cached = ''
        while True:
            request = requests.get()
            if request is None:
                return
            token, generation, png = request
            start = time.monotonic()
            digest = hashlib.sha256(png).digest()
            if digest != previous:
                cached = recognize(engine, png); previous = digest
            replies.put(('result', token, generation, cached, round((time.monotonic()-start)*1000)))
    except Exception as exc:
        replies.put(('error', type(exc).__name__ + ': ' + str(exc)[:400]))
