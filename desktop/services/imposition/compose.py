# -*- coding: utf-8 -*-
"""拼版合成：把版面页摆到底色上、紧裁落盘（PIL，无 Qt）。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）：``compose_page``
管单页、``compose_doc`` 管整轮（持锁 + 清扫）。
"""

from __future__ import annotations

import io
import math
import os
from pathlib import Path

from utils.binary_ink import HARDEN_THRESHOLD as _HARDEN_THRESHOLD
from utils.file_utils import write_bytes_atomic

from desktop.services.imposition.constants import (
    FILE_FMT,
    JPEG_QUALITY,
    TRANSPARENT_BACKGROUND,
    WHITE_BACKGROUND,
    _COMPOSE_LOCK,
    _JPG_SUFFIXES,
    _PRODUCT_SUFFIXES,
)
from desktop.services.imposition.document import (
    is_product_file, normalize_page, page_product_suffix, product_path,
)

# ------------------------------------------------------------------ 合成
#: 「这张源图是不是二值稿」的缓存，key = :func:`source_stamp` 的签名。
#:
#: ⚠️ 拼版合成会被**反复触发**（拖版面时的后台防抖 + 点「生成PDF」前的同步补
#: 一轮），每次都要读同一批源图。尺寸有 ``_SIZE_CACHE`` 同理；这里缓存的是
#: "只有「墨」和「透明」两种像素"这个判据——判一次要扫一遍 alpha，整本几十页
#: 每轮重扫就是白花的时间。签名带 mtime + 字节数，源图被编辑器覆盖后自动失效。
_BINARY_CACHE: dict[tuple[str, int, int], bool] = {}

#: 二值稿的 **alpha 阈值表**：插值出来的半透明边缘压回 0 / 255
#: （分界取 ``utils.binary_ink.HARDEN_THRESHOLD``，与编辑器那一刀同一条）。
_HARDEN_LUT = bytes(
    255 if value >= _HARDEN_THRESHOLD else 0 for value in range(256))


def source_stamp(path) -> tuple[str, int, int] | None:
    """源图的**新鲜度签名**（路径 + mtime_ns + 字节数）；读不到返回 None。"""
    try:
        stat = os.stat(str(path))
    except OSError:
        return None
    return (str(path), int(stat.st_mtime_ns), int(stat.st_size))


def _looks_binary(image) -> bool:
    """这张**已解码的 RGBA 图**是不是二值稿：alpha 只有 0 和 255 两种取值。

    "只有 0 和 255" 就是「有墨 / 无墨」——去底色产物（``rembg``）正是这个形态
    （调色板两项 + tRNS，逐像素是 ``(255,255,255,0)`` 与 ``(0,0,0,255)``）。
    全不透明的扫描件（只有 255）**不算**：它没有"无墨"这一态。

    ⚠️ 规则本体在 :func:`utils.binary_ink.ink_only_levels`（编辑器烘焙前用的是
    同一条，只是输入是 QImage）；这里只负责"用 getcolors 一趟拿到取值"。
    """
    from utils.binary_ink import ink_only_levels

    try:
        alpha = image.getchannel("A")
    except (ValueError, AttributeError):      # 灰度/L 图没有 alpha 通道
        return False
    colors = alpha.getcolors(maxcolors=2)
    if not colors:
        return False
    return ink_only_levels(color for _count, color in colors)


def is_binary_source(image, path) -> bool:
    """二值稿判据的**带缓存**版本（``image`` 是已经解码好的那张，省一次解码）。"""
    stamp = source_stamp(path)
    if stamp is not None:
        cached = _BINARY_CACHE.get(stamp)
        if cached is not None:
            return cached
    flag = _looks_binary(image)
    if stamp is not None:
        _BINARY_CACHE[stamp] = flag
    return flag


def _harden_alpha(image):
    """把**插值出来的半透明边缘**阈值化回二值（原地改 ``image`` 的 alpha）。

    为什么可以这么做（2026-11-15 体积排查，任务 0006）：

    - 源图是二值稿 ⇒ 成品里出现的中间 alpha **100% 是 resize/rotate 插值发明的**，
      不是原稿信息（实测第 60 页：35% 的墨像素被抹成平均灰度 64 的半透明边）；
    - 不阈值化的话，一张 88KB 的二值源图合成后变成 2MB：8bit RGBA 是 32 位/像素，
      而二值透明页只要 1 位/像素（见 ``utils.compact_png`` 的表）；
    - 阈值化**不动几何、不动位置、不动落点**：只是把"灰边"还原成"有墨/无墨"，
      笔画位置误差 ≤ 1 像素（打印 300DPI 看不出来）。

    代价只有一条：斜边/拉伸边会出现 1 像素台阶（原本是灰渐变的"软边"）。
    对黑白古籍稿来说这是"回到原稿的锐度"，不是降质。
    """
    image.putalpha(image.getchannel("A").point(_HARDEN_LUT))
    return image


