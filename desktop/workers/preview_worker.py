# -*- coding: utf-8 -*-
"""PDF/图片渲染：整页大图、页缩略图（带磁盘缓存）与去底色效果合成。

区域合成（rembg 预览）在本线程内完成，避免主线程处理原始分辨率大图导致卡顿。
"""

from __future__ import annotations

import atexit
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QPointF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QFontMetrics, QPainter

from utils.box_geometry import (
    build_output_layout,
    build_symmetric_layout,
    parse_border_mm,
)
from desktop.utils.files import THUMBNAIL_EDGE
from utils.file_utils import write_bytes_atomic


def region_canvas_specs(
    image_size: tuple[int, int], boxes: list, area: int, border_mm,
    dpi: int = 300,
) -> list:
    """compose_region_output 的**纯几何**部分：返回 ``[(画布尺寸, sources)]``。

    不碰位图——只依据图片**尺寸**（QImageReader 读文件头即可拿到）就能
    算出每张输出画布的大小与贴图来源。第三步提交据此**预先算好输出
    文件名**（张数 × 名称），再并行处理各页；规则仍然只有这一份。
    """
    W, H = image_size
    present = [list(b) for b in boxes if b]
    if not present:  # 无检测框：整页原图
        return [((W, H), [])]
    padding = parse_border_mm(border_mm, dpi)
    if len(present) == 1 and padding is not None and area in (2, 3):
        layout = build_symmetric_layout(
            box=present[0],
            border_padding=padding,
            image_size=(W, H),
            is_left=True,  # 内容置于左半，右半为空白镜像
            dpi=dpi,
        )
    else:
        layout = build_output_layout(
            boxes=present,
            area=area,
            border_padding=padding,
            image_size=(W, H),
            dpi=dpi,
        )
    return [(canvas_spec.size, canvas_spec.sources) for canvas_spec in layout.canvases]


def compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int = 300) -> list:
    """按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

    **几何规则来自 utils.box_geometry**（与 functions/text_region.py 的 CLI
    输出共用同一份实现），本函数只负责用 QImage 把布局画出来——这样规则
    不会因数像素后端不同而被复制成两份。几何部分见 `region_canvas_specs`。

    与原实现的一处行为修正：area=3 + 双框 + border=None 时，并集区域现在
    **写回原位置**（此前被搬到画布左上角）。规格见
    docs/functions/cropremove.md:57「area=3 → 单图，ROI 写回原位置」。
    """
    W, H = image.width(), image.height()
    specs = region_canvas_specs((W, H), boxes, area, border_mm, dpi)
    result = []
    for size, sources in specs:
        canvas = QImage(max(size[0], 1), max(size[1], 1), QImage.Format_RGB32)
        canvas.fill(Qt.white)
        for source, ox, oy in sources:
            x1, y1, x2, y2 = source
            sx1, sy1 = max(0, x1), max(0, y1)
            sx2, sy2 = min(W, x2), min(H, y2)
            if sx2 > sx1 and sy2 > sy1:
                painter = QPainter(canvas)
                painter.drawImage(
                    ox + sx1 - x1,
                    oy + sy1 - y1,
                    image,
                    sx1,
                    sy1,
                    sx2 - sx1,
                    sy2 - sy1,
                )
                painter.end()
        result.append(canvas)
    return result


# 打印效果预览的基准分辨率：让整页落在 ~1600px 长边，既能看清标题/页码
# 又不至于为一张预览图分配几十 MB
PRINT_PREVIEW_TARGET_EDGE = 1600
PRINT_PREVIEW_MIN_PX_PER_MM = 2.0
PRINT_PREVIEW_MAX_PX_PER_MM = 8.0

