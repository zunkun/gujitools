# -*- coding: utf-8 -*-
"""quick 模式（直取 PDF 内嵌图）的判定与落盘。"""

import io
import math
import os

from utils.exif_clean import strip_orientation
from utils.pdf_extract.constants import (
    IGNORABLE_ANNOT_TYPES,
    QUICK_MIN_COVERAGE,
    QUICK_SOURCE_EXTS,
)
from utils.pdf_extract.render import _save_pil
from utils.file_utils import write_bytes_atomic


def _page_scan_block_reason(page):
    """本页除了那张内嵌图，还有没有别的东西会**产生像素**。

    返回 None 表示"纯扫描页"（只有一张图，没有别的可见内容），可以直接取图；
    否则返回一句人读原因，调用方回退整页渲染。

    判据（先便宜后昂贵；实测纯扫描页约 0.5ms，复杂矢量页约 100ms——后者本来
    就要回退渲染，这点开销可以忽略）：

    - 页面旋转 / 裁切框（整页渲染会转正、裁边，直拷不会）；
    - 注释：``/Link`` 没有外观，可忽略；其余一律算有内容；
    - 可见文字：``get_texttrace()`` 的 ``type == 3`` 是不可见 OCR 层，不产生像素，
      可忽略；其余类型（0/1/…）算可见文字；
    - 矢量绘制：``get_drawings()`` 非空即算（水印/线框/印章轮廓）。
    """
    if int(page.rotation) % 360:
        return "页面有旋转"
    crop, media = page.cropbox, page.mediabox
    if (
        abs(crop.x0 - media.x0) > 0.5
        or abs(crop.y0 - media.y0) > 0.5
        or abs(crop.x1 - media.x1) > 0.5
        or abs(crop.y1 - media.y1) > 0.5
    ):
        return "页面有裁切框"
    try:
        for annot in page.annots() or ():
            kind = annot.type
            name = str(kind[1] if isinstance(kind, tuple) and len(kind) > 1 else kind)
            if name not in IGNORABLE_ANNOT_TYPES:
                return f"页面有注释（{name or '未知'}）"
    except Exception:  # noqa: BLE001 - 读不出注释就从严回退
        return "页面注释检查失败"
    try:
        for span in page.get_texttrace():
            if int(span.get("type", 0)) != 3:
                return "页面有可见文字"
    except Exception:  # noqa: BLE001 - 这一项读不出来就从严回退
        return "页面文字检查失败"
    try:
        if page.get_drawings():
            return "页面有矢量绘制"
    except Exception:  # noqa: BLE001
        return "页面绘制检查失败"
    return None


def _embedded_page_image(doc, page, page_rect, ext: str, actual_zoom: float):
    """判断本页能否走 quick（直接取内嵌图）。

    返回 (info, None) 可取；(None, 原因) 需降级为整页渲染。判定顺序：

    1. **内嵌图必须只有一张**。一页多图时老实现会产出 ``1_1.jpg``/``1_2.jpg``
       多个文件，而 detect/rembg/print 全部按「一页一图」工作，多出来的文件会
       被打成孤儿页。
    2. **页面上不能有别的可见内容**（见 ``_page_scan_block_reason``）：文字、
       矢量绘制、注释、旋转、裁切框都会被整页渲染画进结果，直拷会丢。
    3. **格式必须是 jpg/png**。jp2/jbig2/CCITT 之类要解码再重编码，很可能比
       整页渲染还慢（"quick" 名不副实），而且 PIL 缺解码器时整页直接失败。
    4. **像素不得低于整页渲染尺寸**。否则是低清缩略图/装饰图，取它只会更糊。
    """
    images = page.get_images(full=True)
    if len(images) != 1:
        return None, f"内嵌 {len(images)} 张图（多图不取，避免破坏一页一图）"
    why = _page_scan_block_reason(page)
    if why is not None:
        return None, why
    try:
        info = doc.extract_image(images[0][0])
    except Exception as exc:  # noqa: BLE001
        return None, f"extract_image 失败（{type(exc).__name__}）"

    src_ext = (info.get("ext") or "").lower().lstrip(".")
    if src_ext not in QUICK_SOURCE_EXTS:
        return None, f"内嵌格式 .{src_ext}（非 jpg/png，解码重编码不划算）"

    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    if not w or not h:
        return None, "取不到内嵌图尺寸"

    target_w = max(1.0, page_rect.width * actual_zoom)
    target_h = max(1.0, page_rect.height * actual_zoom)
    if min(w / target_w, h / target_h) < QUICK_MIN_COVERAGE:
        return None, f"内嵌图 {w}x{h} 小于渲染尺寸 {int(target_w)}x{int(target_h)}（低清）"
    return info, None


