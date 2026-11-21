# -*- coding: utf-8 -*-
"""剥掉图片里的 **EXIF 方向语义**（保留像素原样）。

为什么需要（用户 2026-11-20 报「图片去底色后整本书全倒过来了」）：

扫描 PDF 的内嵌 JPEG 常残留 ``EXIF Orientation``（274）标签，而 **PDF 渲染
并不看 EXIF**——PDF 里看到的方向就是**像素原样**。提取走 quick 直拷时若把
标签一起写到产物上，下游各消费端对它的处理并不一致：

- 去底色 / 生成 PDF（PIL）与检测（``cv2.imdecode``）**会按标签再转一次**；
- Qt（``QImage`` / ``QImageReader``，``autoTransform`` 默认 False）**不转**。

于是同一张图在预览里是正的、在去底色成品里是倒的（整本 180° 或整页横躺），
拼版按 ``-l``/``-r`` 的名字配对时左右身份也跟着互换，表现为"整本书倒过来、
只能从最后一页开始拼"。

约定：**凡本程序自己落盘的页面图，一律不带方向标签**——像素以 PDF 所见为准，
下游谁都不必再猜。用户直接放进来的素材不在此列（那是他自己的文件）。

本模块只做字节级搬移，**不解码像素**；没有方向标签时原样返回同一份字节对象
（quick 直拷的"零解码零重编码"契约因此不受影响）。
"""

from __future__ import annotations

import io
from typing import Optional

#: JPEG 里承载 EXIF 的段标识（APP1 + "Exif\0\0"）
_JPEG_EXIF_MARK = b"Exif\x00\x00"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _exif_orientation(data: bytes) -> int:
    """图片 EXIF 里的方向标签（274）；读不出/没有标签一律返回 1。"""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as probe:
            # ⚠️ 只读文件头（不 load）：quick 直拷路径上不能因为这件事解码整张图
            return int(probe.getexif().get(274, 1) or 1)
    except Exception:  # noqa: BLE001 - 坏图/格式不支持：按"没有标签"处理
        return 1


def _strip_jpeg(data: bytes) -> bytes:
    """删掉 JPEG 里承载 EXIF 的 APP1 段；其余段与压缩数据原样搬运。"""
    out = bytearray(data[:2])
    index = 2
    removed = False
    total = len(data)
    while index + 4 <= total:
        if data[index] != 0xFF:
            break
        marker = data[index + 1]
        # 无载荷的独立标记
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            out += data[index:index + 2]
            index += 2
            continue
        if marker == 0xDA:
            # SOS 之后是熵编码数据，里面也会出现 0xFF：整段原样拷贝到结尾
            out += data[index:]
            return bytes(out) if removed else data
        segment_length = int.from_bytes(data[index + 2:index + 4], "big")
        end = index + 2 + segment_length
        if segment_length < 2 or end > total:
            break  # 段长度不合理（截断/损坏）：别再猜，整段保留
        segment = data[index:end]
        if marker == 0xE1 and segment[4:10] == _JPEG_EXIF_MARK:
            removed = True
        else:
            out += segment
        index = end
    # 走到这里说明结构没按预期结束（比如 0xFF 之外的填充字节）：原样收尾
    out += data[index:]
    return bytes(out) if removed else data


def _strip_png(data: bytes) -> bytes:
    """删掉 PNG 的 ``eXIf`` 块；其余块（含 CRC）原样搬运。"""
    out = bytearray(data[:8])
    index = 8
    removed = False
    total = len(data)
    while index + 12 <= total:
        length = int.from_bytes(data[index:index + 4], "big")
        kind = data[index + 4:index + 8]
        end = index + 12 + length
        if end > total:
            break
        if kind == b"eXIf":
            removed = True
        else:
            out += data[index:end]
        index = end
        if kind == b"IEND":
            break
    out += data[index:]
    return bytes(out) if removed else data


def strip_orientation(data: bytes) -> bytes:
    """返回**不带 EXIF 方向标签**的图片字节（像素逐位不变）。

    参数:
        data: 完整图片字节（JPEG / PNG）。

    返回:
        去掉方向标签后的字节；**没有标签或格式不认识时原样返回入参对象**，
        调用方可据此直接走"零拷贝直写"。

    说明:
        只在方向标签存在且不为 1 时动手——``Orientation=1``（正向）的 EXIF
        段保留，避免无意义地改写文件。
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 16:
        return data
    if _exif_orientation(data) == 1:
        return data
    if data[:2] == b"\xff\xd8":
        return _strip_jpeg(bytes(data))
    if data[:8] == _PNG_SIGNATURE:
        return _strip_png(bytes(data))
    return data


def read_orientation(data: Optional[bytes]) -> int:
    """图片字节的 EXIF 方向标签（274），无标签返回 1。供自测/诊断使用。"""
    if not data:
        return 1
    return _exif_orientation(bytes(data))


__all__ = ["strip_orientation", "read_orientation"]
