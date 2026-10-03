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
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

#: 标注图后缀（固定 png，见模块 docstring）
EXPORT_SUFFIX = ".png"


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


__all__ = ["EXPORT_SUFFIX", "annotated_name", "entries_from_mapping", "export_annotated"]