#: 渲染一页缩略图之后让出 GIL 的比例（让出时间 = 刚花掉的时间 × 这个值）。
#: PyMuPDF 渲染 5000×4400 的扫描页约 160ms 且**几乎全程持有 GIL**：不让出时
#: GUI 主线程只能捡到 ~2% 的时间片（实测另一线程 1ms 心跳被拖到 175ms，界面
#: 就是"卡死"）。0.5 换来约 1/3 的时间片给界面，代价是缩略图整体慢约 50%
#: ——它是纯后台活，而界面卡住是用户直接能感觉到的。
THUMB_YIELD_RATIO = 0.5


# --------------------------------------------------------------- 共享文档缓存
# ⚠️ 为什么同一本 PDF 只打开一次（2026-09-25，修「切缩略图卡、多点几下卡死」）
#   此前每次单页渲染都 `fitz.open(整本 832MB)` → 渲一页 → close。用户每点
#   一次缩略图就是一次完整的打开+渲染，而且**每次点击各起一个线程**：连点
#   N 下就有 N 个渲染线程同时攥着 GIL（每页 ~105ms），主线程捡不到时间片，
#   整个界面冻住——"多点几下程序卡死"就是 N 份渲染叠出来的。
#   现在两件事一起做：
#   1. `_PDF_DOC_CACHE` 让同一文档保持打开、跨请求复用（LRU，最多 2 本）；
#   2. `single_flight()`（见 `render_lock`）让**全进程同一时刻最多一个**页渲染
#      在跑——排队的线程睡在锁上（不烧 CPU 不抢 GIL），主线程只在真正渲染的
#      ~105ms 里被捏一下，之后立刻恢复。配合 pdf_viewer 的过期请求丢弃
#      （is_stale），排队的陈旧点击根本不会渲染。
#: 共享文档缓存的容量（本）。第二本是给放大弹窗换 PDF 场景的余量。
_PDF_DOC_CACHE_MAX = 2
#: 路径 → 已打开的 fitz.Document（LRU，最近用的在队尾）
_PDF_DOC_CACHE: "OrderedDict[str, object]" = OrderedDict()
# 单页渲染的全局互斥锁：同时只允许一个渲染使用共享文档（fitz.Document
# 不是线程安全的，且渲染全程攥 GIL，多线程并行只会互相拖慢 + 冻住界面）。
# ⚠️ 锁本体已挪到 `desktop/workers/render_lock.py`（零依赖小模块）：**批量
# 缩略图与导入后台任务也要共用同一把**，而它们不能从本模块 import——那会把
# 第四步预览的整套依赖拖进启动路径（见 workers/__init__.py 的惰性导出）。
from desktop.workers.render_lock import single_flight  # noqa: E402  (位置即说明)


def close_cached_documents() -> None:
    """关掉共享文档缓存里的全部文档，释放 Windows 文件句柄。

    ⚠️ 删除任务/关闭文档前必须调用：缓存里的 Document 一直握着 PDF 文件，
    Windows 上不先关掉，`rmtree` 会一直 PermissionError（store 的重试兜底
    救不了"永远不关"的句柄）。会等到当前正在跑的那次渲染结束（≤几百 ms）。
    """
    with single_flight():
        while _PDF_DOC_CACHE:
            _key, document = _PDF_DOC_CACHE.popitem()
            try:
                document.close()
            except Exception:  # noqa: BLE001 - 关不掉就留给进程退出回收
                pass


# 解释器退出前把文档关干净：PyMuPDF 的 Document 活过 fitz 模块自身的
# 清理阶段会在 C 层崩（0xC0000409 之类），atexit 保证先于模块回收执行。
atexit.register(close_cached_documents)