def _open_rgba(path: str):
    from PIL import Image

    return Image.open(path).convert("RGBA")


def _trim_to_content(image):
    """裁掉四周**纯透明**的边，返回内容图（无透明边时原样返回）。

    ⚠️ 与 :func:`image_content_bounds` 配套：版面 ``rect`` 按**可见内容**记
    （见 :func:`refresh_rects_for_edited_source`），所以这里必须先把透明留白
    裁掉再 ``resize`` 进 rect——否则整张图（含留白）被硬塞进内容尺寸的框里，
    内容会被压扁变形（用户 2026-10-14 报障：「编辑保存后拼版页图片与虚线框
    错位」，修 rect 时若不同步裁图就会从"框偏大"变成"图被压扁"）。

    整幅不透明时 alpha 通道不透明、``getbbox`` 等于整张 ⇒ 直接返回原图，
    零拷贝、与旧行为完全一致。
    """
    try:
        box = image.getchannel("A").getbbox()
    except Exception:  # noqa: BLE001 - 取不到就按整张处理，不冒险裁内容
        return image
    if box is None:
        return image                        # 全透明：保留原图，不裁成空
    if box == (0, 0, image.width, image.height):
        return image                        # 四边都贴着内容：无需裁
    return image.crop(box)


def _item_box(item: dict) -> tuple[float, float, float, float]:
    """一项的**外接框**（旋转后），返回 (left, top, right, bottom)。

    旋转绕 ``rect`` 中心，所以外接框 = 以中心为准的旋转矩形。用 w/h 与角度
    直接推，不必真的转图。
    """
    x, y, w, h = item["rect"]
    center_x, center_y = x + w / 2.0, y + h / 2.0
    angle = math.radians(float(item.get("rotation") or 0.0))
    box_w = abs(w * math.cos(angle)) + abs(h * math.sin(angle))
    box_h = abs(w * math.sin(angle)) + abs(h * math.cos(angle))
    return (center_x - box_w / 2.0, center_y - box_h / 2.0,
            center_x + box_w / 2.0, center_y + box_h / 2.0)


def page_bounds(page: dict) -> tuple[float, float, float, float]:
    """一页的**内容范围**：所有图外接框的并集（用户说的「图片的四个区域」）。

    没有纸张概念之后，产出图就是这块范围的紧裁——所以用户把图挪远/拉大，
    产出就跟着变大，不会被裁掉。
    """
    boxes = [_item_box(item) for item in (page or {}).get("items") or []
             if item.get("rect")]
    if not boxes:
        return 0.0, 0.0, 0.0, 0.0
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def compose_page(page: dict, background=TRANSPARENT_BACKGROUND):
    """一页拼版 → PIL **RGBA** 图：所有图外接框的紧裁。

    ⚠️ 旋转方向必须与画布一致：``rotation`` 按 **Qt 顺时针**口径存，
    PIL ``rotate`` 是**逆时针**，所以这里取负。两边口径写反的话，画布上
    转 90°、落盘却反向 90°，用户会看到"生成的 PDF 和图里不一样"。

    ⚠️ **底默认是透明的，不铺白**（用户 2026-10-10：白底烙进成品页图后，编辑器
    里统一变换/裁剪全带着白底走，去底图白拼了）。消费方各自处理 alpha：
    PDF 侧 ``functions/print._load_image`` 压平到白纸；编辑器/预览按 RGBA
    显示。⚠️ 返回 **RGBA**，调用方别再 ``convert("RGB")``（透明处会变黑）。
    要**不透明**成品（独立拼图页「导出成品」，2026-10-13 用户）就显式传
    :data:`WHITE_BACKGROUND`——任务流程的默认值不变。

    参数:
        page: 版面页字典（``normalize_page`` 过的口径）。
        background: 画布底色 RGBA 四元组；透明底 :data:`TRANSPARENT_BACKGROUND`
            （默认）或白底 :data:`WHITE_BACKGROUND`。
    """
    from PIL import Image

    left, top, right, bottom = page_bounds(page)
    width = max(1, int(round(right - left)))
    height = max(1, int(round(bottom - top)))
    canvas = Image.new("RGBA", (width, height), tuple(background))
    for item in page.get("items") or []:
        x, y, w, h = item["rect"]
        if w <= 0 or h <= 0:
            continue
        try:
            image = _open_rgba(str(item["file"]))
        except Exception:  # noqa: BLE001 - 单张坏图不该毁掉整页
            continue
        # ⚠️ 判据必须拿**变换前**的源图算（"源图是不是二值稿"和缩放/旋转无关），
        #    阈值化则必须放在 resize/rotate **之后**——灰边正是那两步造出来的。
        binary = is_binary_source(image, str(item["file"]))
        # ⚠️ 先裁掉透明留白再 resize：``rect`` 按**可见内容**记（见
        #    ``refresh_rects_for_edited_source``），不裁的话整张图会被硬塞
        #    进内容尺寸的框里 ⇒ 内容压扁。
        image = _trim_to_content(image)
        image = image.resize((max(1, int(round(w))), max(1, int(round(h)))),
                             Image.Resampling.LANCZOS)
        rotation = float(item.get("rotation") or 0.0)
        if rotation:
            image = image.rotate(
                -rotation, expand=True, resample=Image.Resampling.BICUBIC)
        if binary:
            image = _harden_alpha(image)
        center_x = x + w / 2.0 - left
        center_y = y + h / 2.0 - top
        canvas.alpha_composite(
            image,
            (int(round(center_x - image.width / 2.0)),
             int(round(center_y - image.height / 2.0))),
        )
    return canvas


