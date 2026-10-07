# -*- coding: utf-8 -*-
"""图片拼版的派生与合成规则（纯函数 + PIL，无 Qt 依赖，便于独立测试）。

一句话职责：**把每页的两张源图按版面摆到白底上，落成 ``stages/imposition``
里的成品页图**，供第四步「PDF排版」当整页图片直接用。

三件事在这里定死（别在别处再写一份）：

1. **槽位约定**：一页拼版恒两项，``items[0]`` = **右槽**、``items[1]`` = **左槽**。
   用户口径「序号排前面的在右侧、序号大的在左侧」——所以按源清单顺序取两张
   （序号小的在前）时，序号小的进右槽。
2. **坐标口径**：``rect`` 是**源图像素**，左上原点、x 向右、y 向下；
   ``rotation`` 是**顺时针角度**（Qt 口径；PIL 侧取负），绕该项 ``rect`` 的中心。
3. **没有"纸张"**（用户 2026-09-30：「这个拼版不需要设置纸张，只需要背景是白色的
   就行，后续提交的时候根据图片的四个区域合并出一张图片」）：版面只有白底，
   图可以随意移动/拉伸；**产出图 = 所有图外接框的紧裁**（``page_bounds`` →
   ``compose_page``），所以加多少留白、挪多远，用户自己说了算。
"""

from __future__ import annotations

import io
import math
import re
import threading
from pathlib import Path

from utils.file_utils import write_bytes_atomic

#: 一页拼版固定两项（右槽、左槽）
ITEMS_PER_PAGE = 2

#: 落盘文件名：``0001.png`` …（列表顺序即页序，与第四步列表一致）
FILE_FMT = "{:04d}.png"

#: ``compose_doc`` 的**进程内**互斥锁：按目标目录串行化整轮合成。
#:
#: ⚠️ 为什么需要（用户 2026-10-03 报「程序容易跑崩溃」）：拼版合成有**两条**
#: 路径会打到同一个 ``stages/imposition`` 目录——
#:
#: - 后台防抖合成 ``ImpositionComposeWorker``（拖版面时反复触发）；
#: - 主线程同步合成 ``TaskDetailPage._compose_imposition_now``
#:   （改完版面立刻点「生成PDF」时补一轮）。
#:
#: 原先两条路径**没有任何互斥**：同一个 ``0003.png`` 可能被两个线程同时
#: ``image.save()``（非原子写），第四步 PDF 会读到半张图；更糟的是
#: :func:`_sweep_stale` 会 ``unlink`` 掉序号大的旧文件——一个线程按旧页数
#: 清理、另一个按新页数在写，好内容会被误删。
#:
#: 用**进程内**的模块级锁就够：两条路径都在本进程内（同源），不涉及跨进程。
_COMPOSE_LOCK = threading.Lock()

_CN_DIGITS = "零一二三四五六七八九"


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _rect(value) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return [_num(v) for v in value]


def normalize_page(page) -> dict | None:
    """把任意来源的一页拼版收敛成合法形状；不可修复时返回 None。

    ⚠️ 校验必须严：``rect`` 会直接喂给合成函数当落点，坏值（缺字段、0 宽、
    非数字）会让合成抛异常或产出空图，而这份文档在用户的文档目录里、可被
    外部编辑写坏。

    ⚠️ 老版本存过 ``"sheet": [w, h]``（有纸张的时代）。现在**忽略它**：
    版面以两张图为准，纸张已经不存在了，读老任务照样能合成。
    """
    if not isinstance(page, dict):
        return None
    raw_items = page.get("items")
    if not isinstance(raw_items, (list, tuple)):
        return None
    items: list[dict] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        file_text = str(raw.get("file") or "").strip()
        rect = _rect(raw.get("rect"))
        if not file_text or rect is None or rect[2] <= 0 or rect[3] <= 0:
            continue
        items.append(
            {"file": file_text, "rect": rect,
             "rotation": _num(raw.get("rotation"))}
        )
    if not items:
        return None
    return {"items": items}


