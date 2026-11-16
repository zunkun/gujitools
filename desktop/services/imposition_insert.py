# -*- coding: utf-8 -*-
"""拼版「插入 / 上传」的文件落点与成页规则（**纯数据，不碰 Qt**）。

用户 2026-11-16 的口径（左列缩略图右键「向前插入拼版 / 向后插入拼版」、以及
「选择拼版」弹窗里「自己上传图片」）：

- 插入用的图来自**两处**：上一节点给过来的候选池（原文件直接引用，不复制），
  以及用户**当场上传的本地图**（必须复制进任务目录，否则源文件一挪走，
  拼版成品就再也合不出来）；
- **同一张图片可以多次上传**（与「PDF排版 → 插入图片」同一套规范）：复制时
  重名避让，``x.png`` 第二次上传落成 ``x-1.png``，两次各自成页；
- 复制落点 ``<任务目录>/inserted/imposition/``（用户 2026-11-16）：不能放
  ``stages/`` 下——那层是阶段产物，``print_plan`` 会清理"本任务其它阶段的残留"，
  用户插进来的图会被当残留删掉；也不能与打印侧的 ``inserted/`` 混在一起，
  否则打印插进来的图会出现在拼版候选里；
- 上传过的图**一直是候选**：删掉拼版页之后，它们要能像上游图一样回到候选
  列表（见 :func:`uploaded_candidates`——扫的就是这个目录）。

⚠️ 本模块只做"算目标名 / 复制 / 列候选 / 成页 / 插入"这些纯函数，界面与日志
由宿主负责。
"""

from __future__ import annotations

from pathlib import Path

from desktop.services.imposition import (
    ITEMS_PER_PAGE,
    make_page,
    make_single_page,
)
from desktop.utils.files import copy_file_atomic

__all__ = [
    "UPLOAD_DIRNAME",
    "UPLOAD_SUBDIRNAME",
    "insert_pages_at",
    "pages_from_candidates",
    "resolve_chosen",
    "upload_dir",
    "uploaded_candidates",
]

#: 用户上传图在本任务目录里的落点（与打印侧共用 ``inserted`` 这一层，
#: 但拼版另有子目录，见 :func:`upload_dir`）。
UPLOAD_DIRNAME = "inserted"
#: 拼版自己的上传子目录名：``<任务目录>/inserted/imposition/``。
#:
#: ⚠️ **必须与打印侧分开**（用户 2026-11-16：「当前步骤自己上传的图片和缩略图，
#: 不要影响上一步页面查看」）：打印侧的 `inserted/` 是为 PDF 排版准备的一批图，
#: 而拼版的候选清单要**扫目录**（见 :func:`uploaded_candidates`）——两者混在一个
#: 目录里，打印插进来的图会凭空出现在拼版候选里。
UPLOAD_SUBDIRNAME = "imposition"

#: 能当候选/能复制的图片扩展名（与「插入图片」弹窗的文件框同源）
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def upload_dir(task_dir: Path | str) -> Path:
    """拼版上传图的落点：``<任务目录>/inserted/imposition/``。

    ⚠️ 放**任务根目录**的兄弟目录、不进 ``stages/``：那一层是阶段产物，
    ``print_plan`` 会清理"本任务其它阶段的残留"，用户插进来的图会被当残留
    删掉。也**不进上一步的目录**——那会让上一步的页面清单凭空多出一条。
    """
    return Path(task_dir) / UPLOAD_DIRNAME / UPLOAD_SUBDIRNAME


def uploaded_candidates(directory: Path | str | None) -> list[Path]:
    """某任务**曾经上传过、现在还在**的图片（拼版候选的一部分）。

    用户 2026-11-16：删掉拼版页之后，自己上传过的图要像上游图一样**回到候选
    列表**（否则它就再也不出现了）。上传的图本就是复制进这个目录的，所以
    "扫目录"= "列出所有上传过的图"；被页引用过的那些由调用方按
    ``used_source_files`` 减掉。

    只收图片扩展名、按**自然页序**排（``utils.sort_utils.natural_sort_key``，
    与全仓其它图片清单同一个排序键）。目录不存在返回空列表。
    """
    if not directory:
        return []
    from utils.sort_utils import natural_sort_key

    folder = Path(directory)
    if not folder.is_dir():
        return []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    files = [
        path for path in entries
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda path: natural_sort_key(str(path)))