def _get_shared_document(path: Path):
    """取（或打开）共享文档。**必须在 ``single_flight()`` 内调用**。

    fitz.Document 非线程安全，但"持锁串行使用"是安全的——同一时刻只有一个
    线程在碰它。命中缓存直接复用（这正是本缓存的意义：省掉每点一次就重新
    解析 832MB xref 的开销），未命中才打开并插入 LRU。
    """
    key = str(path)
    document = _PDF_DOC_CACHE.pop(key, None)
    if document is not None:
        _PDF_DOC_CACHE[key] = document  # 挪到队尾（最近使用）
        return document
    import fitz

    document = fitz.open(key)
    _PDF_DOC_CACHE[key] = document
    while len(_PDF_DOC_CACHE) > _PDF_DOC_CACHE_MAX:
        _old_key, old_document = _PDF_DOC_CACHE.popitem(last=False)
        try:
            old_document.close()
        except Exception:  # noqa: BLE001
            pass
    return document


def preview_px_per_mm(page_w_mm: float, page_h_mm: float,
                      target_edge: int = PRINT_PREVIEW_TARGET_EDGE) -> float:
    """按纸张尺寸给出效果预览的像素密度（px/mm）。"""
    longest = max(float(page_w_mm), float(page_h_mm))
    if longest <= 0:
        return PRINT_PREVIEW_MIN_PX_PER_MM
    value = target_edge / longest
    return max(PRINT_PREVIEW_MIN_PX_PER_MM,
               min(PRINT_PREVIEW_MAX_PX_PER_MM, value))


def _pick_font(candidates, point_size: float) -> QFont:
    """从给定族名候选里挑第一个系统真装了的；都没命中则交给 Qt 兜底。

    ⚠️ 别用裸 `QFont()`：它落到平台的 generic "Sans Serif" 上，在离屏
    （`QT_QPA_PLATFORM=offscreen`）或字体缺失的环境里中文会渲染成空心
    方框；而且它的字宽度量恰好等于字号，横向文字的占宽会被严重高估。
    """
    from PySide6.QtGui import QFontDatabase

    available = set(QFontDatabase.families())
    for candidate in candidates:
        if candidate in available:
            font = QFont(candidate)
            break
    else:
        font = QFont()
    font.setPointSizeF(max(1.0, float(point_size)))
    return font


def _pick_preview_font(point_size: float) -> QFont:
    """**界面**文字（效果预览的边距标注等）用的字体：走界面族名候选。"""
    from utils.fonts import cjk_font_families

    return _pick_font(cjk_font_families(), point_size)


#: 字体文件 → Qt 族名的缓存。``addApplicationFont`` 每次调用都会再占一个
#: 字体 id，重复加载同一个文件纯属浪费；而且 worker 线程每次都去加载会让
#: 预览刷新明显变卡。
_QT_FONT_FILES: dict[str, str | None] = {}


def qt_family_for_file(path: str) -> str | None:
    """按**字体文件**加载并取回 Qt 族名；失败返回 None。

    为什么要按文件而不是按族名：PDF 侧（`utils.pdf_draw.build_font_chain`）
    也是按文件注册字体的，两边用同一个文件才能保证「预览 = 成品」。按族名
    查表在离屏/精简环境下会落空（那时 `QFontDatabase.families()` 几乎是
    空的），预览就退回默认字体，与成品对不上。
    """
    key = str(path)
    if key in _QT_FONT_FILES:
        return _QT_FONT_FILES[key]
    family: str | None = None
    try:
        from PySide6.QtGui import QFontDatabase

        font_id = QFontDatabase.addApplicationFont(key)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    except Exception:
        family = None
    _QT_FONT_FILES[key] = family
    return family