def _exif_swap_dims(data: bytes, w: int, h: int) -> tuple[int, int]:
    """EXIF 方向为 5~8（横竖互换）时交换宽高。

    ⚠️ **2026-11-20 起 quick 直拷不再用它**：落盘前会剥掉方向标签
    （:func:`utils.exif_clean.strip_orientation`），像素＝PDF 所见，上报尺寸
    就是内嵌图原始宽高。保留本函数是给"未剥段"的诊断/回溯按标签换算出
    **下游会看到**的尺寸用。

    事实基础：**PDF 渲染不看 EXIF**——PDF 里看到的方向就是像素原样。
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as probe:
            if probe.getexif().get(274, 1) in (5, 6, 7, 8):
                return h, w
    except Exception:  # noqa: BLE001 - 读不出方向就按未旋转上报
        pass
    return w, h


def _save_embedded_image(info, out_dir: str, page_idx: int, ext: str,
                         actual_zoom: float):
    """保存内嵌图：能原样落盘就直接写字节，否则解码转码。返回 (路径, 宽, 高)。

    ⚠️ **两条分支都不许让 EXIF 方向标签活到下游**（用户 2026-11-20 报
    「图片去底色后整本书全倒过来了」）：扫描 PDF 的内嵌 JPEG 常残留
    ``Orientation``，而 PDF 渲染不看它。标签一旦落盘，去底色（PIL）与检测
    （cv2）会再转一次、Qt 预览却不转（``autoTransform`` 默认 False），同一
    步骤里的图方向各不相同。详见 :mod:`utils.exif_clean`。
    """
    src_ext = (info.get("ext") or "").lower().lstrip(".")
    img_path = os.path.join(out_dir, f"{page_idx + 1}.{ext}")

    same_format = (src_ext in ("jpeg", "jpg") and ext.lower() == "jpg") or (
        src_ext == "png" and ext.lower() == "png"
    )
    if same_format and math.isclose(actual_zoom, 1.0):
        # 最快的路径：直接把 PDF 里的压缩字节写成文件，零解码零重编码。
        # ⚠️ 必须**原子写**（2026-09-26 审计）：写到一半被 kill/断电会留下截断的
        #    图片文件，而下游（detect/rembg/print）会把它当成有效页继续处理——
        #    表现为"某一页莫名处理失败/出半张白图"，且没有任何提示。
        #    原子写保证目标名下要么没有、要么完整。
        # ⚠️ **不许把 EXIF 方向标签带到下游**（用户 2026-11-20 报「图片去底色后
        #    整本书全倒过来了」）：扫描 PDF 的内嵌 JPEG 常残留 ``Orientation``，
        #    而 PDF 渲染根本不看它。标签一旦落盘，去底色（PIL）与检测（cv2）会
        #    再转一次、Qt 预览却不转（``autoTransform`` 默认 False）——同一步骤
        #    里的图方向各不相同，成品整本倒置、拼版左右身份互换。
        #    ``strip_orientation`` 只做字节级段搬移（不解码像素），没有标签时
        #    原样返回入参，"零解码零重编码"契约不变。见 :mod:`utils.exif_clean`。
        write_bytes_atomic(img_path, strip_orientation(info["image"]))
        # 尺寸＝落盘像素尺寸：标签已剥，不再按 EXIF 换算（否则框坐标基准会错）
        return img_path, int(info["width"]), int(info["height"])

    from PIL import Image

    img = Image.open(io.BytesIO(info["image"]))
    # ⚠️ 元数据里的方向标签一并摘掉：即使某些 Pillow 版本会顺手把 ``info["exif"]``
    #    带到下一个文件里，也不许它活到下游（理由同上）。
    img.info.pop("exif", None)
    # ⚠️ **不按 EXIF 转正**（2026-11-20）：这里以前做 ``exif_transpose``，等于
    #    拿"PDF 里根本不生效的元数据"去改像素——标签是假的时候（扫描软件转了
    #    像素却留着旧标签）整页就此倒过来。像素原样才与 PDF 显示一致；标签也
    #    不写回（``_save_pil`` 不传 ``exif=``），下游同理不会二次旋转。
    if not math.isclose(actual_zoom, 1.0):
        img = img.resize(
            (max(1, int(img.width * actual_zoom)), max(1, int(img.height * actual_zoom))),
            # ⚠️ type: ignore[attr-defined] —— ``Image.LANCZOS`` 在新版 Pillow
            # 里搬到了 ``Image.Resampling.LANCZOS``，旧名只是别名、运行时一直
            # 有效（这里要与旧 Pillow 兼容，故保留写法）。
            Image.LANCZOS,  # type: ignore[attr-defined]
        )
    _save_pil(img, img_path, ext)
    return img_path, img.width, img.height
