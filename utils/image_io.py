# -*- coding: utf-8 -*-
"""OpenCV 图片读写的路径安全封装。

``cv2.imread`` / ``cv2.imwrite`` 在 Windows 上走的是 ANSI 文件接口，
路径含中文（古籍文件名基本都是中文）时会**静默返回 None / False**，
表现为"无法读取图片"或输出为空。这里统一改为
``np.fromfile`` + ``cv2.imdecode`` 的字节流方式，绕开编码问题。

cv2 / numpy 体积大且加载慢，故在函数内延迟导入——GUI 主进程只是
偶尔需要读一张图，不应该为此付出启动时间的代价。
"""

from __future__ import annotations

from pathlib import Path


def imread(path, flags=None):
    """读取图片（支持中文等非 ASCII 路径）。

    参数:
        path: 图片路径（str / Path）。
        flags: cv2.IMREAD_* 标志，默认 IMREAD_COLOR。

    返回:
        numpy 数组；文件不存在或无法解码时返回 None。
    """
    import cv2
    import numpy as np

    if flags is None:
        flags = cv2.IMREAD_COLOR
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    image = cv2.imdecode(data, flags)
    return image


def imwrite(path, image) -> bool:
    """写出图片（支持中文等非 ASCII 路径），成功返回 True。

    编码格式由扩展名决定，无法识别时回退 PNG。
    """
    import cv2

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower() or ".png"
    try:
        ok, buffer = cv2.imencode(suffix, image)
    except cv2.error:
        ok, buffer = cv2.imencode(".png", image)
    if not ok:
        return False
    buffer.tofile(str(target))
    return True