def _pick_content_font(point_size: float, preferred=None) -> QFont:
    """**PDF 内容**（标题 / 页码）用的字体：**仿宋优先**，可被指定覆盖。

    ``preferred`` 是用户选的字体（显示名 / 路径 / 文件名），能解析到真实文件
    时按**该文件**加载——与 PDF 侧同一个文件，预览与成品才对得上；解析不到
    （本机没这个字体）就回落到自动候选，不会因为一条配置失效而预览不出来。

    必须与 `pdf_draw.register_fonts` 实际选中的字体对齐——那一侧按**文件路径**
    取（Windows 上命中 simfang.ttf = 仿宋），这一侧若按界面候选（雅黑打头）
    取，就会出现「预览是雅黑、导出是仿宋」，所见即所得直接破掉。
    """
    from utils.fonts import content_font_families, resolve_chain

    # ⚠️ 一律**按文件**加载，与 PDF 侧 `build_font_chain` 的链首是同一个
    # 文件——这是「预览 = 成品」唯一可靠的保证。早先默认走族名查表
    # （content_font_families），离屏/精简环境下 `QFontDatabase.families()`
    # 里根本没有那些族，QFont 静默落到 "Sans Serif"，预览与成品对不上。
    chain = resolve_chain(preferred)
    if chain:
        family = qt_family_for_file(chain[0].path)
        if family:
            font = QFont(family)
            font.setPointSizeF(max(1.0, float(point_size)))
            return font
    return _pick_font(content_font_families(), point_size)


#: 1pt = 25.4/72 mm。字体像素大小必须走「pt → mm → px」这条换算，
#: 不能直接用 setPointSizeF——见 ``preview_text_font`` 的说明。
MM_PER_PT = 25.4 / 72.0


def preview_text_font(spec, px_per_mm: float) -> QFont:
    """按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。

    字体族走 ``_pick_content_font``（内容是标题 / 页码，仿宋优先）——与
    ``pdf_draw.register_fonts`` 取到的字体同一种，预览与成品才对得上。

    ⚠️ 不能直接用 ``setPointSizeF(spec.font_size_pt)``：那是固定像素大小，
    而逐字步进是 ``char_h_mm × px_per_mm``（随密度缩放）。两处口径不同时，
    密度一变小（第四步版面编辑画布把整页缩到可视区，≈2 px/mm，远小于效果
    预览的 ≈5.4 px/mm），字仍是原大小、步进却按比例缩小 → **字叠在一起**。

    统一口径后：字高 = 字号(mm) × 密度，与步进同源，任何密度下都不重叠，
    且与成品 PDF 的真实字号（pt → mm）一致。

    ``spec.font`` 是用户为这段文字（标题 / 页码各自独立）指定的字体，
    能解析到文件就按文件加载——与成品 PDF 用同一个字体文件。
    """
    font = _pick_content_font(float(spec.font_size_pt), getattr(spec, "font", None))
    font.setPixelSize(
        max(1, int(round(float(spec.font_size_pt) * MM_PER_PT * px_per_mm)))
    )
    return font


def _draw_print_text(painter: QPainter, spec, px_per_mm: float) -> None:
    """按 PrintTextSpec 画一段文字（竖排逐字、横排整串）。

    坐标与 ``functions/print.py`` 的 fpdf 调用一一对应：fpdf 的
    ``pdf.text(x, y, ch)`` 与 QPainter 的 ``drawText(QPointF)`` 都以
    **基线**为 y，所以这里可以直接复用同一批毫米数——这也是效果预览
    与成品 PDF 不会漂移的原因。

    竖排的分段来自 `utils.page_layout.vertical_runs`（与 fpdf 那边同一份）：
    宽字符一字一格，ASCII 段**整体旋转 90°**（`Happiness` 不会拆成九格）。
    """
    from utils.page_layout import vertical_chunk_advance_mm, vertical_runs

    painter.setFont(preview_text_font(spec, px_per_mm))
    color = spec.color or (0, 0, 0)
    painter.setPen(QColor(int(color[0]), int(color[1]), int(color[2])))
    x = spec.x_mm * px_per_mm
    if spec.vertical:
        char_h_mm = float(spec.char_h_mm)
        step = char_h_mm * px_per_mm
        metrics = QFontMetrics(painter.font())
        y = spec.y_start_mm * px_per_mm
        for chunk, rotated in vertical_runs(spec.text):
            if rotated:
                # 以列位置为基线旋转 90°（Qt 的 rotate 正角即顺时针），
                # 与 fpdf 的 `pdf.rotation(90, x, y)` 同义：字头朝右、自上而下
                painter.save()
                painter.translate(x, y)
                painter.rotate(90)
                painter.drawText(QPointF(0.0, 0.0), chunk)
                painter.restore()
                # ⚠️ 旋转段步进用当前字体实测串宽（与 fpdf 的
                # get_string_width 同一口径，见 utils/pdf_draw.py）：
                # LATIN_ADVANCE_RATIO 估算对数字/下划线长段会高估约
                # 1 个字高，旋转段与后续汉字之间出现空隙。
                latin_width_mm = metrics.horizontalAdvance(chunk) / px_per_mm
            else:
                for index, char in enumerate(chunk):
                    painter.drawText(QPointF(x, y + index * step), char)
                latin_width_mm = None
            y += (
                vertical_chunk_advance_mm(
                    chunk, char_h_mm, rotated, latin_width_mm
                )
                * px_per_mm
            )
        return
    baseline = spec.baseline_mm
    if baseline is None:  # 兜底：无基线时按"顶部 + 1 字高"处理
        baseline = spec.y_start_mm + spec.char_h_mm
    painter.drawText(QPointF(x, baseline * px_per_mm), spec.text)