def _save_page_atomic(image, target: Path) -> None:
    """把一页合成图**原子**写进 ``target``。

    ⚠️ 这是**第二道防线**，别以为有 :data:`_COMPOSE_LOCK` 就够了（实测两者
    各挡一类故障，缺一不可）：

    1. **锁挡的是"线程间打架"**：两个线程同时 ``image.save()`` 同一个
       ``0003.png``，Windows 上后者会撞上前者正开着的文件句柄直接抛
       ``PermissionError``（实测 8 线程并发，老实现必炸）；``_sweep_stale``
       还会在另一线程写到一半时把它 unlink 掉。
    2. **原子写挡的是"进程内也躲不过的"**：写到一半失败/被杀/断电留下的
       **半张 PNG**，mtime 是新的、体积也不为零 —— 第四步「PDF排版」照单
       全收，读出来就是半张图或直接抛解码错。锁救不了这种情况（同一个线程
       自己也会中途挂）。

    做法与项目既有的 JSON / 缩略图缓存一致：同目录临时文件 + ``os.replace``
    （Windows 上还要短暂重试，目标正被 PDF 渲染器打开时会 ``PermissionError``）。

    ⚠️ **编码按目标后缀选**（用户 2026-10-17）：``.png`` 走**紧凑编码**
    （:func:`utils.compact_png.encode_png_compact`，与去底色/编辑器写回同一口径）；
    ``.jpg`` 必须**先白底压平**（JPEG 没有 alpha 通道，透明处不压白会被固化成
    黑色——与 ``thumb_cache_worker.flatten_on_white`` 同一个坑）。

    ⚠️ PNG 为什么必须是紧凑编码（2026-11-15 用户报「拼版后图片大 7 倍」）：
    拼版成品绝大多数是**二值透明页**（源图只有「墨 / 透明」两态），而
    ``image.save(format="PNG")`` 一律按 8bit RGBA（32 位/像素）写，
    1 位/像素的最省形态被丢掉。实测任务 0006 第 60 页 2015KB → 194KB（10.4x），
    整本 91 页 109.8MB → 15.7MB（7.0x；没到 10x 是因为个别页的源图带白纸底、
    不是纯二值，只吃到编码这一层）。
    """
    if Path(target).suffix.lower() in _JPG_SUFFIXES:
        buf = io.BytesIO()
        _flatten_white(image).save(
            buf, format="JPEG", quality=JPEG_QUALITY, subsampling=0,
        )
        write_bytes_atomic(target, buf.getvalue())
        return
    # 调色板/1 位等模式先收敛成 RGB(A)：``encode_png_compact`` 只认像素数组，
    # 直接 ``np.array(P 图)`` 会把调色板索引当灰度值（会画出乱码）。
    if image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGBA")
    import numpy as np

    from utils.compact_png import encode_png_compact

    data, _info = encode_png_compact(np.array(image))
    write_bytes_atomic(target, data)