def _target_for(source: Path, target_dir: Path, reserved: set[str]) -> Path:
    """给一张待复制图挑目标文件名（重名避让；``reserved`` 是本次已占用的名字）。

    ⚠️ 避让是**必须**的：同一张图允许上传两次（用户口径），落成同一个文件名
    会让第二份覆盖第一份，两页拼出来是同一张图——而且 ``items`` 里两条路径
    一模一样，删页时也分不清谁是谁。
    """
    target = target_dir / source.name
    counter = 1
    while target.name in reserved or target.exists():
        target = target_dir / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    reserved.add(target.name)
    return target


def resolve_chosen(chosen: list[dict], target_dir: Path | str | None
                   ) -> tuple[list[Path], list[str]]:
    """把弹窗给的候选落成**可用的文件路径**。

    ``chosen`` 是弹窗 :meth:`ImpositionPickerDialog.chosen_items` 的形状：
    ``[{"path": Path, "uploaded": bool}, ...]``（列表顺序 = 候选顺序）。

    - ``uploaded=False``：源池里的图，**原样引用**（不复制、不动文件）；
    - ``uploaded=True``：用户本次上传的图，复制进 ``target_dir`` 再引用。

    返回 ``(文件路径列表, 失败说明列表)``。上传失败的那几张**跳过**（其余照常
    插入）：一张图读不到不该让整次插入报废，但必须让用户在日志里看见。
    """
    files: list[Path] = []
    errors: list[str] = []
    uploads = [item for item in chosen if item.get("uploaded")]
    if uploads and target_dir is None:
        return (
            [Path(item["path"]) for item in chosen if not item.get("uploaded")],
            ["没有可用的上传目录，本次上传的图片未能插入。"],
        )
    directory = Path(target_dir) if target_dir is not None else None
    if uploads and directory is not None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return (
                [Path(item["path"]) for item in chosen
                 if not item.get("uploaded")],
                [f"上传目录创建失败：{type(exc).__name__}: {exc}"],
            )
    reserved: set[str] = set()
    for item in chosen:
        source = Path(str(item.get("path") or ""))
        if not item.get("uploaded"):
            files.append(source)
            continue
        if directory is None:
            continue
        target = _target_for(source, directory, reserved)
        try:
            copy_file_atomic(source, target)
        except OSError as exc:
            errors.append(f"「{source.name}」复制失败：{type(exc).__name__}: {exc}")
            continue
        files.append(target)
    return files, errors


def pages_from_candidates(files: list) -> tuple[list[dict], list[str]]:
    """候选图 → 拼版页：**每两张一页**、落单的单图一页（与选图弹窗同一配对口径）。

    返回 ``(页列表, 读不出尺寸的文件名列表)``。读不到尺寸（文件被挪走/损坏）
    的那张跳过，其余照常成页——这是既有行为（``make_page`` 返回 ``None``）。
    """
    pages: list[dict] = []
    failed: list[str] = []
    texts = [Path(str(path)) for path in files]
    index = 0
    while index < len(texts):
        pair = texts[index:index + ITEMS_PER_PAGE]
        if len(pair) >= ITEMS_PER_PAGE:
            made = make_page(pair)
            names = [path.name for path in pair]
        else:
            made = make_single_page(pair[0])
            names = [pair[0].name]
        if made is not None:
            pages.append(made)
        else:
            failed.extend(names)
        index += ITEMS_PER_PAGE
    return pages, failed


def insert_pages_at(pages: list[dict], new_pages: list[dict], at: int
                    ) -> list[dict]:
    """把 ``new_pages`` 插到 ``pages`` 的第 ``at`` 个位置（越界自动夹住）。

    返回**新列表**（不改入参）：宿主拿到它直接落盘，落盘失败时内存里的旧清单
    还能原样再试一次。
    """
    out = [dict(page) for page in pages or []]
    at = max(0, min(int(at), len(out)))
    out[at:at] = [dict(page) for page in new_pages or []]
    return out