def normalize_doc(doc) -> dict:
    """整份文档收敛：``{"enabled", "pages", "removed"}``（永不为 None）。

    ``removed`` 是**黑名单**（用户在「选择拼版」弹窗里删掉的图，软删除——
    文件不动，只是不再进入候选范围）。存字符串路径列表，去重保序；
    读老任务没有这个键时为空列表。
    """
    if not isinstance(doc, dict):
        return {"enabled": False, "pages": [], "removed": []}
    pages = []
    for page in doc.get("pages") or []:
        normalized = normalize_page(page)
        if normalized is not None:
            pages.append(normalized)
    removed: list[str] = []
    seen: set[str] = set()
    raw_removed = doc.get("removed")
    for entry in raw_removed if isinstance(raw_removed, (list, tuple)) else ():
        text = str(entry or "").strip()
        if text and text not in seen:
            seen.add(text)
            removed.append(text)
    return {"enabled": bool(doc.get("enabled")), "pages": pages,
            "removed": removed}


def cn_page_label(index: int) -> str:
    """页序（0 起）→ 中文页码标签：``第一页`` / ``第十二页`` / ``第100页``。

    只覆盖 1~99 的中文写法（古籍拼版页数够用），超出退回阿拉伯数字——
    这里只是**界面文案**，不参与任何匹配，宁可难看也不要写错数字。
    """
    number = int(index) + 1
    if number < 1:
        return f"第{number}页"
    if number > 99:
        return f"第{number}页"
    if number < 10:
        return f"第{_CN_DIGITS[number]}页"
    tens, ones = divmod(number, 10)
    text = ("十" if tens == 1 else f"{_CN_DIGITS[tens]}十")
    if ones:
        text += _CN_DIGITS[ones]
    return f"第{text}页"


# ------------------------------------------------------------------ 源图与槽位
#: 模块级尺寸缓存：拼版反复读同一批源图的尺寸，缓存量级可控。
_SIZE_CACHE: dict[str, tuple[int, int]] = {}


def image_size(path) -> tuple[int, int]:
    """图片像素尺寸（读文件头，不解码整图）；读不到返回 (0, 0)。"""
    key = str(path)
    cache = _SIZE_CACHE
    if key in cache:
        return cache[key]
    try:
        from PIL import Image

        with Image.open(key) as img:
            size = (int(img.width), int(img.height))
    except Exception:  # noqa: BLE001 - 尺寸读不到交给上层判空
        size = (0, 0)
    cache[key] = size
    return size


def used_source_files(doc: dict) -> set[str]:
    """已被任何一页拼版引用的源图（用于算「剩余未被选择拼版的图片」）。"""
    used: set[str] = set()
    for page in (doc or {}).get("pages") or []:
        for item in page.get("items") or []:
            file_text = str(item.get("file") or "")
            if file_text:
                used.add(file_text)
    return used


def remaining_files(files: list, doc: dict) -> list:
    """源清单里**还没被任何拼版页用过、也没被删除**的图片（顺序沿用源清单）。

    「删除」是黑名单（``removed``，弹窗里用户主动移出选择范围的图），
    不是删文件——恢复后重新回到候选范围。
    """
    used = used_source_files(doc) | removed_source_files(doc)
    return [f for f in files if str(f) not in used]


def removed_source_files(doc: dict) -> set[str]:
    """被用户「删除图片」移出选择范围的源图路径集合（软删除黑名单）。"""
    raw = (doc or {}).get("removed")
    if not isinstance(raw, (list, tuple)):
        return set()
    return {str(entry) for entry in raw if str(entry).strip()}


def excluded_files(files: list, doc: dict) -> list:
    """源清单里被删除的图（**按源清单顺序**）——给弹窗的「已删除」视图展示。"""
    removed = removed_source_files(doc)
    return [f for f in files if str(f) in removed]