def _flatten_white(image):
    """把带 alpha 的成品页压到**白底**（返回 RGB）；无 alpha 的图原样返回。

    透明处的语义就是**纸色（白）**——与 PDF 侧 ``functions/print._load_image``
    的压平口径一致，所以 jpg 成品与 png 成品的打印效果相同，只是丢了透明底。
    """
    from PIL import Image

    if image.mode == "RGB":
        return image
    canvas = image if image.mode == "RGBA" else image.convert("RGBA")
    white = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    white.alpha_composite(canvas)
    return white.convert("RGB")


def flatten_onto_background(source, target, background=WHITE_BACKGROUND) -> None:
    """把一张图片（可能带透明）压到指定底色上，原子写出 PNG 到 ``target``。

    用途：独立拼图页「导出成品」时，**手工修饰过的整页组合**（存在
    ``singletask/拼图/edited/`` 的手改缓存，编辑器写出的是 RGBA）不走
    ``compose_page`` 重新合成、而是整张盖回成品——那张图也要与导出口径
    同底色，否则手改页透明、合成页白底，一批成品两种底。

    参数:
        source: 源图片路径（任意 PIL 可读格式）。
        target: 输出 PNG 路径（原子写，见 :func:`_save_page_atomic`）。
        background: 底色 RGBA 四元组，与 :func:`compose_page` 同一口径。
    """
    from PIL import Image

    with Image.open(source) as im:
        im.load()
        rgba = im.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, tuple(background))
    canvas.alpha_composite(rgba)
    # 不透明底直接落 RGB：体积更小，消费方（PDF/看图）也少一层 alpha 分支
    image = canvas if background[3] < 255 else canvas.convert("RGB")
    _save_page_atomic(image, Path(target))


def compose_doc(doc: dict, dest_dir, report=None,
                background=TRANSPARENT_BACKGROUND, suffix_for=None,
                only=None) -> list[Path]:
    """把拼版文档落成 ``dest_dir/0001.png`` …（列表顺序即页序）。

    ``suffix_for``：可选 ``(page) -> ".png" | ".jpg"``——**成品后缀随该页源图走**
    （用户 2026-10-17：「输入是 png 就输出 png，输入是 jpg 就输出 jpg」），任务
    流程传 :func:`page_product_suffix`；**不传则一律 ``.png``**（独立拼图页
    「导出成品」的既有口径：白底 PNG 就是交付物）。

    ``only``（可选）：**只重合成这几页**（0 基页序下标集合，**迭代顺序即写入顺序**）。
    用户 2026-10-18：「不是所有图片都重新存储一份，只存储当前拼版的图片页」——一页
    合成要开两张原图 + 缩放 + 旋转 + alpha + 编码，整本 85 页叠起来就是好几秒，而
    用户刚拖的往往只是其中一页。给 ``None``（默认）= 按文档顺序全量，语义与改造前
    **逐字节一致**。
    ⚠️ 只写给定的页，**清扫照做**（多出来的页号/别的后缀仍要删）——删页/换格式
    这类操作若只写一页却不清理，第四步会把残留的旧页也打进 PDF。
    ⚠️ 顺序有意义：调用方把"用户正看着的那一页"排在前面，全量那一轮也能**先**把
    他改的那页写出来（不必等整本跑完）。

    返回写出的文件列表（顺序与页序一致）。**多余的旧文件会被清掉**——否则
    用户删掉一页后，上一轮多出来的 ``0007.png`` 还会被第四步当成一页打进 PDF。
    只清理本函数自己命名形态的文件（``\\d{4}.png`` / ``\\d{4}.jpg``），
    不碰目录里的别的东西。

    单页合成失败时跳过该页（不写文件），其余页照常。任务目录不存在时
    （任务被删）直接返回空列表。

    ⚠️ 整轮**持 :data:`_COMPOSE_LOCK`**：后台防抖合成与点「生成PDF」前的同步合成
    会打到同一个目录，不串行化就会出现"一个线程在写、另一个在清"——详见该锁
    的注释。

    ``report``：可选的进度回调 ``(done, total)``，每处理完一页调一次（**含
    失败的那页**——它也被处理过了，只是不写文件）。独立拼图页靠它显示进度
    （任务流程里后台防抖那条路不传，用户不需要看）。
    ⚠️ 回调在 :data:`_COMPOSE_LOCK` **内**调用，所以它只许发信号、不许做
    可能重入本模块的事（例如再调一次 ``compose_doc`` 会死锁）。

    ``background``：成品页画布底色，语义与 :func:`compose_page` 一致——
    默认透明底（任务流程：PDF 侧压平白纸、编辑器要透明）；独立拼图页
    「导出成品」显式传 :data:`WHITE_BACKGROUND`（2026-10-13 用户：singletask
    导出的 PNG 就是交付物，不要透明底）。
    """
    dest = Path(dest_dir)
    pages = [
        page for page in (
            normalize_page(raw) for raw in (doc or {}).get("pages") or []
        ) if page is not None
    ]
    wanted = None if only is None else [int(index) for index in only]
    written: list[Path] = []
    with _COMPOSE_LOCK:
        if not pages:
            _sweep_stale(dest, 0)
            return written
        dest.mkdir(parents=True, exist_ok=True)
        total = len(pages)
        # ⚠️ 迭代顺序 = ``only`` 给的顺序（全量时是文档顺序）：调用方把"用户正看着
        #    的那一页"排前面，先写它。
        order = (
            range(total) if wanted is None
            else [index for index in wanted if 0 <= index < total]
        )
        for index in order:
            page = pages[index]
            try:
                image = compose_page(page, background)
            except Exception:  # noqa: BLE001 - 单页失败不影响其余页
                _report_page(report, index + 1, total)
                continue
            target = (
                dest / FILE_FMT.format(index + 1)
                if suffix_for is None
                else product_path(dest, index, page)
            )
            # 同一页号、**别的后缀**的旧成品要先删：格式随源图一变（png↔jpg）
            # 旧文件会留下，第四步把它当成同一页的**第二页**打进 PDF。
            _drop_other_format(dest, index + 1, target.suffix.lower())
            try:
                _save_page_atomic(image, target)
            except OSError as exc:
                # 合成本身没问题、只是写不下去（PDF 正被外部程序打开等）：
                # 记一笔继续下一页，别让整轮拼版白跑。
                print(f"[imposition] 第 {index + 1} 页写盘失败：{exc}")
                _report_page(report, index + 1, total)
                continue
            written.append(target)
            _report_page(report, index + 1, total)
        # ⚠️ 清理基准是**页数**而不是"写成功的文件数"：文件名按页序下标取，
        # 中间某一页合成失败会留下编号空洞（0001 / 0003），按写成功数（2）去清
        # 会**误删 0003**——把一页好内容清掉比留个空洞严重得多。
        # ⚠️ 增量合成（``only``）也要清：删页/换格式留下的残留同样得扫掉。
        _sweep_stale(dest, len(pages))
    return written


