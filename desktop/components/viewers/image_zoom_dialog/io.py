# -*- coding: utf-8 -*-
"""预览弹窗的**存盘原语**（下载另存 / 原子覆盖原图）。

从 ``image_zoom_dialog.py`` 拆出（2026-10-07）：两条写盘路径都收在这里，PNG
的"最省编码形态"也只在 ``utils.compact_png`` 一处实现——三个宿主（预览弹窗、
编辑器同步路、编辑器后台应用线程）共用同一份行为。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtGui import QImage

from utils.file_utils import replace_with_retry

from .consts import JPEG_QUALITY, OVERWRITE_FORMATS, OVERWRITE_JPEG_QUALITY


def save_image(image: QImage, path: str | Path,
               quality: int = JPEG_QUALITY) -> bool:
    """把 QImage 写到磁盘：``.jpg``/``.jpeg`` 走有损（quality），``.png`` 走
    紧凑编码，其余交给 Qt。

    单独抽出来是为了可测——保存对话框在离屏环境里弹不出来。

    ⚠️ PNG 走 :func:`_save_png_compact`（**不是** ``image.save(path)``）：Qt
    只会按 ``image.format()`` 原样落 8 位 RGBA/RGB，而"下载另存"出来的多半是
    去底色那种二值/灰阶页——同样的像素，1 位调色板比 RGBA 小一个数量级
    （实测 275KB → 141KB，见 ``utils.compact_png``）。逐像素无损。
    """
    target = Path(path)
    suffix = target.suffix.lower()
    # ⚠️ type: ignore —— PySide6 的 save() 类型注解把 format 写成
    # ``bytes | bytearray | memoryview | None``，但**运行时接受 str**（官方
    # 示例也传字符串）。这里按运行时的写法保持不变。
    if suffix in (".jpg", ".jpeg"):
        return bool(image.save(str(target), "JPEG", quality))  # type: ignore[reportCallIssue]
    if suffix == ".png":
        # 另存是新文件，dpi 只能来自 QImage 自己（Qt 会把它写成 pHYs，走了
        # 紧凑编码也别把这层元数据丢掉）。
        return _save_png_compact(image, target, dpi=_qimage_dpi(image))
    return bool(image.save(str(target)))  # type: ignore[reportCallIssue]


def overwrite_image_file(image: QImage, target: Path,
                         quality: int = OVERWRITE_JPEG_QUALITY) -> bool:
    """把 ``image`` **原子**覆盖到 ``target``（格式按目标后缀）。

    ⚠️ 必须走「临时文件 + os.replace」，不能就地写：任务目录里的页面图
    可能是硬链接（workset 时代的遗产），就地写会把链接另一头的源文件一起
    改掉；且覆盖途中被 200ms 一次的 extract 轮询/预览读到半截也是事故。
    ``os.replace`` 换的是目录项——读者要么看到完整旧图、要么看到完整新图，
    旧 inode 原样留在硬链接另一头。

    ⚠️⚠️ **``quality`` 只对 JPEG 有意义，PNG 绝不能传**（2026-10-14 用户报障
    「去底色图轻微编辑一下，实体图从 200K 涨到 5M」）：``quality`` 是 JPEG 的
    画质，而 Qt 把 PNG 的 ``quality`` 当**反过来的压缩级别**用——传 95 等于
    「压缩级别 ≈ 0」，PNG 几乎按原始字节存。用户机器上同一页的实测：

    =============================  =========  ================================
    写法                            体积       说明
    =============================  =========  ================================
    ``save(png, "PNG", 95)``        7.59 MB    改前：与磁盘上那份坏文件逐字节同尺寸
    ``save(png, "PNG")``             130 KB    同一张图，只是不传 quality
    :func:`_save_png_compact`         67 KB    1 位调色板（＝源文件的形态）
    =============================  =========  ================================

    所以 PNG 走 :func:`_save_png_compact`：既不传 quality，又按像素挑回
    "1 位调色板 + tRNS"这类最省形态（规则与实测见 ``utils.compact_png``）。
    其它格式沿用旧写法（BMP/TIFF 不认 quality，传了也无意义）。
    """
    fmt = OVERWRITE_FORMATS.get(target.suffix.lower(), "PNG")
    temp = target.with_name(
        f"{target.stem}.{os.getpid():x}{threading.get_ident():x}"
        f"{target.suffix}.part"
    )
    try:
        if fmt == "PNG":
            # ⚠️ 覆盖的是**已有实体图**，dpi 必须沿用原文件的 pHYs：去底色产物
            #    是 300 DPI，丢了会让下游按 72 DPI 算物理尺寸。
            from utils.compact_png import read_png_dpi

            saved = _save_png_compact(image, temp, dpi=read_png_dpi(target))
        elif fmt == "JPEG":
            # ⚠️ type: ignore —— 同 save_image：PySide6 的 save() 注解要求
            # format 是 bytes，但运行时接受 str（实测 str 正常编码）。
            saved = bool(image.save(str(temp), fmt, quality))  # type: ignore[reportCallIssue]
        else:
            saved = bool(image.save(str(temp), fmt))  # type: ignore[reportCallIssue]
        if not saved:
            _discard(temp)
            return False
        replace_with_retry(temp, target)
        return True
    except OSError:
        _discard(temp)
        return False


def _save_png_compact(image: QImage, temp: Path, dpi) -> bool:
    """PNG 分支：按像素挑最省形态落盘（编码规则见 ``utils.compact_png``）。

    编码器抛任何异常都退回 Qt 默认压缩（**仍不传 quality**，那才是体积杀手）
    ——"挑形态"只是省空间，不该让"保存这张图"整体失败。
    """
    try:
        from utils.compact_png import save_png_compact

        save_png_compact(_qimage_rgba_array(image), temp, dpi=dpi)
        return True
    except Exception:      # noqa: BLE001 - 编码形态挑不动就退回 Qt
        return bool(image.save(str(temp), "PNG"))  # type: ignore[reportCallIssue]


def _discard(temp: Path) -> None:
    """写失败时把半截临时文件收掉（否则任务目录里会攒下 ``*.part``）。"""
    try:
        temp.unlink(missing_ok=True)
    except OSError:
        pass


def _qimage_dpi(image: QImage):
    """QImage 自带的物理分辨率 → ``(x, y)`` DPI；没设过返回 ``None``。

    Qt 存图时会把 ``dotsPerMeter`` 写成 pHYs；换成 PIL 落盘就得自己换算，
    否则"另存一份"会凭空丢掉 300 DPI（下游按物理尺寸排版的地方会吃亏）。
    """
    x, y = image.dotsPerMeterX(), image.dotsPerMeterY()
    if x <= 0 or y <= 0:
        return None
    return x * 0.0254, y * 0.0254


def _qimage_rgba_array(image: QImage):
    """QImage → ``(H, W, 4)`` RGBA 数组（``uint8``，**独立于 QImage 生命周期**）。

    ⚠️ 四个坑（前三个与 ``desktop.stages.rembg_stage._qimage_rgb_array`` 同一套）：
    1. 走 ``Format_RGBA8888`` 让内存序就是 **R,G,B,A**——ARGB32 的内存序是
       B,G,R,A，直接按 RGBA 用会让红蓝互换；预乘变体还多一道解预乘
       （``convertToFormat`` 会做）。
    2. **必须真复制**（``.copy()``）：``frombuffer`` 只是引用 Qt 的缓冲区，而
       内存归 QImage 所有；转换格式产生的是**临时对象**，本函数一返回就被回收
       ⇒ 数组变成悬垂指针。实测症状是**段错误**（`读取 arr` 时 access violation）。
    3. ``bytesPerLine`` 可能有行尾填充，必须按行切片再 reshape。
    4. ⚠️ **不能用 ``np.ascontiguousarray`` 代替 ``.copy()``**：RGBA8888 的
       ``width*4`` 恰好等于 ``bytesPerLine`` 时切片本来就是连续的，它**原样返回
       那个视图**、一个字节都不复制——正是坑 2。本项目 2026-10-14 实测踩过：
       ``_apply_job`` 后台写底片时直接段错误。
    """
    import numpy as np
    from PySide6.QtGui import QImage as _QImage

    source = (image if image.format() == _QImage.Format.Format_RGBA8888
              else image.convertToFormat(_QImage.Format.Format_RGBA8888))
    height, width = source.height(), source.width()
    stride = source.bytesPerLine()
    buffer = np.frombuffer(source.constBits(), np.uint8)
    rows = buffer[: stride * height].reshape(height, stride)
    return rows[:, : width * 4].reshape(height, width, 4).copy()