def page_source_stems(page: dict) -> list[str]:
    """一页拼版两张源图的名字（去扩展名），按槽位顺序（右、左）。"""
    return [
        Path(str(item.get("file") or "")).stem
        for item in (page or {}).get("items") or []
    ]


def default_items(files: list) -> list[dict] | None:
    """两张源图 → **默认并排版面**（各按原始像素，不改动用户的图）。

    ``files`` 顺序即槽位顺序 ``[右槽, 左槽]``：左槽贴 x=0，右槽紧挨在它右边，
    两者顶部对齐。古籍一页的两半通常同尺寸，摆出来就是标准对开。

    尺寸读不到 / 少于两张时返回 None（调用方负责提示）。
    """
    if len(files) < ITEMS_PER_PAGE:
        return None
    sizes = [image_size(f) for f in files[:ITEMS_PER_PAGE]]
    if any(w <= 0 or h <= 0 for w, h in sizes):
        return None
    right_file, left_file = str(files[0]), str(files[1])
    (right_w, right_h), (left_w, left_h) = sizes
    return [
        # 右槽：序号在前 → 排在左侧那张的右边
        {"file": right_file, "rect": [float(left_w), 0.0, float(right_w),
                                      float(right_h)], "rotation": 0.0},
        # 左槽：序号在后 → 贴最左
        {"file": left_file, "rect": [0.0, 0.0, float(left_w), float(left_h)],
         "rotation": 0.0},
    ]


def make_page(sources: list) -> dict | None:
    """按**源清单顺序**取两张图造一页拼版版面。

    ``sources`` 顺序即源清单顺序（序号小在前）；本函数把 ``sources[0]``
    放进**右槽**、``sources[1]`` 放进**左槽**——这就是用户的口径
    「序号排前面的在右侧，序号大的在左侧」。版面本身见 ``default_items``。
    """
    items = default_items(sources)
    if items is None:
        return None
    return {"items": items}


def single_items(file) -> list[dict] | None:
    """一张源图 → **单图版面**（整幅图 / 落单图专用：原始像素、不旋转）。

    尺寸读不到返回 None（调用方负责跳过 / 提示）。
    """
    width, height = image_size(file)
    if width <= 0 or height <= 0:
        return None
    return [{"file": str(file), "rect": [0.0, 0.0, float(width), float(height)],
             "rotation": 0.0}]


def make_single_page(file) -> dict | None:
    """一张源图**自成一页**（整幅不拼、落单）：版面里只有一项。"""
    items = single_items(file)
    if items is None:
        return None
    return {"items": items}


def append_item_to_page(items: list[dict], file) -> list[dict] | None:
    """单图页「新增图片」：把 ``file`` 并进当前页，返回**新的 items**。

    槽位与摆放口径（用户 2026-09-30：单图页可以再导一张图拼成对页）：

    - 原图是**左半幅**（文件名 ``-l``/``_l`` 结尾）→ 新图进**右槽**
      （``items[0]``），摆在原图**右边**；
    - 其余（右半幅 / 整幅 / 无后缀）→ 新图进**左槽**（``items[1]``），
      摆在原图**左边**；
    - 新图按**原始像素**进版面、顶边与原图对齐、紧贴原图边缘（用户可再
      拖动/缩放）；原图的版面（位置/大小/旋转）**原样保留**，不重排。

    ``items`` 不是恰好一项（只有单图页能加图）或尺寸读不到时返回 None，
    调用方负责提示。
    """
    if len(items) != 1:
        return None
    existing = dict(items[0])
    ex_x, ex_y, ex_w, _ex_h = (float(v) for v in existing["rect"])
    fresh = single_items(file)
    if fresh is None:
        return None
    new_w, new_h = fresh[0]["rect"][2], fresh[0]["rect"][3]
    new_item = {
        "file": str(file),
        "rect": [0.0, ex_y, float(new_w), float(new_h)],
        "rotation": 0.0,
    }
    if classify_source(existing["file"]) == SOURCE_LEFT:
        # 原图是左半幅：新图进右槽，贴在原图右边
        new_item["rect"][0] = ex_x + ex_w
        return [new_item, existing]
    # 其余：新图进左槽，贴在原图左边
    new_item["rect"][0] = ex_x - new_w
    return [existing, new_item]