def compose_print_page(
    image: QImage,
    plan,
    px_per_mm: float | None = None,
) -> QImage:
    """按 ``utils.page_layout.PrintPagePlan`` 合成"打印效果"位图。

    **只画内存位图，不写任何文件**——第四步的效果预览就是它；真正生成
    PDF 仍要走「生成 PDF」按钮（functions/print.py）。

    几何全部取自 ``plan``，而 ``plan`` 由 PDF 生成与预览共用，所以用户
    按预览调好的边距/纸张/标题，与最终 PDF 必然一致。
    """
    density = px_per_mm or preview_px_per_mm(plan.page_w_mm, plan.page_h_mm)
    img_w_mm, img_h_mm = plan.image[2], plan.image[3]
    if not image.isNull() and img_w_mm > 0 and img_h_mm > 0:
        # 密度**不得超过源图原生密度**：再往上就是把源图凭空放大（只会更糊），
        # 还白占内存。宿主会给很大的 target_edge（弹窗 4000），小图（1200px
        # 的扫描件）必须在这里被夹住。
        density = min(
            density, image.width() / img_w_mm, image.height() / img_h_mm
        )
    page_w = max(1, round(plan.page_w_mm * density))
    page_h = max(1, round(plan.page_h_mm * density))
    page = QImage(page_w, page_h, QImage.Format_RGB32)
    if plan.skipped:
        # 命中 skip_pages：成品里没有这一页，预览给一张留白的灰页，
        # 明确告诉用户"这页不会输出"
        page.fill(QColor("#eceff3"))
        painter = QPainter(page)
        painter.setPen(QColor("#98a2b3"))
        painter.setFont(_pick_preview_font(14))
        painter.drawText(page.rect(), Qt.AlignCenter, "该页已跳过，不会输出到 PDF")
        painter.end()
        return page
    page.fill(Qt.white)
    painter = QPainter(page)
    x_mm, y_mm, w_mm, h_mm = plan.image
    target_w = max(1, round(w_mm * density))
    target_h = max(1, round(h_mm * density))
    if target_w > 0 and target_h > 0 and not image.isNull():
        scaled = image.scaled(
            target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        painter.drawImage(round(x_mm * density), round(y_mm * density), scaled)
    for spec in (plan.title, plan.page_number):
        if spec is not None:
            _draw_print_text(painter, spec, density)
    painter.end()
    return page


def compose_outputs_horizontal(outputs: list, gap: int = 12) -> QImage:
    """多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。"""
    if not outputs:
        return QImage()
    if len(outputs) == 1:
        return outputs[0]
    height = max(c.height() for c in outputs)
    total_w = sum(c.width() for c in outputs) + gap * (len(outputs) - 1)
    out = QImage(total_w, height, QImage.Format_RGB32)
    out.fill(Qt.darkGray)
    painter = QPainter(out)
    offset_x = 0
    for crop in outputs:
        painter.drawImage(offset_x, (height - crop.height()) // 2, crop)
        offset_x += crop.width() + gap
    painter.end()
    return out


class PreviewWorker(QObject):
    """渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。"""

    finished = Signal(int, QImage, str)
    metadata = Signal(int, str)
    thumbnail_ready = Signal(int, QImage)
    completed = Signal()
    failed = Signal(int, str)
    #: 请求在真正渲染前被判定为过期（用户已点了别的页），什么都没渲染。
    #: 宿主据此结束线程即可，不要当错误处理。
    skipped = Signal()

    def __init__(
        self,
        path: Path,
        page: int = 0,
        longest_edge: int | None = 1200,
        thumbnails: bool = False,
        cache_dir: Path | None = None,
        effect: dict | None = None,
        print_spec: dict | None = None,
        render_missing: bool = True,
        pages: list[int] | None = None,
    ):
        """构造预览渲染 worker。

        PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
        thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
        effect 为去底色合成参数 {boxes, area, border}，仅对单图生效。
        print_spec 为第四步「打印效果」参数
        {"args": print 参数, "index": 0-based 页序, "total": 总页数, "name": 文件名}，
        非空时把图片按 utils.page_layout 的几何排进一张纸（仅内存，不落盘）；
        另可给 "target_edge"：按该边长反推像素密度**重新排版**（标题/页码是
        重新绘制的，放到 4000px 依然锐利）。⚠️ 这个密度应当**高于屏幕需求**
        （超采样）——Qt 一次大比例缩小的质量明显差于分两档温和缩放，实测
        「合成 3000px」的锐度接近理论理想，而「合成 = 显示尺寸」反而最糊。
        密度的上限由 compose_print_page 夹住（不超过源图原生密度）。
        ⚠️ 给了 target_edge 时，longest_edge 应传 0（画布已按该密度合成，
        再缩一次纯粹白扔细节）。

        `render_missing=False`：**只读缓存，不渲染缺页**。给「另一个生产者
        正在填这个缓存目录」的场景用（导入后台任务在逐页写缩略图）——两边
        各跑一遍全量渲染等于把工作量翻倍，而且两个 PyMuPDF 循环会互相抢
        GIL，界面直接冻住（2026-09-25 实测）。
        `pages`：只处理这些页（None = 全部）；配合 render_missing=False 就是
        「只把我还没有的那几页从缓存里读出来」。
        """
        super().__init__()
        self.path = path
        self.page = page
        self.longest_edge = longest_edge
        self.thumbnail_edge = THUMBNAIL_EDGE
        self.thumbnails = thumbnails
        self.cache_dir = Path(cache_dir) if cache_dir else None
        # 去底色效果合成参数：{"boxes": [[x1,y1,x2,y2],...], "area": int, "border": str|None}
        self.effect = effect
        self.print_spec = print_spec
        self.render_missing = render_missing
        self.pages = list(pages) if pages is not None else None
        #: 最近一次 PDF 单页渲染的 JPEG 字节（供宿主做页间缓存，见 _render_pdf_page）
        self.last_jpeg: bytes | None = None
        #: 宿主提供的"这条请求是否已过期"回调（如：用户已经点了别的页）。
        #: 过期的请求在拿到渲染锁后直接跳过、发 skipped——不渲染、不白烧
        #: 105ms 的 GIL。批量缩略图模式不用它。
        self.is_stale: Callable[[], bool] | None = None
        #: 收尾时置位：批量缩略图在**页边界**退出（见 cancel 与 _render_all_thumbnails）
        self._cancelled = False

    def cancel(self) -> None:
        """请求中止。

        批量缩略图（整本几百上千页）会在**下一页开头**退出——已经渲好的页都已
        落盘，重进会命中缓存，不会白干。单页渲染不可中断（一次 get_pixmap
        只有 ~160ms，等它一下比打断安全）。
        """
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。"""
        try:
            if self.path.suffix.lower() == ".pdf" and self.thumbnails:
                self._render_all_thumbnails()
                return
            if self.path.suffix.lower() == ".pdf":
                image = self._render_pdf_page()
                if image is None:
                    return  # 过期请求：skipped 已发出
            else:
                image = self._load_image()
            self.finished.emit(self.page, image, str(self.path))
        except Exception as exc:
            self.failed.emit(self.page, str(exc))
            if self.thumbnails:
                self.completed.emit()

    def _render_pdf_page(self) -> QImage | None:
        """渲染单页大图；请求过期时发 skipped 并返回 None。

        ⚠️ 全程持 ``single_flight()``：共享文档只能串行使用（非线程安全），
        且渲染本身攥 GIL，多线程并行只会把界面冻死。排队中的线程睡在锁上，
        不烧 CPU；排到锁后先查一次 is_stale——用户在这期间点了别的页，这条
        请求就不必再渲染了。
        """
        import fitz

        if self.is_stale is not None and self.is_stale():
            self.skipped.emit()
            return None
        with single_flight():
            if self.is_stale is not None and self.is_stale():
                self.skipped.emit()
                return None
            document = _get_shared_document(self.path)
            self.metadata.emit(document.page_count, str(self.path))
            page = document.load_page(self.page)
            rect = page.rect
            # longest_edge=0 的语义是「不缩放（要原始分辨率）」。此前直接相除会
            # 得到 scale=0 → **一张空图**，所以调用方都得绕开这个语义；这里显式
            # 处理掉，谁都不用再防。
            scale = (
                self.longest_edge / max(rect.width, rect.height)
                if self.longest_edge
                else 1.0
            )
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            # ⚠️ 顺手留一份 JPEG 字节：宿主（如 PDF 查看器）拿它做**页间缓存**，
            # 命中时只要 QImage.fromData（实测 25ms）而不是重渲（187ms，且渲染
            # 途中攥着 GIL 105ms）。加载图片的路径（_load_image）不经过这里，
            # 缓存只对 PDF 页有效，见 pdf_viewer 的 _page_cache。
            self.last_jpeg = pixmap.tobytes("jpg", jpg_quality=80)
            return QImage.fromData(self.last_jpeg)

    def _render_all_thumbnails(self) -> None:
        """逐页取缩略图：**命中缓存就直接用**，缺页按 ``render_missing`` 决定渲不渲。

        ⚠️ 渲染一页扫描件（5000×4400 的内嵌 JPEG）要 ~160ms，而且 PyMuPDF
        在这 160ms 里几乎一直攥着 GIL（实测另一线程 1ms 的心跳被拖到 175ms）。
        所以：
        1. **别人正在填这个缓存目录时（render_missing=False）一页都不要渲**——
           原先两边各跑一遍全量渲染，工作量翻倍、GIL 互相抢，界面直接冻住；
        2. 真要渲染时**按单页耗时成比例让出 GIL**，否则主线程只拿到 ~2% 的
           时间片（用户看到的正是「导入期间整个界面卡住」）。
        """
        import time

        import fitz

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(
                self.cache_dir / ".meta", str(self.thumbnail_edge).encode("utf-8")
            )
        document = fitz.open(str(self.path))
        try:
            self.metadata.emit(document.page_count, str(self.path))
            order = (
                list(self.pages)
                if self.pages is not None
                else list(range(document.page_count))
            )
            for page_number in order:
                if self._cancelled:
                    # ⚠️ 没有这句时，整本缩略图渲染在收尾时只能"等它跑完"：
                    # 几百上千页 × ~160ms/页，`shutdown_workers` 的 800ms 必然
                    # 超时，线程被摘出父对象后还在后台啃 GIL（2026-09-26 审计）。
                    # 在页边界退出即可——已经渲好的页都落盘了，重进会命中缓存。
                    break
                if not (0 <= page_number < document.page_count):
                    continue
                image = None
                # 命名与导入缩略图一致：1 起始、四位补零（0001.jpg），自然排序
                cache_file = (
                    self.cache_dir / f"{page_number + 1:04d}.jpg"
                    if self.cache_dir
                    else None
                )
                if cache_file and cache_file.exists():
                    image = QImage(str(cache_file))
                if image is None or image.isNull():
                    if not self.render_missing:
                        continue  # 只读通道：缺页交给正在填缓存的那个生产者
                    started = time.perf_counter()
                    # ⚠️ 渲染段也要进**同一把单飞锁**：批量补页与用户的单页
                    # 点击原来是各渲各的，两个 PyMuPDF 渲染并行 = GIL 互相抢。
                    # 逐页进出锁（不是包整批）：用户点一下最多排在**一页**后面
                    # （~160ms），而且让出 GIL 的 sleep 在锁外，排队期间界面照常。
                    with single_flight():
                        page = document.load_page(page_number)
                        rect = page.rect
                        scale = self.thumbnail_edge / max(rect.width, rect.height)
                        pixmap = page.get_pixmap(
                            matrix=fitz.Matrix(scale, scale), alpha=False
                        )
                        data = pixmap.tobytes("jpg", jpg_quality=70)
                    image = QImage.fromData(data)
                    if cache_file:
                        # 原子写：截断的缩略图会被 mtime 判据永久当成有效缓存
                        write_bytes_atomic(cache_file, data)
                    # 让出量与刚花掉的耗时成比例：GUI 拿到约 1/3 的时间片
                    spent_ms = (time.perf_counter() - started) * 1000
                    yield_ms = min(60.0, max(3.0, spent_ms * THUMB_YIELD_RATIO))
                    time.sleep(yield_ms / 1000)
                self.thumbnail_ready.emit(page_number, image)
        finally:
            document.close()
        self.completed.emit()

    def _load_image(self) -> QImage:
        image = QImage(str(self.path))
        if image.isNull():
            raise ValueError("无法读取图片")
        if self.effect:
            outputs = compose_region_output(
                image,
                self.effect.get("boxes", []),
                int(self.effect.get("area", 1)),
                self.effect.get("border"),
            )
            image = compose_outputs_horizontal(outputs)
        if self.print_spec:
            # 打印效果：几何由 utils.page_layout 计算（PDF 生成也是同一份）
            from utils.page_layout import plan_print_page

            plan = plan_print_page(
                (image.width(), image.height()),
                self.print_spec.get("args") or {},
                int(self.print_spec.get("index", 0)),
                int(self.print_spec.get("total", 1)),
                image_name=self.print_spec.get("name"),
                image_rect=self.print_spec.get("rect"),
            )
            # target_edge（放大弹窗用）：按目标边长**反推像素密度**重新排版。
            # ⚠️ 不能只把 compose_print_page 的产物放大了事——它内部固定按
            # preview_px_per_mm（目标 1600px 长边）合成，放大只会糊；按密度
            # 重排则标题/页码是**重新绘制**的，放到 4000px 依然锐利。
            density = None
            target_edge = self.print_spec.get("target_edge")
            if target_edge:
                longest_mm = max(plan.page_w_mm, plan.page_h_mm)
                if longest_mm > 0:
                    density = float(target_edge) / longest_mm
            image = compose_print_page(image, plan, density)
        if not self.longest_edge:
            return image  # 不缩放：调用方需要原始分辨率
        return image.scaled(
            self.longest_edge,
            self.longest_edge,
            aspectMode=Qt.KeepAspectRatio,
            mode=Qt.SmoothTransformation,
        )
