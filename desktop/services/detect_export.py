# -*- coding: utf-8 -*-
"""把「每页的框」画回原图并落盘（**纯函数模块，无 Qt**）。

这一块原本只存在于 CLI 那条路上（``functions.detect`` 的 ``--save``），
独立「检测文本框」模块页要导出同样的标注图时，若在页面里再写一遍，就会
出现两套「按槽位取名/配色」的代码——那正是 :mod:`utils.box_draw` 当初被
抽出来的原因（配色与命名必须处处一致）。所以规则本体在
:func:`utils.box_draw.draw_slots`，本模块只做**遍历 + 落盘**。

⚠️ **重依赖的导入时机**：本模块在**worker 线程**里被 :class:`CallableJob`
调用（见 ``desktop/modules/detect/page.py``），而画框/读写图都要 ``cv2``。
GUI 主进程**绝不能**在这里 import 到 cv2（实测 ``import functions.detect``
会把 cv2 拖进启动路径）——所以 cv2 相关导入全部放进函数内部，让它发生
在子线程里。这也是本模块不 import 任何 Qt 的原因：它必须能被线程安全调用。

输出命名沿用 detect 的口径：``<原文件名去后缀>.png``（全分辨率无损位图，
适合线框标注）。用 ``.png`` 而不是原图的后缀，是因为标注图是**中间核对
产物**，不该让人误以为能替换原图。

**YOLO 数据集切片**（:func:`export_yolo`，用户 2026-10-16）是同一批框的另一种
交付形态：按页序把原图复制成 ``<名称>-1.jpg``、标签写成同名的
``<名称>-1.txt``，一起放进 ``<导出目录>/<名称>/{images,labels}/``（名称同时
是父节点目录名与文件名前缀，默认取任务名/源名）。没有框的页写**空文件**
（负样本）。两类别的映射见 ``utils.box_geometry`` 的 ``YOLO_CLASS_NAMES``
（左框/右框都算 0 号 harfcontent，整幅是 1 号 fullcontent）——那是唯一一份
类别顺序，本模块不重抄。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

from utils.box_geometry import (
    YOLO_CLASS_NAMES,
    YOLO_CLASS_ID_FULL,
    YOLO_CLASS_ID_HARF,
    is_full_content,
)

from desktop.utils.files import copy_file_atomic, safe_dirname

#: 标注图后缀（固定 png，见模块 docstring）
EXPORT_SUFFIX = ".png"

#: YOLO 数据集切片里的两个子目录名（``<dest>/<名称>/images`` 与 ``.../labels``）。
#:
#: ⚠️ 这就是 ultralytics 默认布局：训练配置 ``train: images`` 指的就是
#: ``<数据集根>/images``，标签由它**同名替换**成 ``labels`` 找过去。
YOLO_IMAGES_DIRNAME = "images"
YOLO_LABELS_DIRNAME = "labels"

#: YOLO 标签后缀（归一化文本，一行一个框）。
YOLO_LABEL_SUFFIX = ".txt"

#: 切片自带的**凭据文件**：``<切片>/data.json``（用户 2026-10-16：
#: 「将任务编号写进 b8/data.json 中」）。
#:
#: 用途：切片拷进训练集之后就没有"它从哪来"的线索了，而校验工具
#: （``tools/check_yolo_dataset.py``）要拿基准（``tasks/<任务号>/boxes.json``）
#: 逐框比对——有了它，`python tools/check_yolo_dataset.py <切片>` 一条命令就够，
#: 不必再让用户回忆任务号。
#:
#: ⚠️ 不是 ``data.yaml``（那是 ultralytics 的数据集配置，得由用户按训练集整体
#: 写）；这个 ``data.json`` 只是**本切片的来龙去脉**，ultralytics 不读它。
SLICE_META_NAME = "data.json"


def yolo_dataset_dir(dest, name: str) -> Path:
    """``(导出的父目录, 名称)`` → 这一次导出的数据集切片目录。

    用户 2026-10-16 定的形状（「就是要有个父节点名称」）::

        <dest>/<name>/
            images/<name>-1.jpg     # 原图按页序复制（保留原后缀）
            labels/<name>-1.txt     # 同名标签；没有框的页是空文件（负样本）

    名称同时是**父节点目录名**与**文件名前缀**（一个字段，见设置页与弹窗）。
    按 :func:`desktop.utils.files.safe_dirname` 洗掉非法字符——它要当目录名
    也要当文件名前缀。
    """
    return Path(dest) / safe_dirname(name)


def yolo_entries(images: Sequence, boxes: Mapping[str, Sequence]) -> list:
    """``(图片清单, {页名去后缀: 槽位})`` → :func:`export_yolo` 的入参。

    ⚠️ 与 :func:`entries_from_mapping` 的**唯一区别**：这里**一张不落**。
    没有框的页也要出一份**空标签**当负样本（用户 2026-10-16：「写空标签当
    负样本」）——按"只取有框的页"过滤会把整批的背景页全丢掉，训练出来的模型
    只见过"有内容"的页面。
    """
    entries = []
    for image in images or []:
        key = Path(image).stem
        entries.append((Path(image), list(boxes.get(key) or [])))
    return entries


def yolo_label_lines(slots, image_size) -> Optional[list]:
    """槽位 + 原图尺寸 → YOLO 标签行；**尺寸未知且有框**时返回 ``None``。

    行格式（YOLO detection 的标准形）::

        <类别号> <cx> <cy> <w> <h>      # 四个数都按图宽/图高归一化到 0~1

    - 无框 → 空表（调用方照样写文件，那就是负样本）；
    - 有框、尺寸读不出来（图被删/损坏）→ ``None``：归一化没有基准，只能跳过
      这一页（写空标签等于把"有框的页"谎报成负样本，比跳过更糟）；
    - 类别号取自 ``utils.box_geometry`` 的类别顺序（**左框/右框都算半幅**，
      整幅才是 1 号），本函数不另写数字。
    """
    present = [list(b) for b in (slots or []) if b]
    if not present:
        return []
    if not image_size or int(image_size[0]) <= 0 or int(image_size[1]) <= 0:
        return None
    width, height = int(image_size[0]), int(image_size[1])
    class_id = YOLO_CLASS_ID_FULL if is_full_content(slots) else YOLO_CLASS_ID_HARF
    lines = []
    for box in present:
        x1, y1, x2, y2 = (float(v) for v in box[:4])
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0:
            continue  # 退化框（零面积）：写进去只会污染训练集
        lines.append(
            f"{class_id} "
            f"{_clamp01((x1 + x2) / 2 / width):.6f} "
            f"{_clamp01((y1 + y2) / 2 / height):.6f} "
            f"{_clamp01(bw / width):.6f} "
            f"{_clamp01(bh / height):.6f}"
        )
    return lines


def _clamp01(value: float) -> float:
    """夹到 [0, 1]：YOLO 要求归一化坐标不越界（越界样本会被 ultralytics 丢弃）。"""
    return 0.0 if value < 0 else (1.0 if value > 1 else value)


def _yolo_image_size(path: Path):
    """图片尺寸 ``(宽, 高)``；读不出来返回 ``None``。

    ⚠️ 用 PIL 只读**文件头**（``Image.open`` 是惰性的），不解码整张图——一
    批几百页时按 :func:`utils.imread` 那样全解一遍纯属白烧时间，而标签只需要
    归一化的分母。
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - PIL 是既有依赖（标注图也用它）
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:  # noqa: BLE001 - 单页读不出来不该拖垮整批
        return None