# ------------------------------------------------------------------ 自动拼版
#: 源图形态（``classify_source`` 的返回值）。
SOURCE_LEFT = "left"    # 左半幅：文件名以 ``-l`` / ``_l`` 结尾
SOURCE_RIGHT = "right"  # 右半幅：文件名以 ``-r`` / ``_r`` 结尾
SOURCE_FULL = "full"    # 整幅：无 -l/-r 后缀（fullcontent 页在 area=1 下
#                          不拆半幅，第三步提交产物就是无后缀单文件）


def classify_source(path) -> str:
    """源图形态：左半幅 / 右半幅 / 整幅（**判据唯一处：文件名后缀**）。

    自动拼版只能靠文件名认图——拼版侧读不到检测框，而第三步的落盘口径是
    半幅页 ``<页号>-l`` / ``<页号>-r``、整幅页 ``<页号>``（见
    ``functions/text_region._area1_outputs`` 与单图输出）。
    """
    match = re.search(r"[_-]([lr])$", Path(str(path)).stem.lower())
    if match:
        return SOURCE_LEFT if match.group(1) == "l" else SOURCE_RIGHT
    return SOURCE_FULL


def source_page_number(path) -> int | None:
    """源图**页号**：文件名开头的连续数字（``3-r`` → 3、``004-l`` → 4）。

    「不连续的图片不可以合并在一页」的判据。文件名不带数字前缀的图
    （如 ``cover``）返回 None——永不参与配对，只能单独成页。
    """
    match = re.match(r"(\d+)", Path(str(path)).stem)
    return int(match.group(1)) if match else None


def auto_impose_pages(files: list) -> list[dict]:
    """自动拼版（用户 2026-09-30 规则，**唯一实现**）：

    1. **默认两张半栏拼一页**：配对必须是「前一个左半幅 + 当前右半幅」
       （序号在前的进右槽，与手动配对口径一致）。例：``3-r, 3-l, 4-r,
       4-l, 5-r`` 从 ``3-l`` 起 → ``(3-l, 4-r)、(4-l, 5-r)``；从 ``3-r``
       起 → ``[3-r]、(3-l, 4-r)、(4-l, 5-r)``（首位右半幅前面没有左半幅，
       单独一页）；
    2. **页号必须连续**：不连续的图片不可以合并在一页——``3-l`` 之后隔着
       已用掉的 4 直接来 ``5-r``，则 ``3-l`` 单独一页、``5-r`` 重新开始；
       文件名无数字前缀的图永不配对；
    3. **整幅(fullcontent)标注的图单独一页**，不与任何图配对；等配对的
       上一张因此落单、也单独一页；整幅之后拼版重新开始；末尾落单的
       左半幅同样单独一页。

    遍历按源清单顺序（``pdf_custom_sort_key``：同页号 r 在前），产出的
    页清单顺序即 PDF 页序。尺寸读不到的图跳过（不产出残页）。
    """
    pages: list[dict] = []
    pending: str | None = None   # 等待配对的上一张（右槽候选）
    pending_no: int | None = None  # pending 的页号（连续性判据）
    for raw in files:
        file = str(raw)
        kind = classify_source(file)
        no = source_page_number(file)
        if kind == SOURCE_FULL:
            if pending is not None:
                page = make_single_page(pending)
                if page is not None:
                    pages.append(page)
                pending = None
                pending_no = None
            page = make_single_page(file)
            if page is not None:
                pages.append(page)
            continue
        if (pending is not None
                and classify_source(pending) == SOURCE_LEFT
                and kind == SOURCE_RIGHT
                and pending_no is not None
                and no == pending_no + 1):
            page = make_page([pending, file])
            if page is not None:
                pages.append(page)
            pending = None
            pending_no = None
            continue
        if pending is not None:
            page = make_single_page(pending)
            if page is not None:
                pages.append(page)
        pending = file
        pending_no = no
    if pending is not None:
        page = make_single_page(pending)
        if page is not None:
            pages.append(page)
    return pages