def _report_page(report, done: int, total: int) -> None:
    """把"第 done / total 页处理完了"报给可选回调。

    ⚠️ 回调自身抛异常必须吞掉：它是纯旁路（进度显示），带崩合成才是真事故。
    """
    if report is None:
        return
    try:
        report(done, total)
    except Exception:  # noqa: BLE001 - 进度汇报失败绝不能中断合成
        pass


def _sweep_stale(dest: Path, keep: int) -> None:
    """删掉 ``dest`` 里序号大于 ``keep`` 的成品页（``数字.png`` / ``数字.jpg``）。

    ⚠️ 后缀认**两种**（见 :func:`is_product_file`）：格式从 png 切到 jpg（或反之）
    时上一轮多出来的页会**留在盘上**，第四步会把它们当成页打进 PDF。
    """
    if not dest.exists():
        return
    for candidate in dest.iterdir():
        if not is_product_file(candidate):
            continue
        if int(candidate.stem) > keep:
            try:
                candidate.unlink()
            except OSError:
                pass


def _drop_other_format(dest: Path, page_number: int, keep_suffix: str) -> None:
    """删掉**同一页号、别的后缀**的旧成品（``0001.jpg`` 对 ``0001.png``）。

    ⚠️ 这一条与 :func:`_sweep_stale` 分工不同、缺一不可：那个按**页数**清"多出来
    的页"，只管页号 > keep；而"同一页换了格式"（源图从 png 换成 jpg，或反之）
    留下的是**同页号、不同后缀**的文件——第四步会把同一页当成两页打进 PDF。
    """
    for suffix in _PRODUCT_SUFFIXES:
        if suffix == keep_suffix:
            continue
        stale = dest / f"{page_number:04d}{suffix}"
        if stale.is_file():
            try:
                stale.unlink()
            except OSError:
                pass