def export_yolo(
    entries: Iterable[tuple],
    dest: Path | str,
    name: str,
    task_id: str = "",
    source: str = "",
    report: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """把一批 ``(图片路径, 槽位)`` 导出成 YOLO 数据集的**一整块切片**。

    参数：

    - ``entries``：``[(图片路径, 槽位), …]``，**应含无框的页**（见
      :func:`yolo_entries`）——列表顺序即导出编号顺序（``<名称>-1``、
      ``<名称>-2``…），调用方按页序给；
    - ``dest``：用户在弹窗里选的**导出目录**（这批切片放它下面）；
    - ``name``：父节点名 = 文件名前缀（弹窗里的「名称」字段）；
    - ``task_id`` / ``source``：来龙去脉，写进切片的 ``data.json``（见
      :data:`SLICE_META_NAME`）。任务流程那条链有任务号，独立页那条链只有源名
      （可以是空串，字段照写）；
    - ``report`` / ``progress``：同 :func:`export_annotated`。

    落点（见 :func:`yolo_dataset_dir`）::

        <dest>/<name>/images/<name>-1.jpg     # 原图复制（保留原后缀）
        <dest>/<name>/labels/<name>-1.txt     # 同名标签；无框 → 空文件（负样本）
        <dest>/<name>/data.json               # 本次导出的凭据（任务号/类别顺序/统计）

    返回统计（供界面写状态行）::

        {"folder": Path, "images": [路径, …], "labels": [路径, …],
         "labeled": 有框页数, "empty": 空标签页数, "skipped": [页名, …],
         "boxes": 写进去的框总数}

    ⚠️ **图片是复制过去的**（用户 2026-10-16 改定，推翻此前"只写标签"）：
    源图随时可能被删/被移走，而训练集必须自包含——图片与标签同名同号地放在
    同一块切片里，直接把它拷进数据集根目录就能训。

    ⚠️ 单页失败（源图被删、读不出尺寸、磁盘写不动）**只跳过这一页**，不中断
    整批：编号仍按它在清单里的位置算，不重排（重排会让"第 7 页"变成别的页，
    对不上原始来源）。
    """
    folder = yolo_dataset_dir(dest, name)
    images_dir = folder / YOLO_IMAGES_DIRNAME
    labels_dir = folder / YOLO_LABELS_DIRNAME
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    written_images: list = []
    written_labels: list = []
    skipped: list = []
    empty = 0
    boxes = 0
    items = list(entries)
    total = len(items)
    for index, entry in enumerate(items):
        # ⚠️ 变量名是 ``image_path`` 而不是 ``source``：后者是**本函数的入参**
        #    （写进 data.json 的来龙去脉），在循环里复用会把它悄悄改成最后一页
        #    的图片路径（真踩过：凭据里写出一串 ``…/0003.png``）。
        image_path, slots = entry[0], entry[1]
        path = Path(image_path)
        number = index + 1
        stem = f"{safe_dirname(name)}-{number}"
        lines = yolo_label_lines(slots, _yolo_image_size(path))
        if lines is None or not path.is_file():
            # 读不出尺寸（图被删/损坏）或源图根本不在：跳过这一页。
            # ⚠️ 不写空标签顶替——那会把"本来有框的页"谎报成负样本。
            skipped.append(path.name)
            if report is not None:
                report(f"跳过 {path.name}：读不到原图或尺寸，无法归一化")
            _report_page(progress, index + 1, total)
            continue
        try:
            image_out = images_dir / f"{stem}{path.suffix.lower()}"
            copy_file_atomic(path, image_out)
            label_out = labels_dir / f"{stem}{YOLO_LABEL_SUFFIX}"
            # 空标签就是**空文件**（YOLO 约定的负样本），照写不误
            label_out.write_text(
                "".join(line + "\n" for line in lines), encoding="utf-8"
            )
        except OSError as exc:
            skipped.append(path.name)
            if report is not None:
                report(f"跳过 {path.name}：{exc}")
            _report_page(progress, index + 1, total)
            continue
        written_images.append(str(image_out))
        written_labels.append(str(label_out))
        if lines:
            boxes += len(lines)
        else:
            empty += 1
        _report_page(progress, index + 1, total)
    labeled = len(written_labels) - empty
    meta = _write_slice_meta(
        folder, name=name, task_id=task_id, source=source,
        total=total, labeled=labeled, empty=empty, boxes=boxes, skipped=skipped,
    )
    if report is not None:
        report(
            f"YOLO 数据集切片完成：{labeled} 页有框（{boxes} 个框）、"
            f"{empty} 页空标签（负样本）→ {folder}"
        )
    return {
        "folder": folder,
        "images": written_images,
        "labels": written_labels,
        "labeled": labeled,
        "empty": empty,
        "skipped": skipped,
        "boxes": boxes,
        "meta": meta,
    }


def _write_slice_meta(
    folder: Path, *, name: str, task_id: str, source: str,
    total: int, labeled: int, empty: int, boxes: int, skipped: list,
) -> dict:
    """把这次导出的**来龙去脉**写进 ``<切片>/data.json``（用户 2026-10-16）。

    有了它，校验工具不必再让用户回忆任务号：
    ``python tools/check_yolo_dataset.py <切片>`` 就能自动找到基准。

    ⚠️ 写它失败**不算导出失败**（数据都已经落盘了）：只往日志说一声。
    """
    meta = {
        "kind": "yolo_dataset_slice",
        "name": safe_dirname(name),
        "task_id": str(task_id or ""),
        "source": str(source or ""),
        "class_names": list(YOLO_CLASS_NAMES),
        "exported_at": time.time(),
        "pages": int(total),
        "labeled": int(labeled),
        "empty": int(empty),
        "boxes": int(boxes),
        "skipped": list(skipped),
    }
    try:
        (folder / SLICE_META_NAME).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        meta["error"] = str(exc)
    return meta


def annotated_name(source: Path | str) -> str:
    """原图路径 → 标注图**文件名**（``<stem>.png``）。"""
    return Path(source).stem + EXPORT_SUFFIX


def export_annotated(
    entries: Iterable[tuple],
    dest: Path | str,
    report: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> list:
    """把一批 ``(图片路径, 槽位)`` 画框后写到 ``dest``。

    参数：

    - ``entries``：``[(图片路径, 槽位), …]``。``槽位`` 是
      :mod:`utils.box_geometry` 的槽位表示（半幅 2 槽 / 整幅 1 槽，缺失侧
      ``None``）；外观（名字与颜色）由 :func:`utils.box_draw.slot_names_colors`
      按**槽位**给，调用方不传也不该自己拼；
    - ``dest``：输出目录，**已存在直接写**（覆盖由调用方与用户确认过，见
      模块页的「目录已存在，是否覆盖」）；
    - ``report``：人读日志回调（``Callable[[str], None]``），每页调一次；
    - ``progress``：结构化进度回调（``Callable[[done, total], None]``），
      每处理完一页调一次（**含读不出来/画框失败的那页**——它也被走过了）。
      与 ``report`` 分开是因为两者用途不同、频率与内容也不同（一个给人看、
      一个驱动进度条）；``progress`` 是可选的，CLI 那条路不传。

    返回：写出的文件路径列表（成功的那几张）。

    ⚠️ **一页框都没有也照样写**（就是一张没画的原图）：用户导出的是"这批
    页面图 + 我认定的框"，漏掉没框的页会让他以为程序跳过了它。
    单页失败（文件被删、图片损坏、磁盘满）不中断整批——记进返回值之外的
    日志，由调用方决定要不要提示；只有 ``cv2``/``numpy`` 装不上这种
    整批性的问题才会抛出去。
    """
    import utils  # 函数内导入：cv2 只在 worker 线程里加载

    from utils.box_draw import draw_slots

    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    written: list = []
    items = list(entries)
    total = len(items)
    for index, (source, slots) in enumerate(items):
        path = Path(source)
        if report is not None:
            report(f"绘制标注图：{path.name}")
        image = utils.imread(path)
        if image is None:
            # 单页读不出来（被删/损坏）不中断整批：其余页仍要导出
            _report_page(progress, index + 1, total)
            continue
        try:
            annotated = draw_slots(image, slots)
        except Exception:  # noqa: BLE001 - 单页画框失败同样不该拖垮整批
            _report_page(progress, index + 1, total)
            continue
        out_path = target / annotated_name(path)
        if utils.imwrite(out_path, annotated):
            written.append(str(out_path))
        _report_page(progress, index + 1, total)
    return written


def _report_page(progress, done: int, total: int) -> None:
    """报一次进度；回调自身抛异常必须吞掉（它是纯旁路，不能带崩整批导出）。"""
    if progress is None:
        return
    try:
        progress(done, total)
    except Exception:  # noqa: BLE001 - 进度汇报失败绝不能中断导出
        pass


def entries_from_mapping(
    images: Sequence,
    boxes: Mapping[str, Sequence],
) -> list:
    """``(图片清单, {页名去后缀: 槽位})`` → :func:`export_annotated` 的入参。

    ⚠️ **只取** ``boxes`` 里有的页：没有框的页不导出，用户要的是"我标了框
    的那些页"。（若产品口径要"整批都导出"，改这里一处即可，别改导出循环。）
    """
    entries = []
    for image in images or []:
        key = Path(image).stem
        slots = boxes.get(key)
        if slots and any(slots):
            entries.append((Path(image), list(slots)))
    return entries


__all__ = [
    "EXPORT_SUFFIX",
    "SLICE_META_NAME",
    "YOLO_IMAGES_DIRNAME",
    "YOLO_LABELS_DIRNAME",
    "YOLO_LABEL_SUFFIX",
    "annotated_name",
    "entries_from_mapping",
    "export_annotated",
    "export_yolo",
    "yolo_dataset_dir",
    "yolo_entries",
    "yolo_label_lines",
]