# ------------------------------------------------------------------ 合成
def _open_rgba(path: str):
    from PIL import Image

    return Image.open(path).convert("RGBA")


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


def compose_page(page: dict):
    """一页拼版 → PIL RGB 图：**白底 + 所有图外接框的紧裁**。

    ⚠️ 旋转方向必须与画布一致：``rotation`` 按 **Qt 顺时针**口径存，
    PIL ``rotate`` 是**逆时针**，所以这里取负。两边口径写反的话，画布上
    转 90°、落盘却反向 90°，用户会看到"生成的 PDF 和图里不一样"。

    留白处为白：去底图的透明在此压到白底上（与 ``functions.print`` 加载图片
    时的压平规则一致）。
    """
    from PIL import Image

    left, top, right, bottom = page_bounds(page)
    width = max(1, int(round(right - left)))
    height = max(1, int(round(bottom - top)))
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    for item in page.get("items") or []:
        x, y, w, h = item["rect"]
        if w <= 0 or h <= 0:
            continue
        try:
            image = _open_rgba(str(item["file"]))
        except Exception:  # noqa: BLE001 - 单张坏图不该毁掉整页
            continue
        image = image.resize((max(1, int(round(w))), max(1, int(round(h)))),
                             Image.LANCZOS)
        rotation = float(item.get("rotation") or 0.0)
        if rotation:
            image = image.rotate(-rotation, expand=True, resample=Image.BICUBIC)
        center_x = x + w / 2.0 - left
        center_y = y + h / 2.0 - top
        canvas.alpha_composite(
            image,
            (int(round(center_x - image.width / 2.0)),
             int(round(center_y - image.height / 2.0))),
        )
    return canvas.convert("RGB")


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
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    write_bytes_atomic(target, buf.getvalue())


def compose_doc(doc: dict, dest_dir, report=None) -> list[Path]:
    """把整份拼版文档落成 ``dest_dir/0001.png`` …（列表顺序即页序）。

    返回写出的文件列表（顺序与页序一致）。**多余的旧文件会被清掉**——否则
    用户删掉一页后，上一轮多出来的 ``0007.png`` 还会被第四步当成一页打进 PDF。
    只清理本函数自己命名形态的文件（``\\d{4}.png``），不碰目录里的别的东西。

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
    """
    dest = Path(dest_dir)
    pages = [
        page for page in (
            normalize_page(raw) for raw in (doc or {}).get("pages") or []
        ) if page is not None
    ]
    written: list[Path] = []
    with _COMPOSE_LOCK:
        if not pages:
            _sweep_stale(dest, 0)
            return written
        dest.mkdir(parents=True, exist_ok=True)
        total = len(pages)
        for index, page in enumerate(pages):
            try:
                image = compose_page(page)
            except Exception:  # noqa: BLE001 - 单页失败不影响其余页
                _report_page(report, index + 1, total)
                continue
            target = dest / FILE_FMT.format(index + 1)
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
    """删掉 ``dest`` 里序号大于 ``keep`` 的 ``数字.png``（上一轮多出来的页）。"""
    if not dest.exists():
        return
    for candidate in dest.iterdir():
        stem = candidate.stem
        if candidate.suffix.lower() != ".png" or not stem.isdigit():
            continue
        if int(stem) > keep:
            try:
                candidate.unlink()
            except OSError:
                pass
